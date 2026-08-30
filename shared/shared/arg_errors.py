"""Answer a rejected ARGUMENT with the return contract, not a pydantic dump.

Every tool here promises the same failure shape: `success: False`, `op`,
`error`, `hint`, `token_estimate`. That promise held for everything the tool
body could raise -- and broke completely one step earlier. An argument of the
wrong *type* is rejected by pydantic before a single line of our code runs:

    fs_read(path=123)
      -> 1 validation error for call[fs_read]
         path
           Input should be a valid string [type=string_type, input_value=123, ...]
             For further information visit https://errors.pydantic.dev/2.12/v/string_type

No `success` to branch on, no `error`, no `hint` to act on, no
`token_estimate` to budget with -- and an external URL, in a fleet whose
founding constraint is that it works offline and nothing leaves the machine.

Confirmed on all four servers. `enforce_known_arguments` looks like it covers
this and does not: it catches an unknown argument NAME, while a known name with
the wrong type never reaches it. A guard that appears to cover a case it misses
is worse than no guard, because nobody looks again.

Round 18 could not see this at all. Its axis was "do what the hint told you to
do", and here there is no hint to follow -- the phase records a tool that failed
without advice and moves on. It was found by chasing a one-line aside in a
report ("also tried row_index='two', got validation error without hint").

Wrapping `call_tool` is the same choke point `enforce_known_arguments` uses, so
one install per server covers every tool it has, including any added later.

The two FastMCP flavours in this fleet differ in ways that matter here, which is
why the wrapper takes *args and inspects rather than declaring parameters:

    bundled mcp.server.fastmcp   call_tool(name, arguments, context, convert_result)
                                 raises ToolError wrapping the pydantic text
    fastmcp 2.x                  call_tool(key, arguments)
                                 raises pydantic ValidationError, returns ToolResult
"""

from __future__ import annotations

import difflib
import inspect
import re
from typing import Any

try:  # fastmcp 2.x returns a ToolResult; the bundled flavour returns a dict
    from fastmcp.tools.tool import ToolResult  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - depends which flavour is installed
    ToolResult = None  # type: ignore[assignment]

# The line that sends a caller to the internet to understand a local error.
_URL = re.compile(r"\s*For further information visit https?://\S+")
# "Input should be a valid string [type=string_type, input_value=123, input_type=int]"
_DETAIL = re.compile(r"^\s+(?P<why>.+?)\s*\[type=(?P<kind>[^,\]]+)(?:,[^\]]*input_type=(?P<got>[^,\]]+))?[^\]]*\]\s*$")


def _clean(message: str) -> str:
    return _URL.sub("", message).strip()


def looks_like_validation(message: str) -> bool:
    """True for pydantic's argument rejection, in either flavour's wrapping."""
    return "validation error" in message.lower()


def explain(message: str) -> list[tuple[str, str]]:
    """Return [(field, why)] read out of a pydantic validation message.

    The shape is stable across both flavours: a header line, then for each
    problem a bare field name on its own line and an indented detail line.
    Anything unparseable is skipped rather than guessed at -- a wrong field
    name in a hint is the defect this module exists to stop.
    """
    out: list[tuple[str, str]] = []
    field: str | None = None
    for line in _clean(message).splitlines():
        if not line.strip():
            continue
        if not line.startswith(" ") and "validation error" not in line.lower():
            field = line.strip()
            continue
        m = _DETAIL.match(line)
        if m and field:
            why = m.group("why")
            got = m.group("got")
            # "Field required" reports input_type=dict -- the whole argument
            # object, not the missing value -- so naming a type there says
            # something false about an argument that was never passed.
            if got and "missing" not in m.group("kind") and "unexpected" not in m.group("kind"):
                why = f"{why} (got {got})"
            out.append((field, why))
            field = None
    return out


