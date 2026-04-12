"""Safe file path resolution, backup copy, and JSON helpers."""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


def _downloads_dir() -> Path:
    """Return the user's Downloads directory."""
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
    """
    Normalise any user-provided file path to an absolute resolved Path.

    Handles:
    - Leading/trailing whitespace and wrapping quotes
    - ~ home directory expansion
    - Environment variable expansion ($HOME, %USERPROFILE%)
    - Windows backslash paths
    - Windows UNC paths and long-path prefix (\\\\?\\)
    - Relative paths (resolved from CWD)

    Raises:
        ValueError: if path is inside .mcp_versions/ or contains null bytes
    """
    s = raw.strip()

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

    # Reject paths inside .mcp_versions/ to prevent snapshot-of-snapshot loops
    if ".mcp_versions" in path.parts:
        raise ValueError(f"Path '{path}' is inside .mcp_versions/. Pass the original document path, not a backup path.")

    # Add Windows long-path prefix if needed
    if sys.platform == "win32" and len(str(path)) > 200:
        path = Path("\\\\?\\" + str(path))

    return path


def hint_for_error(e: Exception, path: Path | None = None) -> str:
    """Return a user-facing hint appropriate for the exception type."""
    if isinstance(e, PermissionError):
        name = path.name if path else "the file"
        return f"'{name}' is open in Word, Excel, or PowerPoint. Close it and try again."
    return "Use restore_version to undo if a snapshot was taken."


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
    shutil.move(tmp_path, str(p))
