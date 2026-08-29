"""Safe file path resolution, backup copy, and JSON helpers."""

import base64
import json
import mimetypes
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from shared.exchange import (
    apply_default_mode,
    attach_public_url,
    fetch_url,
    get_inbox_dir,
    get_output_dir,
    is_url,
    public_url_for,
    url_fetch_enabled,
)
from shared.version_control import discard_unused_snapshot

__all__ = [
    "apply_default_mode",
    "attach_public_url",
    "drop_snapshot_if_unwritten",
    "embed_content",
    "fetch_url",
    "get_inbox_dir",
    "get_output_dir",
    "hint_for_error",
    "image_hint",
    "image_problem",
    "is_url",
    "public_url_for",
    "read_mcp_json",
    "resolve_path",
    "safe_copy",
    "scrub_repr",
    "sheet_names_hint",
    "url_fetch_enabled",
    "write_mcp_json",
]


def _downloads_dir() -> Path:
    """Return MCP_OUTPUT_DIR when set, else the user's Downloads directory.

    A container deployment sets MCP_OUTPUT_DIR to a bind-mounted directory so
    generated documents land somewhere the caller can reach; unset, this is
    the original ~/Downloads behaviour.
    """
    if os.environ.get("MCP_OUTPUT_DIR", "").strip():
        return get_output_dir()
    if sys.platform == "win32":
        base = Path(os.environ.get("USERPROFILE", str(Path.home())))
    else:
        base = Path.home()
    return base / "Downloads"


try:
    import json5  # type: ignore[import-untyped]

    _HAS_JSON5 = True
except ImportError:
    _HAS_JSON5 = False


