"""A missing file is answered with the nearest files that exist.

"File not found: /workspace/data/q3_report.docx" left a remote caller to guess
again: it shares no filesystem with the server and cannot look. The file it
meant, one case-fold or one extension away, was visible only to the server.

Asserted through the registered tools of every tier, since every tier reports
a missing file, and asserted never to name anything outside the served folders.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from docx import Document

from shared.missing_file import suggest  # type: ignore[reportMissingImports]

TIERS = [
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


def _server(tier: str):
    return importlib.import_module(f"servers.{tier}.{tier}.server")


@pytest.fixture
def served(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "drafts").mkdir(parents=True)
    monkeypatch.setenv("MCP_CONFINE_PATHS", "1")
    monkeypatch.setenv("MCP_OUTPUT_DIR", str(data))
    monkeypatch.setenv("MCP_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.delenv("MCP_DATA_ROOT", raising=False)
    monkeypatch.delenv("MCP_ALLOWED_ROOTS", raising=False)
    Document().save(str(data / "Q3_Report.docx"))
    Document().save(str(data / "drafts" / "budget_2023.docx"))
    (data / ".hidden.docx").write_bytes(b"")
    return data


def _outline(file_path: str) -> dict:
    return _server("docx_basic").mcp._tool_manager._tools["get_document_outline"].fn(file_path=file_path)


class TestThroughTheTool:
    def test_a_case_fold_away_is_named_first(self, served):
        if (served / "q3_report.docx").exists():
            pytest.skip("case-insensitive filesystem: the file is found, nothing to suggest")
        r = _outline("q3_report.docx")
        assert r["success"] is False
        assert r["did_you_mean"][0] == "Q3_Report.docx"
        assert "Q3_Report.docx" in r["hint"]

    def test_a_misremembered_extension_finds_the_real_one(self, served):
        r = _outline("Q3_Report.doc")
        assert r["did_you_mean"][0] == "Q3_Report.docx"

    def test_a_file_in_a_subfolder_is_named_by_the_path_to_pass(self, served):
        r = _outline("budget_2024.docx")
        assert str(Path("drafts") / "budget_2023.docx") in r["did_you_mean"]

    def test_nothing_close_lists_what_the_folder_holds(self, served):
        r = _outline("zzqx.docx")
        assert "did_you_mean" not in r
        assert "Q3_Report.docx" in r["hint"]
        assert ".hidden.docx" not in r["hint"]

    @pytest.mark.parametrize("tier", TIERS)
    def test_every_tier_installs_it(self, tier):
        tools = _server(tier).mcp._tool_manager._tools.values()
        assert tools
        assert all(getattr(t.fn, "__suggests_missing_files__", False) for t in tools)


class TestNeverOutside:
    def test_a_folder_outside_the_served_ones_is_never_listed(self, served, tmp_path):
        outside = tmp_path / "private"
        outside.mkdir()
        (outside / "salaries.docx").write_bytes(b"")
        r = suggest(
            {"success": False, "error": f"File not found: {outside / 'salary.docx'}", "hint": "h"},
            {"file_path": str(outside / "salary.docx")},
        )
        assert "salaries.docx" not in str(r)


class TestLeftAlone:
    @pytest.mark.parametrize(
        "result",
        [
            {"success": True, "error": "File not found: a.docx"},
            {"success": False, "error": "Sheet not found: 'Q3'"},
        ],
    )
    def test_only_a_missing_file_is_touched(self, served, result):
        assert suggest(dict(result), {"file_path": "Q3_Report.docx"}) == result
