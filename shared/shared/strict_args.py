"""Refuse an argument a tool does not take, instead of ignoring it.

These eleven servers run on the FastMCP bundled in the `mcp` SDK, which builds
each tool's argument model with pydantic's default `extra="ignore"`. Sending a
wholly invented argument to a tool on every server, against the live endpoints:

    office-docx-basic   read_document        IGNORED, same answer as without it
    office-docx-tables  list_tables          IGNORED
    office-docx-layout  add_image            IGNORED
    office-pptx-basic   read_presentation    IGNORED
    office-xlsx-basic   list_sheets          IGNORED
    ml-basic            list_models          refused
    data-basic          list_patch_ops       refused

The two sibling repos on standalone fastmcp 2.x answer "Unexpected keyword
argument". All 96 tools here answered as if nothing were wrong. That matters
most where a name is easy to get wrong: add_chart takes `anchor_cell` and
add_pivot_table, 47 lines below it in the same file, takes `dest_cell`; five
tools size things with `width` and add_image uses `width_inches`. A caller who
guesses gets a chart at the default position and no indication.

`enforce_known_arguments(mcp)` checks argument names against the tool's own
schema before dispatch. The refusal *lists the names the tool accepts*, so a
caller can fix the call from the response rather than guessing again.

Applied once per server at start; no tool body changes.
"""

from __future__ import annotations

from typing import Any


def _did_you_mean(unknown: str, known: list[str]) -> str:
    """The closest accepted name, when one is obviously close."""
    import difflib

    # Underscore-insensitive first: type/type_ and format/format_ are the real
    # cases here and difflib alone rates them no higher than unrelated names.
    stripped = {k.rstrip("_"): k for k in known}
    if unknown.rstrip("_") in stripped:
        return stripped[unknown.rstrip("_")]
    close = difflib.get_close_matches(unknown, known, n=1, cutoff=0.75)
    return close[0] if close else ""


def enforce_known_arguments(mcp: Any) -> None:
    """Make every tool on this server refuse an argument it does not declare."""
    manager = mcp._tool_manager
    original = manager.call_tool

    async def call_tool(
        name: str,
        arguments: dict[str, Any],
        context: Any = None,
        convert_result: bool = False,
    ) -> Any:
        tool = manager.get_tool(name)
        if tool is not None and isinstance(arguments, dict):
            known = sorted((tool.parameters or {}).get("properties", {}))
            unknown = [k for k in arguments if k not in known]
            if unknown and known:
                first = unknown[0]
                suggestion = _did_you_mean(first, known)
                hint = f"Did you mean {suggestion}=?" if suggestion else f"{name} accepts: {', '.join(known)}."
                refusal = {
                    "success": False,
                    "op": name,
                    "error": f"{name} does not take {', '.join(unknown)}",
                    "hint": f"{hint} Accepted: {', '.join(known)}.",
                    "progress": [],
                    "token_estimate": 40,
                }
                # The server asks for the converted form. Returning the raw dict
                # -- or worse a JSON string, which the SDK then iterates one
                # character at a time into 1900 validation errors -- produces a
                # response no client can read. Convert it exactly as this tool's
                # own return value would have been.
                if convert_result:
                    return tool.fn_metadata.convert_result(refusal)
                return refusal
        return await original(name, arguments, context, convert_result)

    manager.call_tool = call_tool
