"""Report what a response actually costs, instead of a number typed in by hand.

Every tool returns `token_estimate`, and STANDARDS defines it as
`len(str(response)) // 4`. Across this repo it was a literal instead: 161
occurrences of `"token_estimate": 15` and friends, none of them measured.

    read_document("…/.mcp_versions/working_….docx.bak")
        -> a 290-character refusal, repeated three times across
           error / progress[0].msg / progress[0].message
        -> "token_estimate": 15        the response is ~205

Under-reporting is the harmful direction. A client budgets its context from
this number and *admits* the response on the strength of it, so a fleet that
under-reports by an order of magnitude blows the 12,000-token budget these
servers are designed around. Error responses are the worst case: their length
is dominated by a variable-length message, so any constant is wrong by
construction -- and lengthening a message, which is usually an improvement,
silently makes the lie bigger.

Found once before and fixed for a single tool. `add_chart`'s literal 40 got a
test (`test_the_token_estimate_is_measured`) after its argument-refusal hint
grew; the other 587 sites across the fleet kept their literals. Hence a shared
choke point rather than a 588th hand-edit: measuring at the boundary cannot
drift out of step with the response the way a literal does.

`measure_responses(mcp)` is applied once per server at start, beside
`enforce_known_arguments(mcp)`, and changes no tool body. It wraps the tools the
manager has already registered rather than the `@mcp.tool` decorator, so it does
not care whether it runs above or below the tool declarations -- a decorator
wrapper would have to precede every one of them, and would silently miss any
tool added above the call.

Engines called directly -- as most unit tests do -- keep whatever literal the
engine set. That is deliberate: the contract is about what a *client* receives,
and the MCP dispatch path is where a client receives it. Tests that want to
assert the measured value must go through `mcp._tool_manager.call_tool`, which
is the path `tests/test_a_wrong_argument_name_is_reported.py::call` already
uses for exactly this reason.
"""

from __future__ import annotations

import functools
from typing import Any


def recount(response: Any) -> Any:
    """Set `token_estimate` to the measured size of the response carrying it.

    The field is removed before measuring so the number describes the payload
    rather than partly describing itself; a four-digit estimate would otherwise
    count its own digits. Non-dict returns pass through untouched -- the return
    contract says every tool returns a dict, and this is not the place to
    enforce that.
    """
    if not isinstance(response, dict):
        return response
    response.pop("token_estimate", None)
    response["token_estimate"] = len(str(response)) // 4
    return response


def measure_responses(mcp: Any) -> None:
    """Measure `token_estimate` on every tool this server has registered.

    `Tool.run` dispatches through `self.fn`, and the schema was built from the
    original at registration time, so replacing `fn` afterwards changes what the
    tool returns without touching how it is described. `is_async` is recorded on
    the Tool rather than re-derived, so a sync wrapper stays sync.
    """
    for tool in mcp._tool_manager._tools.values():
        tool.fn = _measured(tool.fn)


def _measured(fn: Any) -> Any:
    # functools.wraps carries __name__, __doc__ and __annotations__ over and
    # sets __wrapped__ so inspect.signature follows through to the original --
    # which matters because the SDK validates arguments against that signature
    # on every call, not only at registration.
    @functools.wraps(fn)
    def measured(*a: Any, **kw: Any) -> Any:
        return recount(fn(*a, **kw))

    return measured
