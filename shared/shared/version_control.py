"""Snapshot, patch log, and rollback for document version control.

A snapshot is named for the file it came from, and until now that name dropped
the extension: `report.docx` and `report.xlsx` sitting in the same directory both
snapshotted to `.mcp_versions/report_{timestamp}.bak`, and the history was read
back with a `{stem}_` prefix match. So one document's history was another
document's history -- and on these servers a .docx, .xlsx and .pptx built for the
same piece of work routinely share a name and a folder.

Proved against the live endpoints with a CSV and a Word document beside it:
restoring the CSV with no timestamp returned the newest snapshot under that
stem, which was the .docx, and answered success: true. 12 bytes of CSV came back
as 37,117 bytes of Word document.

File_System already writes `{stem}_{ts}{ext}.bak`; this brings the Office
servers in line with it and with the two other siblings. Reading stays more
forgiving than writing so snapshots taken before this change are not stranded --
but an extension-less legacy name is only accepted when nothing else in the
directory shares the stem, which is exactly where it cannot be ambiguous.
"""

import hashlib
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

# A snapshot name is the stem, an underscore, then a UTC timestamp that always
# begins with a four-digit year. Matching on `{stem}_` alone also lets a snapshot
# of `report_final.docx` answer a query about `report.docx`.
_TS_PREFIX_LEN = 4


def _versions_dir(file_path: str) -> Path:
    """Return the .mcp_versions/ directory for the given file."""
    return Path(file_path).resolve().parent / ".mcp_versions"


def _backup_name(file_path: str, timestamp: str) -> str:
    """Return the backup filename for a given file and timestamp."""
    src = Path(file_path)
    return f"{src.stem}_{timestamp}{src.suffix}.bak"


def _legacy_backup_name(file_path: str, timestamp: str) -> str:
    """The pre-fix name, without the extension. Read only, never written."""
    return f"{Path(file_path).stem}_{timestamp}.bak"


def _legacy_is_unambiguous(file_path: str) -> bool:
    """True when no other file beside this one shares its stem.

    `report_{ts}.bak` could be a snapshot of report.docx or of report.xlsx. When
    only one `report.*` exists there is nothing to confuse it with, so the old
    name is still safe to offer.
    """
    src = Path(file_path).resolve()
    try:
        siblings = list(src.parent.iterdir())
    except OSError:
        return False
    return not any(p.is_file() and p.stem == src.stem and p.suffix != src.suffix for p in siblings)


def snapshot(file_path: str) -> str:
    """Copy file_path to .mcp_versions/{stem}_{iso_timestamp}{ext}.bak.

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
        backup_path = versions_dir / f"{src.stem}_{timestamp}_{counter}{src.suffix}.bak"
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


def discard_unused_snapshot(backup_path: str, file_path: str) -> bool:
    """Drop a snapshot whose edit never happened. Returns True if removed.

    Every write tool snapshots before it edits, which is the right order --
    there is no way to capture the previous state afterwards. But when the edit
    then raises, the snapshot stays, and the file's history gains an entry for
    something that did not occur. A round-15 phase hit a permission error on a
    workbook and got back `backup: .mcp_versions/book_....xlsx.bak` for a write
    that left A1 exactly as it was.

    The guard is content, not intent: the snapshot is removed only if it is
    still byte-for-byte identical to the file it came from, which means nothing
    was written. A partial write leaves them different, and then the snapshot is
    the only copy of the original and must survive. On any doubt -- unreadable
    file, vanished backup -- it stays.
    """
    try:
        src, bak = Path(file_path).resolve(), Path(backup_path)
        if not src.exists() or not bak.exists():
            return False
        if src.stat().st_size != bak.stat().st_size:
            return False
        if hashlib.sha256(src.read_bytes()).digest() != hashlib.sha256(bak.read_bytes()).digest():
            return False
        bak.unlink()
        return True
    except OSError:
        return False


def restore(file_path: str, timestamp: str) -> bool:
    """
    Copy .mcp_versions/{stem}_{timestamp}{ext}.bak back over file_path.

    Returns True on success, False if backup not found.
    """
    versions_dir = _versions_dir(file_path)
    candidates = [versions_dir / _backup_name(file_path, timestamp)]
    if _legacy_is_unambiguous(file_path):
        candidates.append(versions_dir / _legacy_backup_name(file_path, timestamp))

    for backup_path in candidates:
        if backup_path.exists():
            shutil.copy2(str(backup_path), file_path)
            return True
    return False


def get_history(file_path: str) -> list[dict]:
    """
    Return list of snapshots for file_path, newest first.

    Each dict: {"timestamp": str, "backup_path": str, "size_bytes": int}
    """
    versions_dir = _versions_dir(file_path)
    if not versions_dir.exists():
        return []

    src = Path(file_path)
    prefix = f"{src.stem}_"
    tails = [f"{src.suffix}.bak"]
    if _legacy_is_unambiguous(file_path):
        tails.append(".bak")

    entries = []
    seen: set[str] = set()
    for p in versions_dir.iterdir():
        if not p.name.startswith(prefix) or p.name in seen:
            continue
        for tail in tails:
            if not p.name.endswith(tail):
                continue
            timestamp = p.name[len(prefix) : -len(tail)]
            # The timestamp always opens with a four-digit year. Without this,
            # a snapshot of report_final.docx answers for report.docx.
            if not (timestamp[:_TS_PREFIX_LEN].isdigit() and timestamp[_TS_PREFIX_LEN : _TS_PREFIX_LEN + 1] == "-"):
                continue
            seen.add(p.name)
            entries.append(
                {
                    "timestamp": timestamp,
                    "backup_path": str(p),
                    "size_bytes": p.stat().st_size,
                }
            )
            break

    # Sort newest first (ISO timestamp with hyphens sorts lexicographically)
    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    return entries
