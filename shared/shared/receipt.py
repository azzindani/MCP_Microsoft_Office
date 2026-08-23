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
"""

import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shared.exchange import apply_default_mode


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


def append_receipt(
    file_path: str,
    tool: str,
    server: str = "",
    args: dict[str, Any] | None = None,
    result: str = "",
    backup: str | None = None,
    success: bool = True,
) -> None:
    """Append one entry to the receipt log for this file.

    Creates the log if it does not exist.
    Never raises — receipt failures must not abort the main operation.

    ``server`` and ``success`` default to "" / True so that callers using
    the MCP_Data_Analyst 5-arg signature also work without changes.
    """
    try:
        path = Path(file_path).resolve()
        receipt_path = _receipt_path(path)

        source = receipt_path if receipt_path.exists() else _legacy_receipt_path(path)
        if source is not None:
            # Carry an unambiguous legacy log forward rather than orphaning it:
            # the first write under the new name inherits its entries.
            data: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))
            data["file"] = path.name
        else:
            data = {"file": path.name, "entries": []}

        data["entries"].append(
            {
                "ts": datetime.now(UTC).isoformat(),
                "tool": tool,
                "server": server,
                "args": _sanitise_args(args or {}),
                "result": result,
                "backup": backup,
                "success": success,
            }
        )

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            suffix=".json",
            dir=receipt_path.parent,
        ) as tmp:
            json.dump(data, tmp, indent=2, ensure_ascii=False)
            tmp_path = tmp.name
        apply_default_mode(tmp_path)
        shutil.move(tmp_path, str(receipt_path))

    except Exception:
        pass  # receipt failure must never abort the main operation


def read_receipt_log(file_path: str, last_n: int = 10) -> list[dict[str, Any]]:
    """Return the last N receipt entries for the given file."""
    try:
        path = Path(file_path).resolve()
        receipt_path = _receipt_path(path)
        if not receipt_path.exists():
            legacy = _legacy_receipt_path(path)
            if legacy is None:
                return []
            receipt_path = legacy
        data = json.loads(receipt_path.read_text(encoding="utf-8"))
        entries: list[dict[str, Any]] = data.get("entries", [])
        return entries[-last_n:]
    except Exception:
        return []


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
