"""Operation receipt log — persistent audit trail for document edits.

The log is `{filename}.mcp_receipt.json`, beside the file. It used to be
`{stem}.mcp_receipt.json`, and that had two consequences.

`report.docx`, `report.xlsx` and `report.pptx` -- three files these servers
routinely build for the same piece of work, in one folder -- all wrote to
`report.mcp_receipt.json`. One document's audit trail was another document's
audit trail, and the log's own `file` field named whichever created it first.

And the three sibling repos all name the log for the full filename, so an edit
made here was invisible to a File_System or Data_Analyst `read_receipt` on the
same document: they looked for `report.docx.mcp_receipt.json`, which did not
exist. Office was the odd one out of four.

Reading falls back to the old name so nothing already written is stranded, and
only where the stem is unambiguous -- if a namesake with another extension sits
beside the file, the old log cannot be attributed to either.

**The name was fixed and the format was not.**

That earlier repair made the siblings look in the right place and find
something they could not read. Office wrote a JSON *object*,
`{"file": ..., "entries": [...]}`; MCP_Data_Analyst, MCP_Machine_Learning and
MCP_File_System all wrote a JSON *array*. Every one of them does
`json.loads(...)` and iterates, so an Office log read from a sibling yielded
the string keys "file" and "entries" where entries were expected, and a sibling
log read here returned `[]` from `data.get("entries", [])` on a list. The same
document, the same filename, four servers, and no two of them could read each
other. That is worth more than the naming fix it followed, because a rename or
a move in MCP_File_System is exactly the operation that puts a second server's
entries into a document's history.

So writing now uses the array form the other three use, with the scope header
they added, and reading accepts all three shapes: headed array, bare array, and
this repo's own legacy object. Nothing already on disk becomes unreadable.

**What the log records, and why the file says so.** `append_receipt` is called
by the tools that CHANGE a file. Reads change nothing and are not in here --
true, defensible, and previously invisible. A user review drove twenty calls at
one file, read two entries, and concluded eighteen operations had vanished.
`RECEIPT_SCOPE` is that sentence, carried in the file and handed back by
`read_receipt`.
"""

import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shared.exchange import apply_default_mode

# Identical wording to the siblings: they write the same file, and a caller
# reading the scope should not be able to tell which server wrote it.
RECEIPT_SCOPE = (
    "mutations only: operations that wrote to this file. Reads, inspections, "
    "correlations and chart generation are not recorded here."
)

# Above this, a content hash costs more than the operation it describes.
_MAX_HASH_BYTES = 64 * 1024 * 1024


def _receipt_path(path: Path) -> Path:
    """Where this file's log lives, named as all four repos name it."""
    return path.parent / f"{path.name}.mcp_receipt.json"


def _legacy_receipt_path(path: Path) -> Path | None:
    """The pre-fix stem-named log, when it can only be this file's."""
    legacy = path.parent / f"{path.stem}.mcp_receipt.json"
    if legacy == _receipt_path(path) or not legacy.exists():
        return None
    try:
        siblings = list(path.parent.iterdir())
    except OSError:
        return None
    if any(p.is_file() and p.stem == path.stem and p.suffix != path.suffix for p in siblings):
        return None
    return legacy


def _hash_args(args: dict[str, Any]) -> str:
    """Stable hash of the arguments, so two calls can be told apart."""
    try:
        blob = json.dumps(args, sort_keys=True, default=str)
    except Exception:
        blob = repr(sorted(args.items()))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def fingerprint(file_path: str | Path) -> str:
    """Identify a file's contents, or say honestly that this is not a hash.

    Returns `sha256:<16 hex>` for a file small enough to read, and
    `size-mtime:<...>` for one that is not. The prefix is the point: a caller
    comparing two fingerprints must be able to tell a content hash from a
    cheaper stand-in, because only one of them proves the bytes are the same.
    """
    p = Path(file_path)
    try:
        stat = p.stat()
    except OSError:
        return ""
    if stat.st_size > _MAX_HASH_BYTES:
        return f"size-mtime:{stat.st_size}-{int(stat.st_mtime)}"
    try:
        digest = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    except OSError:
        return f"size-mtime:{stat.st_size}-{int(stat.st_mtime)}"
    return f"sha256:{digest}"


