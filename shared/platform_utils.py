"""Platform detection and path utilities for office-mcp."""

import os
import shutil
import sys
import tempfile
from pathlib import Path


def is_windows() -> bool:
    return sys.platform == "win32"


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def get_lmstudio_mcp_config_path() -> Path:
    """Return the LM Studio mcp.json path for the current OS."""
    if is_windows():
        base = Path(os.environ.get("APPDATA", "~")).expanduser()
        return base / "LM Studio" / "mcp.json"
    elif is_macos():
        return Path.home() / "Library" / "Application Support" / "LM Studio" / "mcp.json"
    else:
        return Path.home() / ".config" / "LM Studio" / "mcp.json"


def get_claude_desktop_config_path() -> Path:
    """Return Claude Desktop config path for the current OS."""
    if is_windows():
        base = Path(os.environ.get("APPDATA", "~")).expanduser()
        return base / "Claude" / "claude_desktop_config.json"
    elif is_macos():
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    else:
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def get_cursor_config_path() -> Path:
    """Return Cursor MCP config path."""
    return Path.home() / ".cursor" / "mcp.json"


def get_windsurf_config_path() -> Path:
    """Return Windsurf MCP config path."""
    return Path.home() / ".codeium" / "windsurf" / "mcp_config.json"


def get_cline_config_path() -> Path:
    """Return Cline (VS Code) settings.json path."""
    if is_windows():
        base = Path(os.environ.get("APPDATA", "~")).expanduser()
        return base / "Code" / "User" / "settings.json"
    elif is_macos():
        return (
            Path.home() / "Library" / "Application Support" / "Code" / "User" / "settings.json"
        )
    else:
        return Path.home() / ".config" / "Code" / "User" / "settings.json"


def get_pdf_converter() -> str | None:
    """
    Return the available PDF conversion tool for the current platform.

    Returns 'word' if Microsoft Word is available (Windows/macOS).
    Returns 'libreoffice' if LibreOffice is available.
    Returns None if neither is available.
    """
    if is_windows():
        word_paths = [
            Path("C:/Program Files/Microsoft Office/root/Office16/WINWORD.EXE"),
            Path("C:/Program Files (x86)/Microsoft Office/root/Office16/WINWORD.EXE"),
        ]
        if any(p.exists() for p in word_paths):
            return "word"
    elif is_macos():
        if Path("/Applications/Microsoft Word.app").exists():
            return "word"

    if shutil.which("libreoffice") or shutil.which("soffice"):
        return "libreoffice"
    return None


def get_temp_dir() -> Path:
    """Return a reliable temp directory for the current platform."""
    d = Path(tempfile.gettempdir()) / "office-mcp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_8gb_mode() -> bool:
    """Return True when OFFICE_MCP_8GB_MODE=1 is set."""
    return os.environ.get("OFFICE_MCP_8GB_MODE", "0") == "1"


def get_max_paragraphs() -> int:
    """Maximum paragraphs to return in a range read."""
    return 20 if is_8gb_mode() else 50


def get_max_cells() -> int:
    """Maximum cells to return in a range read."""
    return 100 if is_8gb_mode() else 200


def get_max_search_results() -> int:
    """Maximum search results to return."""
    return 10 if is_8gb_mode() else 50
