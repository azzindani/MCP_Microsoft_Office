"""A name a tool does not take must be refused, not quietly dropped.

These servers run on the FastMCP bundled in the `mcp` SDK, whose argument model
uses pydantic's default `extra="ignore"`. Sending a wholly invented argument to
one tool per server, against the live endpoints, before this fix:

    office-docx-basic   read_document        IGNORED, same answer as without it
    office-docx-tables  list_tables          IGNORED
    office-docx-layout  add_image            IGNORED
    office-pptx-basic   read_presentation    IGNORED
    office-xlsx-basic   list_sheets          IGNORED
    ml-basic            list_models          refused
    data-basic          list_patch_ops       refused

The two sibling repos, on standalone fastmcp 2.x, refuse. All 96 tools here
answered as if nothing were wrong -- which is worse than a refusal, because
there is no error anywhere to read and the answer looks like an answer.

It bites hardest where a name is genuinely easy to get wrong. add_chart takes
`anchor_cell`; add_pivot_table, in the same file, takes `dest_cell`. Five tools
size things with `width`; add_image takes `width_inches`. A caller who guesses
got a chart at the default position and no indication of why.

Both of those now accept either spelling, and every other unknown name is
refused with the accepted names listed.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path

import pytest
from mcp.types import CallToolResult

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SERVERS = [
    "docx_basic",
    "docx_layout",
    "docx_new",
    "docx_tables",
    "pptx_basic",
    "pptx_design",
    "pptx_new",
    "xlsx_basic",
    "xlsx_charts",
    "xlsx_formulas",
    "xlsx_new",
]


def load(name: str):
    pkg = ROOT / "servers" / name / name
    if str(pkg.parent) not in sys.path:
        sys.path.insert(0, str(pkg.parent))
    return importlib.import_module(f"{name}.server")


def call(server: str, tool: str, arguments: dict) -> dict:
    """Dispatch the way the server does, conversion included.

    Two layers are easy to test past. Calling the wrapper's `.fn` skips argument
    validation entirely. Calling `call_tool` with its default
    convert_result=False skips the result conversion -- where the first version
    of this refusal in a sibling repo broke, returning a JSON string that the
    SDK iterated one character at a time into 1900 validation errors. So every
    assertion here goes through the converted path and validates the content
    against CallToolResult, exactly as the protocol does.
    """
    mod = load(server)
    result = asyncio.run(mod.mcp._tool_manager.call_tool(tool, arguments, convert_result=True))
    CallToolResult(content=list(result))
    assert result and hasattr(result[0], "text"), f"not renderable content: {result!r}"
    return json.loads(result[0].text)


@pytest.fixture
def workbook(tmp_path):
    mod = load("xlsx_new")
    out = tmp_path / "book.xlsx"
    r = mod.engine.create_from_data(
        str(out),
        "Data",
        ["platform", "spend"],
        [["Google", 100], ["Meta", 50], ["Google", 70]],
    )
    assert r["success"] is True, r.get("error")
    return str(out)


class TestEveryServerReportsAnUnknownName:
    @pytest.mark.parametrize(
        "server,tool,args",
        [
            ("docx_basic", "read_document", {"file_path": "/tmp/none.docx"}),
            ("docx_layout", "set_font", {"file_path": "/tmp/none.docx", "paragraph_index": 0}),
            ("docx_new", "create_document", {"output_path": "/tmp/none.docx"}),
            ("docx_tables", "list_tables", {"file_path": "/tmp/none.docx"}),
            ("pptx_basic", "read_presentation", {"file_path": "/tmp/none.pptx"}),
            ("pptx_design", "export_pdf", {"file_path": "/tmp/none.pptx"}),
            ("pptx_new", "create_presentation", {"output_path": "/tmp/none.pptx"}),
            ("xlsx_basic", "list_sheets", {"file_path": "/tmp/none.xlsx"}),
            ("xlsx_charts", "delete_chart", {"file_path": "/tmp/none.xlsx", "sheet_name": "S", "chart_index": 0}),
            ("xlsx_formulas", "freeze_panes", {"file_path": "/tmp/none.xlsx", "sheet_name": "S"}),
            ("xlsx_new", "create_workbook", {"output_path": "/tmp/none.xlsx"}),
        ],
    )
    def test_an_invented_argument_does_not_pass_silently(self, server, tool, args):
        r = call(server, tool, {**args, "totally_invented_argument": 1})
        assert r["success"] is False
        assert "totally_invented_argument" in r["error"], r

    def test_the_refusal_lists_the_names_that_work(self):
        r = call("xlsx_basic", "list_sheets", {"file_path": "/tmp/none.xlsx", "bogus": 1})
        assert "file_path" in r["hint"], r["hint"]

    def test_a_near_miss_is_named(self):
        r = call("xlsx_basic", "list_sheets", {"file_pah": "/tmp/none.xlsx"})
        assert r["success"] is False
        assert "file_path" in r["hint"], r["hint"]

    def test_a_correct_call_is_untouched(self, workbook):
        r = call("xlsx_basic", "list_sheets", {"file_path": workbook})
        assert r["success"] is True, r.get("error")
        assert "Data" in json.dumps(r)


class TestThePlacementCellHasOneName:
    """add_chart says anchor_cell; add_pivot_table, same file, says dest_cell."""

    def test_add_chart_takes_dest_cell(self, workbook):
        r = call(
            "xlsx_charts",
            "add_chart",
            {
                "file_path": workbook,
                "sheet_name": "Data",
                "chart_type": "bar",
                "data_range": "A1:B4",
                "title": "Spend",
                "dest_cell": "D2",
            },
        )
        assert r["success"] is True, r.get("error")

    def test_add_chart_still_takes_anchor_cell(self, workbook):
        r = call(
            "xlsx_charts",
            "add_chart",
            {
                "file_path": workbook,
                "sheet_name": "Data",
                "chart_type": "bar",
                "data_range": "A1:B4",
                "title": "Spend",
                "anchor_cell": "D2",
            },
        )
        assert r["success"] is True, r.get("error")

    def test_add_pivot_table_takes_anchor_cell(self, workbook):
        r = call(
            "xlsx_charts",
            "add_pivot_table",
            {
                "file_path": workbook,
                "sheet_name": "Data",
                "source_range": "A1:B4",
                "rows": "platform",
                "values": "spend",
                "anchor_cell": "E2",
            },
        )
        assert r["success"] is True, r.get("error")

    def test_add_pivot_table_still_takes_dest_cell(self, workbook):
        r = call(
            "xlsx_charts",
            "add_pivot_table",
            {
                "file_path": workbook,
                "sheet_name": "Data",
                "source_range": "A1:B4",
                "rows": "platform",
                "values": "spend",
                "dest_cell": "E2",
            },
        )
        assert r["success"] is True, r.get("error")

    def test_neither_spelling_names_both(self, workbook):
        r = call(
            "xlsx_charts",
            "add_pivot_table",
            {
                "file_path": workbook,
                "sheet_name": "Data",
                "source_range": "A1:B4",
                "rows": "platform",
                "values": "spend",
            },
        )
        assert r["success"] is False
        assert "dest_cell" in r["hint"] and "anchor_cell" in r["hint"]


class TestTheImageWidthHasOneName:
    @pytest.fixture
    def document(self, tmp_path):
        mod = load("docx_new")
        out = tmp_path / "doc.docx"
        r = mod.engine.create_document(str(out))
        assert r["success"] is True, r.get("error")
        return str(out)

    @pytest.fixture
    def image(self, tmp_path):
        # a 1x1 PNG, enough for python-docx to embed
        import base64

        p = tmp_path / "dot.png"
        p.write_bytes(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
            )
        )
        return str(p)

    def test_width_is_accepted_and_used(self, document, image):
        r = call(
            "docx_layout",
            "add_image",
            {"file_path": document, "paragraph_index": 0, "image_path": image, "width": 2.5},
        )
        assert r["success"] is True, r.get("error")
        assert r["width_inches"] == 2.5, "width= was accepted and then ignored"

    def test_width_inches_still_works(self, document, image):
        r = call(
            "docx_layout",
            "add_image",
            {"file_path": document, "paragraph_index": 0, "image_path": image, "width_inches": 3.0},
        )
        assert r["success"] is True, r.get("error")
        assert r["width_inches"] == 3.0

    def test_the_documented_name_wins_when_both_are_given(self, document, image):
        # This test's name always said the documented name wins; its assertion
        # said 2.0, the alias. The engine read `if width: width_inches = width`,
        # so the fallback overwrote an explicit width_inches -- the opposite of
        # every other alias here. A caller who spells the documented name
        # correctly must not be overridden by the spelling kept for compatibility.
        r = call(
            "docx_layout",
            "add_image",
            {
                "file_path": document,
                "paragraph_index": 0,
                "image_path": image,
                "width_inches": 3.0,
                "width": 2.0,
            },
        )
        assert r["success"] is True, r.get("error")
        assert r["width_inches"] == 3.0

    def test_the_alias_still_applies_when_the_documented_name_is_absent(self, document, image):
        r = call(
            "docx_layout",
            "add_image",
            {"file_path": document, "paragraph_index": 0, "image_path": image, "width": 2.0},
        )
        assert r["success"] is True, r.get("error")
        assert r["width_inches"] == 2.0

    def test_the_default_still_applies_when_neither_is_given(self, document, image):
        r = call(
            "docx_layout",
            "add_image",
            {"file_path": document, "paragraph_index": 0, "image_path": image},
        )
        assert r["success"] is True, r.get("error")
        assert r["width_inches"] == 4.0


class TestTheRefusalSaysItOnce:
    """The refusal listed every accepted name twice and mis-stated its size.

    `hint` was built as `f"{hint} Accepted: {names}."` where `hint` had already
    spelled the same list out when there was no near-miss to suggest. Against
    the live endpoint, add_chart's refusal:

        add_chart accepts: anchor_cell, chart_type, data_range, dest_cell,
        file_path, height, sheet_name, title, width. Accepted: anchor_cell,
        chart_type, data_range, dest_cell, file_path, height, sheet_name,
        title, width.

    214 characters where 110 say the same thing. And `token_estimate` was the
    literal 40 whatever the response held -- under half the real size for a wide
    tool, on servers whose entire design is a 12,000-token client budget.
    """

    def test_the_accepted_names_appear_once(self):
        r = call("xlsx_charts", "add_chart", {"file_path": "/tmp/none.xlsx", "bogus": 1})
        names = "chart_type"
        assert r["hint"].count(names) == 1, r["hint"]

    def test_a_near_miss_still_names_the_alternatives(self):
        r = call("xlsx_charts", "add_chart", {"file_path": "/tmp/none.xlsx", "chart_typ": "bar"})
        assert "chart_type" in r["hint"], r["hint"]
        assert "Did you mean" in r["hint"], r["hint"]

    def test_the_token_estimate_is_measured(self):
        r = call("xlsx_charts", "add_chart", {"file_path": "/tmp/none.xlsx", "bogus": 1})
        assert r["token_estimate"] >= len(str(r)) // 8, r["token_estimate"]
        assert r["token_estimate"] != 40 or len(str(r)) // 4 == 40