def _split_header(loaded: Any) -> tuple[list[dict], dict | None]:
    """Entries and scope header, from any of the three shapes ever written.

    * headed array  -- `[{"_scope": ...}, entry, ...]`, what this writes now
    * bare array    -- what the siblings wrote before the header existed
    * legacy object -- `{"file": ..., "entries": [...]}`, what this repo wrote
    """
    if isinstance(loaded, dict):
        entries = loaded.get("entries", [])
        return [e for e in entries if isinstance(e, dict)], None
    if not isinstance(loaded, list) or not loaded:
        return [], None
    first = loaded[0]
    if isinstance(first, dict) and "_scope" in first:
        return [e for e in loaded[1:] if isinstance(e, dict)], first
    return [e for e in loaded if isinstance(e, dict)], None


def append_receipt(
    file_path: str,
    tool: str,
    server: str = "",
    args: dict[str, Any] | None = None,
    result: str = "",
    backup: str | None = None,
    success: bool = True,
    input_fingerprint: str = "",
    duration_ms: float | None = None,
) -> None:
    """Append one entry to the receipt log for this file.

    Creates the log if it does not exist.
    Never raises — receipt failures must not abort the main operation.

    ``server`` and ``success`` default to "" / True so that callers using
    the MCP_Data_Analyst 5-arg signature also work without changes.

    ``input_fingerprint`` is what ``fingerprint()`` returned BEFORE the write;
    the output side is measured here, after it. Omit it and the entry is still
    valid -- one side of a lineage is better than none.
    """
    try:
        path = Path(file_path).resolve()
        receipt_path = _receipt_path(path)

        source = receipt_path if receipt_path.exists() else _legacy_receipt_path(path)
        entries: list[dict[str, Any]] = []
        header: dict[str, Any] | None = None
        if source is not None:
            # Carry an unambiguous legacy log forward rather than orphaning it:
            # the first write under the new name inherits its entries, whichever
            # of the three shapes they were stored in.
            try:
                entries, header = _split_header(json.loads(source.read_text(encoding="utf-8")))
            except Exception:
                entries, header = [], None

        entry: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "tool": tool,
            "server": server,
            "args": _sanitise_args(args or {}),
            "args_hash": _hash_args(_sanitise_args(args or {})),
            "result": result,
            "backup": backup,
            "success": success,
        }
        if input_fingerprint:
            entry["input"] = input_fingerprint
        after = fingerprint(path)
        if after:
            entry["output"] = after
        if duration_ms is not None:
            entry["duration_ms"] = round(float(duration_ms), 1)
        entries.append(entry)

        head = header or {"_scope": RECEIPT_SCOPE, "_format": 2, "file": path.name}
        head.setdefault("file", path.name)
        payload = [head, *entries]

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            suffix=".json",
            dir=receipt_path.parent,
        ) as tmp:
            json.dump(payload, tmp, indent=2, ensure_ascii=False, default=str)
            tmp_path = tmp.name
        apply_default_mode(tmp_path)
        shutil.move(tmp_path, str(receipt_path))

    except Exception:
        pass  # receipt failure must never abort the main operation


def read_receipt_log(file_path: str, last_n: int = 10) -> list[dict[str, Any]]:
    """Return the last N receipt entries for the given file, oldest first."""
    entries, _ = read_receipt(file_path, last_n)
    return entries


def read_receipt(file_path: str, last_n: int = 10) -> tuple[list[dict[str, Any]], str]:
    """The last N entries and the scope sentence that belongs beside them.

    Two return values rather than one because the count alone is what misled a
    caller: twenty operations, two entries, and no way to learn from the log
    that eighteen of them were never eligible for it.
    """
    try:
        path = Path(file_path).resolve()
        receipt_path = _receipt_path(path)
        if not receipt_path.exists():
            legacy = _legacy_receipt_path(path)
            if legacy is None:
                return [], RECEIPT_SCOPE
            receipt_path = legacy
        entries, header = _split_header(json.loads(receipt_path.read_text(encoding="utf-8")))
        scope = str(header.get("_scope")) if header else RECEIPT_SCOPE
        return (entries[-last_n:] if last_n > 0 else entries), scope
    except Exception:
        return [], RECEIPT_SCOPE


def _sanitise_args(args: dict[str, Any]) -> dict[str, Any]:
    """Remove large values from args before logging."""
    sanitised: dict[str, Any] = {}
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 200:
            sanitised[k] = v[:200] + "... [truncated]"
        elif isinstance(v, list) and len(v) > 10:
            sanitised[k] = list(v[:10]) + ["... [truncated]"]
        else:
            sanitised[k] = v
    return sanitised
