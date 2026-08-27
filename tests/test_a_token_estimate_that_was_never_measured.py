"""token_estimate was a literal, so it described nothing.

    read_document("/workspace/data/…/.mcp_versions/working_….docx.bak")

    -> "error": "Path '…' is inside .mcp_versions/. Snapshots are addressed by
                 timestamp, not by path: get_history lists them, and
                 restore_version and diff_versions take that timestamp …"
       "token_estimate": 15          the response is ~205

The 290-character refusal appears three times in the response -- once as
`error`, twice inside `progress[0]` -- and the estimate stayed 15 regardless.
161 literals in this repo, 588 across the fleet; MCP_Math is the only one that
computes it, in engine/formatter.py.

Under-reporting is the direction that hurts. A client budgets its context from
this number and admits the response on the strength of it, so an order-of-
magnitude undercount blows the 12,000-token budget these servers are designed
around. Error responses are the worst case, because their length is dominated
by a variable-length message: any constant is wrong by construction, and
*improving* a message by making it more specific silently makes the lie bigger.
That is exactly what happened -- the .mcp_versions hint above was lengthened in
6d481b4 to name the timestamp route, which made its own estimate worse.

Found once before, for one tool: add_chart's literal 40 got
`test_the_token_estimate_is_measured` in
test_a_wrong_argument_name_is_reported.py when its refusal hint grew. The other
587 sites kept their literals, which is why the fix here is a shared choke point
(`shared.token_estimate.measure_responses`) rather than a 588th hand-edit.

These assertions go through `mcp._tool_manager.call_tool`, the same converted
dispatch path a real client uses, because that is where the fix lives -- an
engine called directly still returns whatever literal it set.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))

SERVERS = {
    "docx_basic": ("read_document", {"file_path": "/nonexistent/x.docx"}),
    "docx_tables": ("list_tables", {"file_path": "/nonexistent/x.docx"}),
    "docx_layout": ("set_font", {"file_path": "/nonexistent/x.docx", "paragraph_index": 0, "font_name": "Arial"}),
    "docx_new": ("create_from_template", {"template_path": "/nonexistent/x.docx", "output_path": "/tmp/o.docx"}),
    "pptx_basic": ("read_presentation", {"file_path": "/nonexistent/x.pptx"}),
    "pptx_design": ("set_background", {"file_path": "/nonexistent/x.pptx", "slide_index": 0, "color": "FFFFFF"}),
    "pptx_new": ("create_from_outline", {"outline": "", "output_path": "/tmp/o.pptx"}),
    "xlsx_basic": ("list_sheets", {"file_path": "/nonexistent/x.xlsx"}),
    "xlsx_charts": ("delete_chart", {"file_path": "/nonexistent/x.xlsx", "sheet_name": "S", "chart_index": 0}),
    "xlsx_formulas": ("freeze_panes", {"file_path": "/nonexistent/x.xlsx", "sheet_name": "S", "cell": "B2"}),
    "xlsx_new": ("create_from_csv", {"csv_path": "/nonexistent/x.csv", "output_path": "/tmp/o.xlsx"}),
}


def _load(name: str):
    for root in (Path(__file__).resolve().parents[1] / "servers" / name,):
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    return importlib.import_module(f"{name}.server")


def call(server: str, tool: str, arguments: dict) -> dict:
    """Dispatch the way a client does, conversion included."""
    mod = _load(server)
    result = asyncio.run(mod.mcp._tool_manager.call_tool(tool, arguments, convert_result=True))
    assert result and hasattr(result[0], "text"), f"not renderable: {result!r}"
    return json.loads(result[0].text)


def measured(response: dict) -> int:
    """What the contract says the estimate should be for this response.

    token_estimate is removed before measuring, so the number describes the
    payload rather than partly describing itself. recount() sets the key last,
    so dropping it here leaves the remaining keys in the same order and str()
    renders the same bytes.
    """
    return len(str({k: v for k, v in response.items() if k != "token_estimate"})) // 4


class TestTheEstimateIsMeasuredNotTypedIn:
    @pytest.mark.parametrize("server", sorted(SERVERS))
    def test_every_server_measures_its_error_responses(self, server: str) -> None:
        tool, args = SERVERS[server]
        r = call(server, tool, args)
        assert r["token_estimate"] == measured(r), (
            f"{server}.{tool} reported {r['token_estimate']}, response measures {measured(r)}"
        )

    @pytest.mark.parametrize("server", sorted(SERVERS))
    def test_no_server_still_reports_a_stock_literal(self, server: str) -> None:
        """15, 20, 30 and 40 were the hardcoded values; 161 sites used them."""
        tool, args = SERVERS[server]
        r = call(server, tool, args)
        if r["token_estimate"] in (15, 20, 25, 30, 40):
            assert r["token_estimate"] == measured(r), (
                f"{server}.{tool} returned the stock literal {r['token_estimate']} "
                f"and the response measures {measured(r)}"
            )


class TestTheLongRefusalThatMadeThisVisible:
    """The .mcp_versions guard: one message, repeated three times, estimate 15."""

    def test_the_snapshot_path_refusal_is_measured(self, tmp_path: Path) -> None:
        bad = tmp_path / ".mcp_versions" / "working_2026-01-01T00-00-00-000000Z.docx.bak"
        r = call("docx_basic", "read_document", {"file_path": str(bad)})
        assert r["success"] is False
        assert ".mcp_versions" in r["error"]
        assert r["token_estimate"] == measured(r), r["token_estimate"]

    def test_it_is_far_above_the_literal_it_replaced(self, tmp_path: Path) -> None:
        """Guards the direction that matters: this response is nowhere near 15.

        Without this, a recount that returned some other small constant would
        satisfy the equality above just as well.
        """
        bad = tmp_path / ".mcp_versions" / "working_2026-01-01T00-00-00-000000Z.docx.bak"
        r = call("docx_basic", "read_document", {"file_path": str(bad)})
        assert r["token_estimate"] > 100, r["token_estimate"]


class TestRecountItself:
    def test_it_measures_without_counting_its_own_field(self) -> None:
        from shared.token_estimate import recount

        r = recount({"success": True, "note": "x" * 400, "token_estimate": 15})
        assert r["token_estimate"] == measured(r)
        assert r["token_estimate"] > 90

    def test_a_stale_literal_is_replaced_not_kept(self) -> None:
        from shared.token_estimate import recount

        assert recount({"a": 1, "token_estimate": 9999})["token_estimate"] != 9999

    def test_a_response_with_no_estimate_gets_one(self) -> None:
        from shared.token_estimate import recount

        assert "token_estimate" in recount({"success": True})

    def test_a_non_dict_is_left_alone(self) -> None:
        """The return contract is enforced elsewhere; this must not crash."""
        from shared.token_estimate import recount

        assert recount("not a dict") == "not a dict"
        assert recount(None) is None
