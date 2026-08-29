"""A wrong-typed argument escaped the return contract entirely.

    fs_read(path=123)
      -> 1 validation error for call[fs_read]
         path
           Input should be a valid string [type=string_type, input_value=123, ...]
             For further information visit https://errors.pydantic.dev/2.12/v/string_type

No `success` to branch on, no `error`, no `hint` to act on, no `token_estimate`
to budget with -- and an external URL, from a fleet whose founding constraint is
that it works offline and nothing leaves the machine. Reproduced on all four
servers before the fix.

The near-miss that makes it worth a test rather than a patch:
`enforce_known_arguments` looks like it already covers this. It catches an
unknown argument NAME; a *known* name with the wrong type is rejected by
pydantic one step earlier and never reaches it. A guard that appears to cover a
case it misses is worse than no guard.

Round 18's sweep could not see this. Its axis was "do what the hint told you to
do", and here there is no hint to follow -- the phase records a tool that failed
without advice and moves on. It surfaced from a one-line aside in a report:
"also tried row_index='two' (string) first, got validation error without hint".

The tests below run against a throwaway FastMCP server rather than the real
tools, so they hold whichever flavour the repo installs and cannot drift when a
tool's signature changes.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shared.arg_errors import contract_errors, explain, looks_like_validation  # noqa: E402

PYDANTIC_MESSAGE = (
    "1 validation error for call[fs_read]\n"
    "path\n"
    "  Input should be a valid string [type=string_type, input_value=123, input_type=int]\n"
    "    For further information visit https://errors.pydantic.dev/2.12/v/string_type"
)


def _payload(result):
    """The tool's dict, whichever shape this FastMCP flavour returns it in."""
    if isinstance(result, dict):
        return result
    sc = getattr(result, "structured_content", None)
    if isinstance(sc, dict):
        return sc
    content = getattr(result, "content", None)
    if content:
        return json.loads(content[0].text)
    raise AssertionError(f"cannot read a payload out of {result!r}")


@pytest.fixture
def server():
    try:
        from fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError:
        from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("probe")

    @mcp.tool()
    def echo(text: str, count: int = 1) -> dict:
        return {"success": True, "op": "echo", "text": text * count, "token_estimate": 5}

    contract_errors(mcp)
    return mcp


def call(mcp, name, args):
    return asyncio.run(mcp._tool_manager.call_tool(name, args))


class TestTheMessageParser:
    def test_it_recognises_a_validation_message(self):
        assert looks_like_validation(PYDANTIC_MESSAGE)
        assert looks_like_validation("Error executing tool t: 1 validation error for tArguments\nx\n  bad")

    def test_it_ignores_anything_else(self):
        assert not looks_like_validation("KeyError: 'spends'")

    def test_it_names_the_field_and_why(self):
        assert explain(PYDANTIC_MESSAGE) == [("path", "Input should be a valid string (got int)")]

    def test_it_invents_nothing_when_it_cannot_parse(self):
        # A wrong field name in a hint is the defect this module exists to stop.
        assert explain("1 validation error for call[x]\nnothing parseable here") == []


class TestTheContract:
    def test_a_wrong_type_returns_the_failure_dict(self, server):
        p = _payload(call(server, "echo", {"text": 123}))
        assert p["success"] is False
        assert p["op"] == "echo"
        assert p["error"]
        assert p["hint"]
        assert isinstance(p["token_estimate"], int) and p["token_estimate"] > 0

    def test_it_names_the_offending_argument(self, server):
        p = _payload(call(server, "echo", {"text": 123}))
        assert "text" in p["error"]

    def test_it_does_not_send_the_caller_to_the_internet(self, server):
        # The whole fleet is offline by construction; a pydantic.dev link is
        # the one part of that dump that is actively wrong to emit.
        p = _payload(call(server, "echo", {"text": 123}))
        assert "http" not in json.dumps(p), p

    def test_the_hint_says_what_to_do(self, server):
        p = _payload(call(server, "echo", {"text": 123}))
        assert "type" in p["hint"].lower() or "accepts" in p["hint"].lower()

    def test_a_missing_argument_is_told_it_is_missing(self, server):
        # A typo'd name reaches pydantic as a MISSING required field -- it
        # reports that and ignores the stray key entirely. So the honest answer
        # names what is required and lists what the tool takes; telling the
        # caller to fix a type they never passed points at the wrong thing.
        p = _payload(call(server, "echo", {"txet": "x"}))
        assert p["success"] is False
        # The flavours see different amounts here and each gives the best
        # answer it can: fastmcp 2.x is told about the stray key and can
        # suggest the near match, the bundled one only learns that `text` is
        # absent. Both are correct; neither may talk about a wrong type.
        assert ("text is required" in p["hint"]) or ("Did you mean text=?" in p["hint"]), p["hint"]
        assert "accepts" in p["hint"], p["hint"]
        assert "Correct the type" not in p["hint"], p["hint"]

    def test_a_missing_argument_does_not_claim_a_type(self, server):
        # pydantic reports input_type=dict there -- the whole argument object,
        # not the absent value -- and repeating it says something false.
        p = _payload(call(server, "echo", {"txet": "x"}))
        assert "got dict" not in p["error"], p["error"]

    def test_a_second_bad_argument_is_reported_too(self, server):
        p = _payload(call(server, "echo", {"text": 1, "count": "many"}))
        assert "text" in p["error"] and "count" in p["error"]

    def test_a_valid_call_is_untouched(self, server):
        p = _payload(call(server, "echo", {"text": "ab", "count": 2}))
        assert p["success"] is True
        assert p["text"] == "abab"

    def test_installing_twice_does_not_double_wrap(self, server):
        contract_errors(server)
        p = _payload(call(server, "echo", {"text": 123}))
        assert p["success"] is False

    def test_a_real_error_from_the_tool_body_still_propagates(self):
        # The wrapper must only claim validation failures. A tool that raises
        # for its own reasons has to keep reaching the server's error handling.
        try:
            from fastmcp import FastMCP  # type: ignore[import-not-found]
        except ImportError:
            from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("boom")

        @mcp.tool()
        def boom(x: str) -> dict:
            raise RuntimeError("the tool itself failed")

        contract_errors(mcp)
        with pytest.raises(Exception) as e:
            call(mcp, "boom", {"x": "ok"})
        assert "the tool itself failed" in str(e.value)
