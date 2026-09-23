"""Every answer names its op: `success`, `op` and `token_estimate`, from every tool.

A sweep census over 362 logged calls found 25 tools answering at least once
without `op` -- some read tools even on success, and mostly failures built by
helpers that leave it out. A caller that dispatches on `op` could not. The op is
now filled at the one wrapper every tool already passes through
(shared/token_estimate.measure_responses), from the tool's own name; an answer
that already names an op keeps it.
"""

from __future__ import annotations

import asyncio

import pytest

import unified_server  # type: ignore[reportMissingImports]
from shared.token_estimate import with_op  # type: ignore[reportMissingImports]

TOOLS = [
    pytest.param(tool, id=f"{tier}/{tool.name}")
    for tier, server in unified_server._SUB_SERVERS.items()
    for tool in server._tool_manager._tools.values()
]


def test_the_census_finds_the_tools():
    assert len(TOOLS) >= 90


@pytest.mark.parametrize("tool", TOOLS)
def test_every_tool_is_wrapped_to_name_its_op(tool):
    if tool.is_async:
        pytest.skip("an async tool builds its own answer, op included")
    assert getattr(tool.fn, "__op_name__", None) == tool.name


def test_a_failure_answers_with_its_op():
    tier, name, args = ("docx-basic", "read_document", {"file_path": "no_such_file.docx"})
    manager = unified_server._SUB_SERVERS[tier]._tool_manager
    result = asyncio.run(manager.call_tool(name, args, convert_result=False))
    assert result["success"] is False and result["op"] == name


class TestWithOp:
    def test_a_missing_op_is_filled_after_success(self):
        answer = with_op({"success": False, "error": "x", "hint": "y"}, "some_tool")
        assert list(answer) == ["success", "op", "error", "hint"] and answer["op"] == "some_tool"

    def test_an_op_already_named_is_kept(self):
        assert with_op({"success": True, "op": "other"}, "some_tool")["op"] == "other"

    def test_anything_but_a_dict_passes_through(self):
        assert with_op(["a"], "some_tool") == ["a"]
