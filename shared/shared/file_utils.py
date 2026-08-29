"""Safe file path resolution, backup copy, and JSON helpers."""

import base64
import json
import mimetypes
import os
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

__all__ = [
    "apply_default_mode",
    "attach_public_url",
    "embed_content",
    "fetch_url",
    "get_inbox_dir",
    "get_output_dir",
    "hint_for_error",
    "is_url",
    "public_url_for",
    "read_mcp_json",
    "resolve_path",
    "safe_copy",
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


def hint_for_error(e: Exception, path: Path | None = None) -> str:
    """Return a user-facing hint appropriate for the exception type."""
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
    if isinstance(e, (ValueError, TypeError)):
        return (
            "Nothing was written -- this is an argument error, so there is no snapshot to restore. "
            "Fix the value named in the error and call again."
        )
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
