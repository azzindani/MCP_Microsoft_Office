"""Operation receipt log — persistent audit trail for document edits."""

import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


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
        receipt_path = path.parent / f"{path.stem}.mcp_receipt.json"

        if receipt_path.exists():
            data: dict[str, Any] = json.loads(receipt_path.read_text(encoding="utf-8"))
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
        shutil.move(tmp_path, str(receipt_path))

    except Exception:
        pass  # receipt failure must never abort the main operation


def read_receipt_log(file_path: str, last_n: int = 10) -> list[dict[str, Any]]:
    """Return the last N receipt entries for the given file."""
    try:
        path = Path(file_path).resolve()
        receipt_path = path.parent / f"{path.stem}.mcp_receipt.json"
        if not receipt_path.exists():
            return []
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
