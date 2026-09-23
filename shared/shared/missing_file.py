"""A file that was not found, answered with the files that were.

"File not found: q3_report.docx", with a hint to check the path, is the
commonest failure a remote caller meets, and the hint cannot help: the caller
cannot look to see what does exist -- it shares no filesystem with this
server -- and a relative path is read from the data folder, not from anywhere
it can see. So it guesses again. `Q3_Report.docx` sitting one case-fold away, or
`Q3_Report.doc` for a caller who remembered the wrong extension, is exactly the
answer it needed and the only thing that could not see it was the server.

Two dozen tools report a missing file, each with its own copy of that hint, so
this is a choke point on the response rather than two dozen edits: any failure
whose error names a missing file gains `did_you_mean` and a hint built from it.
The search is bounded (depth, entries) and, on a confined server, only ever
looks inside the folders it serves -- a suggestion must never become a way to
list a directory the server would refuse to read.
"""

from __future__ import annotations

import difflib
import functools
import os
import re
from pathlib import Path
from typing import Any

from shared.file_utils import PathOutsideRootError, confine, paths_confined


def data_root() -> Path:
    """Where a relative path is read from, as `resolve_path` reads it."""
    if paths_confined():
        for var in ("MCP_DATA_ROOT", "MCP_OUTPUT_DIR"):
            raw = os.environ.get(var, "").strip()
            if raw:
                return Path(raw).expanduser().resolve()
    return Path.cwd()


_MISSING = re.compile(r"^(?:[A-Za-z]+ )?file not found: (?P<name>.+)$", re.IGNORECASE)

MAX_DEPTH = 2
MAX_ENTRIES = 2000
MAX_SUGGESTIONS = 5
MAX_LISTED = 8


def _walk(folder: Path) -> list[Path]:
    """Files under `folder`, at most MAX_DEPTH deep and MAX_ENTRIES in all, hidden ones skipped."""
    found: list[Path] = []
    seen = 0
    base_depth = len(folder.parts)
    for dirpath, dirnames, filenames in os.walk(folder):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if not d.startswith((".", "__")))
        if len(here.parts) - base_depth >= MAX_DEPTH:
            dirnames[:] = []
        for name in sorted(filenames):
            seen += 1
            if seen > MAX_ENTRIES:
                return found
            # `.mcp_` marks this fleet's own bookkeeping beside a file -- a
            # receipt, a lineage record -- never something a caller would pass.
            if not name.startswith(".") and ".mcp_" not in name:
                found.append(here / name)
    return found


def _score(wanted: str, candidate: str) -> float:
    """How close a file name is to the one asked for; 0 for unrelated."""
    w, c = wanted.lower(), candidate.lower()
    if w == c:
        return 3.0  # the same name in other letters: Q3_Report.docx for q3_report.docx
    if Path(w).stem == Path(c).stem:
        return 2.0  # the extension misremembered: .xlsx for .csv
    ratio = difflib.SequenceMatcher(None, w, c).ratio()
    return ratio if ratio >= 0.6 else 0.0


def _shown(path: Path, root: Path) -> str:
    """`path` relative to the data folder when it lies there -- what the caller should pass."""
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


def _search_folders(arguments: dict[str, Any], name: str) -> list[Path]:
    """Where to look: the folder the caller named, then the data folder.

    On a confined server every folder must pass `confine`, so a suggestion can
    only ever name something the server would also have read.
    """
    folders: list[Path] = []
    for value in arguments.values():
        for raw in value if isinstance(value, list) else [value]:
            if not isinstance(raw, str) or not raw.strip().endswith(name):
                continue
            p = Path(raw.strip()).expanduser()
            folders.append((p if p.is_absolute() else data_root() / p).parent)
    if paths_confined() or os.environ.get("MCP_DATA_ROOT", "").strip():
        folders.append(data_root())
    usable: list[Path] = []
    for folder in folders:
        try:
            folder = confine(folder.resolve(), "Folder")
        except PathOutsideRootError, OSError:
            continue
        if folder.is_dir() and folder not in usable:
            usable.append(folder)
    return usable


def suggest(result: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    """`result` with `did_you_mean` and a hint added when its error is a missing file."""
    if result.get("success") is not False or "did_you_mean" in result:
        return result
    match = _MISSING.match(str(result.get("error", "")).strip())
    if not match:
        return result
    name = Path(match.group("name").strip().strip("'\"")).name
    folders = _search_folders(arguments, name)
    if not folders:
        return result
    root = data_root()
    files = [f for folder in folders for f in _walk(folder)]
    scored = sorted(
        {(_score(name, f.name), _shown(f, root)) for f in files if _score(name, f.name) > 0},
        key=lambda pair: (-pair[0], pair[1]),
    )
    close = [shown for _, shown in scored[:MAX_SUGGESTIONS]]
    if close:
        result["did_you_mean"] = close
        result["hint"] = (
            f"Nothing is named {name!r} there. Closest: {', '.join(close)}. "
            "Pass one of those as the path; a relative path is read from the data folder."
        )
    elif paths_confined() and files:
        listed = sorted({_shown(f, root) for f in files})
        more = f" (+{len(listed) - MAX_LISTED} more)" if len(listed) > MAX_LISTED else ""
        result["hint"] = (
            f"Nothing like {name!r} is in the data folder. It holds: "
            f"{', '.join(listed[:MAX_LISTED])}{more}. A relative path is read from it."
        )
    return result


def suggest_missing_files(mcp: Any) -> None:
    """Answer every tool's "File not found" with the nearest files that exist.

    A path refused by confinement is answered here too, in the same shape.
    """
    for tool in mcp._tool_manager._tools.values():
        fn = getattr(tool, "fn", None)
        if fn is None or getattr(fn, "__suggests_missing_files__", False):
            continue
        tool.fn = _suggesting(fn, getattr(tool, "name", fn.__name__))


def refused(tool: str, exc: PathOutsideRootError) -> dict[str, Any]:
    """The fleet's failure shape for a path the server will not touch."""
    return {
        "success": False,
        "op": tool,
        "error": str(exc),
        "hint": "Name a path inside the data folder; a relative path is read from it and written to it.",
        "progress": [],
        "token_estimate": 0,
    }


def _suggesting(fn: Any, name: str) -> Any:
    @functools.wraps(fn)
    def suggesting(*a: Any, **kw: Any) -> Any:
        # A refused path is an answer, not a crash: a resolver outside a tool's
        # own try let the refusal escape as "Error executing tool" with no
        # success, hint or op. Found live on the ML server's anomaly_detection.
        try:
            result = fn(*a, **kw)
        except PathOutsideRootError as exc:
            return refused(name, exc)
        if isinstance(result, dict) and result.get("success") is False:
            try:
                return suggest(result, kw)
            except Exception:
                return result  # a suggestion is a courtesy; it must never cost the real answer
        return result

    suggesting.__suggests_missing_files__ = True  # type: ignore[attr-defined]
    return suggesting
