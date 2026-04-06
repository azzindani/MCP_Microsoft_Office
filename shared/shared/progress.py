"""Progress step helpers for tool response 'progress' arrays."""

from typing import Any


def step(icon: str, msg: str, detail: str = "") -> dict[str, Any]:
    """Create a single progress step dict."""
    entry: dict[str, Any] = {"icon": icon, "msg": msg}
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
    """
    Format a progress list as a human-readable string.

    Suitable for returning in a tool response for the model to narrate.
    """
    lines = []
    for s in steps:
        line = f"{s['icon']} {s['msg']}"
        if s.get("detail"):
            line += f" ({s['detail']})"
        lines.append(line)
    return "\n".join(lines)