def _refusal(name: str, known: list[str], message: str) -> dict[str, Any]:
    problems = explain(message)
    if problems:
        error = f"{name} rejected an argument: " + "; ".join(f"{f}: {w}" for f, w in problems)
    else:
        # Never invent a field name. If the message did not parse, pass it
        # through cleaned -- minus the URL, which is the one part that is
        # actively wrong for an offline server to emit.
        error = f"{name} rejected an argument: {_clean(message)}"

    bad = [f for f, _ in problems]
    # The two FastMCP flavours word the same two problems differently, so match
    # both vocabularies rather than one: the bundled one says "Field required"
    # and never mentions the stray key, while fastmcp 2.x reports "Missing
    # required argument" AND "Unexpected keyword argument" together.
    missing = [f for f, w in problems if w.startswith(("Field required", "Missing required argument"))]
    unexpected = [f for f, w in problems if w.startswith("Unexpected keyword argument")]
    unknown = unexpected or [f for f in bad if known and f not in known]
    if unknown and known:
        near = difflib.get_close_matches(unknown[0], known, n=1, cutoff=0.6)
        lead = f"Did you mean {near[0]}=? " if near else ""
        hint = f"{lead}{name} accepts: {', '.join(known)}."
    elif missing:
        # A missing argument is not a wrong one: telling the caller to correct
        # a type they never supplied sends them to look at the wrong thing, and
        # a hint naming a specific wrong fix is worse than a vague one.
        others = f" {name} accepts: {', '.join(known)}." if known else ""
        hint = f"{', '.join(missing)} is required.{others}"
    elif bad:
        # A bool rejected where a string is expected is, in this fleet, a
        # THREE-STATE flag: bold and italic are spelled "true" / "false" / ""
        # precisely so that "turn it off" can be said at all, which a plain
        # bool cannot express (False is indistinguishable from unset). Naming
        # the quoted form turns a refusal into a working call; "correct the
        # type" leaves the caller guessing which type.
        quoted = [f for f, w in problems if "valid string" in w and "bool" in w]
        if quoted:
            field = quoted[0]
            hint = (
                f"Pass {field} as a quoted string: {field}='true' to turn it on, "
                f"{field}='false' to turn it off, or leave it out to keep the current value. "
                "Nothing was written."
            )
        else:
            hint = f"Correct the type of {', '.join(bad)} and call again. Nothing was written."
    elif known:
        hint = f"{name} accepts: {', '.join(known)}."
    else:
        hint = "Check the argument names and types against the tool's schema."

    refusal: dict[str, Any] = {
        "success": False,
        "op": name,
        "error": error,
        "hint": hint,
        "progress": [],
    }
    # Measured, never a literal: a client budgets its context from this and
    # admits the response on the strength of it.
    refusal["token_estimate"] = len(str(refusal)) // 4
    return refusal


def contract_errors(mcp: Any) -> None:
    """Make argument rejection return this fleet's failure dict on every tool."""
    manager = mcp._tool_manager
    original = manager.call_tool
    if getattr(original, "__contract_errors__", False):
        return

    async def call_tool(*a: Any, **kw: Any) -> Any:
        try:
            return await original(*a, **kw)
        except Exception as exc:
            message = str(exc)
            if not looks_like_validation(message):
                raise
            name = kw.get("name") or kw.get("key") or (a[0] if a else "tool")
            # The registry dict, not get_tool(): on fastmcp 2.x get_tool is a
            # COROUTINE function, so calling it from here returned an
            # un-awaited coroutine -- no parameters, an empty hint, and a
            # RuntimeWarning. Both flavours keep `_tools`, and it is sync.
            tool = None
            try:
                tool = getattr(manager, "_tools", {}).get(name)
            except Exception:
                pass
            if tool is None:
                getter = getattr(manager, "get_tool", None)
                if getter is not None and not inspect.iscoroutinefunction(getter):
                    try:
                        tool = getter(name)
                    except Exception:
                        pass
            known = sorted((getattr(tool, "parameters", None) or {}).get("properties", {})) if tool else []
            refusal = _refusal(str(name), known, message)

            if ToolResult is not None:
                return ToolResult(structured_content=refusal)
            convert = kw.get("convert_result", a[3] if len(a) > 3 else False)
            if convert and tool is not None:
                # Returning a raw dict where the server asked for the converted
                # form gives a response no client can read -- and returning a
                # JSON *string* is worse: the SDK iterates it one character at a
                # time into ~1900 validation errors.
                return tool.fn_metadata.convert_result(refusal)
            return refusal

    call_tool.__contract_errors__ = True  # type: ignore[attr-defined]
    manager.call_tool = call_tool
