"""Snapshot, patch log, and rollback for document version control."""

import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def _versions_dir(file_path: str) -> Path:
    """Return the .mcp_versions/ directory for the given file."""
    return Path(file_path).resolve().parent / ".mcp_versions"


def _backup_name(file_path: str, timestamp: str) -> str:
    """Return the backup filename for a given file and timestamp."""
    stem = Path(file_path).stem
    return f"{stem}_{timestamp}.bak"


def snapshot(file_path: str) -> str:
    """Copy file_path to .mcp_versions/{stem}_{iso_timestamp}.bak.

    Returns the backup path as a string.
    Raises FileNotFoundError if file_path does not exist.

    Uses microsecond-precision timestamps and a collision counter so that
    two snapshots taken within the same second produce distinct filenames
    (important on Windows where datetime resolution can be coarse).
    Write is atomic: temp-file + rename so a partial copy is never visible.
    """
    src = Path(file_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"File not found: {src}")

    versions_dir = _versions_dir(file_path)
    versions_dir.mkdir(parents=True, exist_ok=True)

    # Microsecond-precision timestamp avoids same-second collisions
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    backup_path = versions_dir / _backup_name(file_path, timestamp)

    # Collision counter: append _N if the path already exists
    counter = 1
    while backup_path.exists():
        stem = Path(file_path).stem
        backup_path = versions_dir / f"{stem}_{timestamp}_{counter}.bak"
        counter += 1

    # Atomic write: copy to a temp file then rename
    tmp_fd, tmp_path = tempfile.mkstemp(dir=versions_dir)
    try:
        os.close(tmp_fd)
        shutil.copy2(str(src), tmp_path)
        shutil.move(tmp_path, str(backup_path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return str(backup_path)


def restore(file_path: str, timestamp: str) -> bool:
    """
    Copy .mcp_versions/{stem}_{timestamp}.bak back over file_path.

    Returns True on success, False if backup not found.
    """
    backup_name = _backup_name(file_path, timestamp)
    backup_path = _versions_dir(file_path) / backup_name

    if not backup_path.exists():
        return False

    shutil.copy2(str(backup_path), file_path)
    return True


def get_history(file_path: str) -> list[dict]:
    """
    Return list of snapshots for file_path, newest first.

    Each dict: {"timestamp": str, "backup_path": str, "size_bytes": int}
    """
    versions_dir = _versions_dir(file_path)
    if not versions_dir.exists():
        return []

    stem = Path(file_path).stem
    prefix = f"{stem}_"
    suffix = ".bak"

    entries = []
    for p in versions_dir.iterdir():
        if p.name.startswith(prefix) and p.name.endswith(suffix):
            # Extract timestamp: remove prefix and suffix
            timestamp = p.name[len(prefix) : -len(suffix)]
            entries.append(
                {
                    "timestamp": timestamp,
                    "backup_path": str(p),
                    "size_bytes": p.stat().st_size,
                }
            )

    # Sort newest first (ISO timestamp with hyphens sorts lexicographically)
    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    return entries
