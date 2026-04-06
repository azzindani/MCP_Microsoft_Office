"""Live editing — detect open files and notify applications to reload."""

import subprocess
from pathlib import Path
from typing import Any

from shared.platform_utils import is_linux, is_macos, is_windows
from shared.progress import info, ok


def is_file_open(file_path: str) -> bool:
    """Check if the file is currently open in a native application."""
    path = Path(file_path).resolve()

    if is_windows():
        try:
            with open(path, "r+b"):
                return False
        except PermissionError:
            return True
        except Exception:
            return False

    elif is_macos():
        lock_file = path.parent / f".~lock.{path.name}#"
        owner_file = path.parent / f"~${path.name}"
        return lock_file.exists() or owner_file.exists()

    else:  # Linux
        lock_file = path.parent / f".~lock.{path.name}#"
        return lock_file.exists()


def notify_reload(file_path: str, app_type: str) -> dict[str, Any]:
    """
    Attempt to notify the open application to reload the file.

    Returns a progress step dict indicating what happened.
    app_type: "docx", "xlsx", or "pptx"
    """
    if not is_file_open(file_path):
        return ok("File saved", Path(file_path).name)

    if is_macos():
        success = False
        if app_type == "docx":
            success = _notify_word_reload_macos(file_path)
        elif app_type == "xlsx":
            success = _notify_excel_reload_macos(file_path)

        if success:
            return ok("Live update sent — document reloaded in Office")
        return info("File saved — reopen to see changes")

    elif is_linux():
        return info("File saved — accept reload prompt in LibreOffice")

    else:  # Windows
        return info(
            "File saved — close and reopen to see changes",
            "Word has the file locked",
        )


def _notify_word_reload_macos(file_path: str) -> bool:
    """Tell Microsoft Word to close and reopen the document."""
    script = f"""
tell application "Microsoft Word"
    set targetDoc to "{file_path}"
    repeat with d in documents
        if full name of d is targetDoc then
            close d saving no
            open targetDoc
            return true
        end if
    end repeat
end tell
"""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _notify_excel_reload_macos(file_path: str) -> bool:
    """Tell Microsoft Excel to close and reopen the workbook."""
    script = f"""
tell application "Microsoft Excel"
    set targetWB to "{file_path}"
    repeat with wb in workbooks
        if full name of wb is targetWB then
            close wb saving no
            open workbook workbook file name targetWB
            return true
        end if
    end repeat
end tell
"""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False
