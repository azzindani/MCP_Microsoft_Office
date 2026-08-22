"""Progress step helpers for tool response 'progress' arrays.

Each entry emits both Office-MCP fields (icon, msg) and DA-compatible fields
(status, message) so both server families produce a consistent schema that
the LLM can read without branching on the server name.
"""

from typing import Any

# Maps icon → DA-compatible status string
_ICON_TO_STATUS: dict[str, str] = {
    "✔": "ok",
    "✘": "fail",
    "→": "info",
    "⚠": "warn",
    "↩": "undo",
}


def step(icon: str, msg: str, detail: str = "") -> dict[str, Any]:
    """Create a single progress step dict with dual-schema fields."""
    entry: dict[str, Any] = {
        # Office-MCP native fields
        "icon": icon,
        "msg": msg,
        # DA-compatible fields (same values, different keys)
        "status": _ICON_TO_STATUS.get(icon, "info"),
        "message": msg,
    }
    if detail:
        entry["detail"] = detail
    return entry


def ok(msg: str, detail: str = "") -> dict[str, Any]:
    """Successful step."""
    return step("✔", msg, detail)


def fail(msg: str, detail: str = "") -> dict[str, Any]:
    """Failed step — operation stops here."""
    return step("✘", msg, detail)


def info(msg: str, detail: str = "") -> dict[str, Any]:
    """Informational step — no pass/fail."""
    return step("→", msg, detail)


def warn(msg: str, detail: str = "") -> dict[str, Any]:
    """Warning step — operation continues."""
    return step("⚠", msg, detail)


def undo(msg: str, detail: str = "") -> dict[str, Any]:
    """Rollback or restore step."""
    return step("↩", msg, detail)


def format_progress(steps: list[dict[str, Any]]) -> str:
    """Format a progress list as a human-readable string."""
    lines = []
    for s in steps:
        line = f"{s['icon']} {s['msg']}"
        if s.get("detail"):
            line += f" ({s['detail']})"
        lines.append(line)
    return "\n".join(lines)


def index_range(total: int, noun: str) -> str:
    """Describe the valid index range, or say the collection is empty.

    Twenty-seven call sites hand-built this as f"(0-{total - 1})", which reads
    "(0--1)" when there is nothing to index. A coverage sweep hit an empty
    document and got "Table index 0 out of range (0--1)" from four tools in a
    row; the caller cannot tell from that whether it picked a bad index or the
    document simply has no tables, so it has no way to work out that add_table()
    is the next move. Non-empty output is unchanged: "(0-3)".
    """
    return f"(0-{total - 1})" if total > 0 else f"— this file has no {noun}"