def resolve_path(raw: str) -> Path:
    """Normalise any user-provided file path to an absolute resolved Path.

    Handles:
    - workspace:name/alias and project:name/alias prefixes (DA interop)
    - Leading/trailing whitespace and wrapping quotes
    - ~ home directory expansion
    - Environment variable expansion ($HOME, %USERPROFILE%)
    - Windows backslash paths
    - Windows UNC paths and long-path prefix (\\\\?\\)
    - Relative paths (resolved from CWD)
    - http(s) URLs, downloaded into the inbox dir first (MCP_FETCH_URLS=1;
      off by default — see shared/exchange.py)

    Raises:
        ValueError: if path is inside .mcp_versions/ or contains null bytes
    """
    s = raw.strip()

    if is_url(s):
        return fetch_url(s)

    # Resolve workspace: / project: aliases produced by MCP_Data_Analyst handover
    if s.startswith("workspace:") or s.startswith("project:"):
        try:
            from shared.workspace_utils import resolve_alias  # type: ignore[import]

            return resolve_alias(s)
        except Exception as exc:
            raise ValueError(f"Cannot resolve workspace alias '{s}': {exc}") from exc

    # Strip wrapping quotes (drag-and-drop artifact)
    if len(s) >= 2 and ((s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'"))):
        s = s[1:-1].strip()

    # Strip Windows long-path prefix
    if s.startswith("\\\\?\\"):
        s = s[4:]

    # Reject null bytes
    if "\x00" in s:
        raise ValueError("Path contains null byte — invalid path.")

    # Expand environment variables and ~
    s = os.path.expandvars(s)
    s = os.path.expanduser(s)

    # Normalise backslashes on Windows
    if sys.platform == "win32":
        s = s.replace("\\", "/")

    p = Path(s)

    # Bare filename (no directory component): check Downloads before falling back to CWD.
    # This lets tools find files that were created by _new servers (which default to Downloads).
    if p.parent == Path(".") and not p.is_absolute():
        downloads_candidate = _downloads_dir() / p.name
        if downloads_candidate.exists():
            p = downloads_candidate

    path = p.resolve()

    # Reject paths inside .mcp_versions/ to prevent snapshot-of-snapshot loops.
    #
    # get_history hands back backup_path for every entry, and this refused the
    # very paths it had just been given -- so a caller who wanted to *look at*
    # an old version was told only what not to pass, never how to see it. The
    # guard is right (a write to a backup snapshots the snapshot); the silence
    # about the timestamp route was not. Versions are addressed by timestamp
    # plus the original path, never by the .bak path itself.
    if ".mcp_versions" in path.parts:
        raise ValueError(
            f"Path '{path}' is inside .mcp_versions/. Snapshots are addressed by timestamp, not by "
            "path: get_history lists them, and restore_version and diff_versions take that timestamp "
            "together with the original file_path. To open a .bak directly, copy it outside "
            ".mcp_versions/ first."
        )

    # Add Windows long-path prefix if needed
    if sys.platform == "win32" and len(str(path)) > 200:
        path = Path("\\\\?\\" + str(path))

    return path


SNAPSHOT_ROUTE_HINT = (
    "Call get_history() for the timestamps, then restore_version() or diff_versions() with the "
    "ORIGINAL file_path and that timestamp. To read a .bak directly, copy it outside "
    ".mcp_versions/ first."
)


def hint_for_message(message: str, default: str) -> str:
    """Keep a hint that fits the error, instead of one that contradicts it.

    A call site's default hint is written for the common failure and then
    handed to every exception its try block can raise. That is usually
    harmless, and once was not:

        read_document(".../.mcp_versions/working_....docx.bak")
        -> error: "... is inside .mcp_versions/. Snapshots are addressed by
                   timestamp ... restore_version and diff_versions take that
                   timestamp together with the original file_path."
           hint:  "Check that file_path is a valid .docx file."

    The file *is* a valid .docx. It is only in a directory the tools refuse to
    open, the error already said exactly what to do instead, and `hint` is the
    field a caller acts on -- so the response argued a caller out of the answer
    it had just handed them. A hint that names a specific wrong fix is worse
    than a vague one, the same lesson as the PermissionError branch below.
    """
    if ".mcp_versions" in message:
        return SNAPSHOT_ROUTE_HINT
    return default


# "cannot identify image file <_io.BytesIO object at 0x7170edaa6a70>"
#
# A default Python repr, heap pointer included, reaching a client as the `error`
# field of a JSON response. Round 19b got that one out of add_image_to_all_slides
# on a corrupt PNG. It tells the caller nothing, it changes on every run so no
# test or cache can key on it, and the address is an implementation detail of a
# process the caller cannot see.
#
# Every tool here builds its error as str(e), so any library that interpolates
# an object into its message can leak one. Substituting the type name keeps the
# sentence readable -- "cannot identify image file <BytesIO>" -- and is the
# identity function on the ordinary messages that make up almost every error.
_OBJECT_REPR = re.compile(r"<([A-Za-z_][\w.]*) object at 0x[0-9a-fA-F]+>")


def scrub_repr(e: Exception | str) -> str:
    """str(e) with any <... object at 0x...> reduced to its bare type name."""
    return _OBJECT_REPR.sub(lambda m: f"<{m.group(1).rsplit('.', 1)[-1]}>", str(e))


# Raised while VALIDATING, before anything is saved. The round-18 fix listed
# only ValueError and TypeError, which covered openpyxl's coordinate checks --
# the case it was written for -- and let every sibling fall through to the
# "Use restore_version to undo" line it existed to remove. Round 19b reached
# that line twice, on two different servers:
#
#   xlsx  sort_sheet(column="qty")        IndexError            list index out of range
#   pptx  add_image_to_all_slides(...)    UnidentifiedImageError  (a corrupt PNG)
#
# Both wrote nothing, and both were told to restore a snapshot.
#
# UnidentifiedImageError subclasses OSError, and OSError as a whole is NOT an
# argument error -- a disk filling up mid-save belongs on the restore branch --
# so it is matched by name rather than by widening to its base class.
_ARGUMENT_ERROR_TYPES = (ValueError, TypeError, IndexError, KeyError)
_ARGUMENT_ERROR_NAMES = frozenset({"UnidentifiedImageError"})


def _is_argument_error(e: Exception) -> bool:
    """True when e was raised validating an argument, before any write."""
    if isinstance(e, (PermissionError, FileNotFoundError)):
        return False
    return isinstance(e, _ARGUMENT_ERROR_TYPES) or type(e).__name__ in _ARGUMENT_ERROR_NAMES


SUPPORTED_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff"})


def image_problem(path: Path) -> str | None:
    """Say why this file cannot be inserted as an image, or None if it can.

    The three image tools in this fleet each checked the *extension* and
    nothing else, so a file named .png holding anything at all got as far as
    python-pptx, which snapshots the deck, hands the bytes to Pillow and lets

        cannot identify image file <_io.BytesIO object at 0x7170edaa6a70>

    out as the tool's error -- a heap address in place of the one fact the
    caller needed, which is that the file is not an image. Reading the header
    here costs one open() and moves the failure in front of the snapshot.
    """
    if path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        return f"Unsupported image format: {path.suffix or '(no extension)'}"
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow ships with python-pptx
        return None
    try:
        with Image.open(path) as probe:
            probe.verify()
    except Exception:
        return f"{path.name} has a {path.suffix} extension but its contents are not a readable image"
    return None


def image_hint(path: Path) -> str:
    """The hint that goes with image_problem(path).

    Kept beside it so the three image tools answer the same way. The
    contents-not-extension wording is load-bearing: a caller who named the file
    .png believes it is a PNG, and "supported formats: png, jpg, ..." reads as
    though .png were not on the list.
    """
    formats = ", ".join(sorted(s.lstrip(".").upper() for s in SUPPORTED_IMAGE_SUFFIXES))
    if path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        return f"Nothing was written. Supported formats: {formats}."
    return (
        f"The {path.suffix} extension names a format but not the contents -- pass a file whose "
        f"contents really are an image. Nothing was written. Supported formats: {formats}."
    )


def drop_snapshot_if_unwritten(
    backup: str | None, path: Path | None, progress: list[dict[str, Any]] | None = None
) -> str | None:
    """Report a snapshot only if it still stands for something that happened.

    Every write tool snapshots before it edits, which is the only order that can
    work. When validation then fails, the copy is left behind and advertised:
    round 19b made three argument mistakes against one workbook and got three
    .bak files plus, in each response,

        "hint":   "Nothing was written -- ... there is no snapshot to restore."
        "backup": ".mcp_versions/p53_2026-...-xlsx.bak"
        "progress": [{"icon": "✔", "msg": "Snapshot saved"}]

    -- the hint denying what the other two fields advertise. Round 18 fixed the
    sentence and left the contradiction; before it, the hint at least agreed
    with `backup`.

    `discard_unused_snapshot` has answered this since round 15 and no caller
    ever used it: it removes the copy only when it is still byte-identical to
    its source, so a partial write keeps its snapshot and any doubt keeps it too.
    This is the wrapper that puts it in the response path.
    """
    if not backup or path is None:
        return backup
    if not discard_unused_snapshot(backup, str(path)):
        return backup
    if progress is not None:
        # The log said "✔ Snapshot saved" on the way in and that entry is still
        # sitting there. Leaving it makes the execution log the last field still
        # claiming a backup that no longer exists -- a fix that stops at two of
        # the three fields is not a fix.
        for entry in progress:
            if entry.get("msg") == "Snapshot saved":
                entry["icon"] = "→"
                entry["status"] = "info"
                entry["msg"] = entry["message"] = "Snapshot discarded — nothing was written"
                entry.pop("detail", None)
    return None


def hint_for_error(e: Exception, path: Path | None = None, argument: str | None = None) -> str:
    """Return a user-facing hint appropriate for the exception type.

    Pass `argument` when the caller knows which parameter was being validated;
    the hint then names it instead of asserting the error text does.
    """
    # Checked before the type branches: the guard raises a plain ValueError, so
    # nothing below would recognise it, and the path-is-None branch would answer
    # "Pass an absolute path to an existing file" -- which this already is.
    if ".mcp_versions" in str(e):
        return SNAPSHOT_ROUTE_HINT
    if isinstance(e, PermissionError):
        name = path.name if path else "the file"
        # This used to answer "is open in Word, Excel, or PowerPoint" for every
        # PermissionError, which is a Windows file-lock answer given to a Linux
        # ownership problem. A round-15 phase hit `[Errno 13] Permission denied`
        # on a root-owned workbook, was told to close an application that was
        # not running, and retried into the same error. A hint that names a
        # specific WRONG fix is worse than a vague one: the caller acts on it.
        #
        # os.access with the real uid answers the question directly -- if the
        # process cannot write the file, no amount of closing Excel will help.
        if path is not None and path.exists() and not os.access(path, os.W_OK):
            return (
                f"'{name}' is not writable by this process -- check its owner and mode. "
                "On a container mount the MCP server often runs as a different user than your shell, "
                "so a file created with bash needs chmod/chown before a tool can write it."
            )
        return f"'{name}' is open in Word, Excel, or PowerPoint. Close it and try again."
    if isinstance(e, FileNotFoundError):
        return "That path does not exist. Check the directory was created first."
    if path is None:
        # resolve_path() raised, so file_path never became a Path at all: a
        # workspace:/project: alias that does not resolve, a path inside
        # .mcp_versions/, a null byte, a URL that could not be fetched. The
        # generic "use restore_version to undo" answer is doubly wrong here --
        # nothing was written, and the fix is to the argument.
        return "file_path could not be resolved. Pass an absolute path to an existing file."
    # An argument error is raised while VALIDATING, before the workbook or the
    # document is ever saved -- openpyxl's own coordinate checks, our range and
    # index checks, a value of the wrong type. Nothing has been written, so the
    # fallback below is advice to destroy unrelated work in answer to a typo:
    #
    #     set_cell(cell_address="A0")
    #     error: Row numbers must be between 1 and 1048576. Row number supplied was 0
    #     hint : Use restore_version to undo if a snapshot was taken.
    #
    # Round 18 followed that hint literally, which is what a model with nothing
    # else to go on does. It restored a snapshot three times over (set_cell,
    # set_range, insert_row) and every retry failed, because rolling a file back
    # cannot fix a bad argument; one phase reached for a DIFFERENT server's
    # restore_version to do it.
    #
    # The error text already names the offending value, so the hint's job is
    # only to say what to do about it -- and, above all, that there is nothing
    # to undo.
    #
    # `argument`, when the call site passes it, is the precise form: the error
    # text does not always name anything actionable, and round 19b caught the
    # round-18 sentence promising it does when it does not --
    #
    #     sort_sheet(column="B")        '<' not supported between instances of 'int' and 'str'
    #     set_font_all_slides("red")    invalid literal for int() with base 16: 're'
    #     sort_sheet(column="qty")      list index out of range
    #
    # -- three leaked exceptions naming no argument at all, under a hint that
    # told the caller to go and fix the one the error named. The function
    # validating the value always knows which parameter it came from even when
    # the exception it caught does not, so it can say so.
    if _is_argument_error(e):
        target = f"Fix the {argument} argument" if argument else "Fix the value named in the error"
        return f"Nothing was written -- this is an argument error, so there is no snapshot to restore. {target} and call again."
    return "Use restore_version to undo if a snapshot was taken."


# Every "Sheet 'X' not found" in the xlsx servers answered "Use list_sheets to
# get available sheet names." -- a second call to learn something the workbook
# already open in front of it knows. Every other server in the fleet names the
# alternatives inline (read_column_stats lists the columns, fs_write lists the
# valid ops), so a caller that guessed a sheet name wrong spends one round trip
# rather than two.
_SHEET_HINT_LIMIT = 12


def sheet_names_hint(sheet_names: list[str]) -> str:
    """Hint naming the sheets that exist. Read sheetnames before closing the wb."""
    if not sheet_names:
        return "The workbook has no sheets. Use add_sheet to create one."
    shown = ", ".join(sheet_names[:_SHEET_HINT_LIMIT])
    extra = len(sheet_names) - _SHEET_HINT_LIMIT
    if extra > 0:
        return f"Available sheets: {shown} (+{extra} more). Use list_sheets for the full list."
    return f"Available sheets: {shown}"


# mimetypes.guess_type() depends on the OS's registered MIME db (registry on
# Windows, /etc/mime.types on Linux/macOS) and doesn't reliably know Office
# Open XML types on every platform — verified missing on windows-latest CI
# runners specifically. Known extensions are resolved here first.
_KNOWN_MIME_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".pdf": "application/pdf",
}


def embed_content(result: dict[str, Any], path: Path, return_content: bool) -> dict[str, Any]:
    """Attach `public_url`, and base64 file bytes when return_content is set.

    In remote/HTTP deployments the caller has no filesystem in common with this
    server, so a server-local output path is useless to it. `public_url` (set
    whenever the file lands under a publicly served MCP_OUTPUT_DIR) gives it a
    link; return_content gives it the bytes themselves. A read failure here
    doesn't fail the whole tool call.
    """
    if not result.get("success"):
        return result
    attach_public_url(result, path)
    if not return_content:
        return result
    try:
        data = path.read_bytes()
    except OSError:
        return result
    result["content_base64"] = base64.b64encode(data).decode("ascii")
    mime = _KNOWN_MIME_TYPES.get(path.suffix.lower())
    if mime is None:
        mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    result["content_mime_type"] = mime
    return result


def safe_copy(src: str, dst: str) -> None:
    """Copy src to dst, creating parent directories as needed."""
    dst_path = Path(dst)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def read_mcp_json(path: str) -> dict[str, Any]:
    """
    Parse an MCP config JSON file safely.

    Uses json5 if available (handles trailing commas and inline comments).
    Returns an empty dict if the file does not exist.
    """
    p = Path(path)
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8")
    if _HAS_JSON5:
        result = json5.loads(text)
    else:
        result = json.loads(text)
    if not isinstance(result, dict):
        return {}
    return result


def write_mcp_json(path: str, data: dict[str, Any]) -> None:
    """
    Write an MCP config JSON file atomically.

    Writes to a temp file first, then renames to avoid partial writes.
    Pretty-prints with 2-space indent.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        suffix=".json",
        dir=p.parent,
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    apply_default_mode(tmp_path)
    shutil.move(tmp_path, str(p))
