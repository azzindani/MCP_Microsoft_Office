"""Regression tests against real deliverables produced during the 2026-08-12
real-world tool sweeps — genuine Word/PowerPoint/Excel output built from real
analysis of the Ad_Data.csv dataset, not fabricated content. Committing them
as fixtures means the real content these tools produced stays verifiable
instead of only having existed in a manual session transcript.
See project memory: project_real_world_report_test_2026-08-12,
project_full_tool_sweep_2026-08-12.
"""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


class TestAdCampaignPerformanceReport:
    """Real 15-page Word report analyzing the full Ad_Data.csv dataset."""

    def test_has_real_section_headings(self):
        from docx_basic.engine import get_document_outline

        path = FIXTURES / "ad_campaign_performance_report.docx"
        result = get_document_outline(str(path))
        assert result["success"] is True
        headings = [h["text"] for h in result["outline"]]
        assert "Executive Summary" in headings
        assert "Data Quality Issues Found" in headings
        assert "Correlation & Regression Analysis" in headings

    def test_has_real_data_tables(self):
        from docx_tables.engine import list_tables

        path = FIXTURES / "ad_campaign_performance_report.docx"
        result = list_tables(str(path))
        assert result["success"] is True
        assert len(result["tables"]) == 15

    def test_documents_the_real_facebook_device_defect(self):
        from docx_basic.engine import search_paragraphs

        path = FIXTURES / "ad_campaign_performance_report.docx"
        result = search_paragraphs(str(path), "1,733")
        assert result["success"] is True
        assert len(result["matches"]) > 0


class TestAdCampaignPerformanceDeck:
    """Real 15-slide deck built from the same analysis as the Word report."""

    def test_has_real_slide_count(self):
        from pptx_basic.engine import read_presentation

        path = FIXTURES / "ad_campaign_performance_deck.pptx"
        result = read_presentation(str(path))
        assert result["success"] is True
        assert result["slide_count"] == 15

    def test_key_metrics_slide_has_real_figures(self):
        from pptx_basic.engine import read_slide_text

        path = FIXTURES / "ad_campaign_performance_deck.pptx"
        result = read_slide_text(str(path), 1)
        assert result["success"] is True
        full_text = " ".join(shape["text"] for shape in result["shapes"])
        assert "2,503,118.77" in full_text


class TestMlAnalyticsAddendum:
    """Real Word addendum covering classification/regression/clustering
    results and the 3 real engine bugs found during the ML sweep."""

    def test_has_real_section_headings(self):
        from docx_basic.engine import get_document_outline

        path = FIXTURES / "ml_analytics_addendum.docx"
        result = get_document_outline(str(path))
        assert result["success"] is True
        headings = [h["text"] for h in result["outline"]]
        assert any("Classification" in h for h in headings)
        assert any("bugs found" in h.lower() for h in headings)

    def test_documents_the_data_leakage_caveat(self):
        from docx_basic.engine import search_paragraphs

        path = FIXTURES / "ml_analytics_addendum.docx"
        result = search_paragraphs(str(path), "data leakage")
        assert result["success"] is True
        assert len(result["matches"]) > 0


class TestMlFindingsAddendum:
    """Real 6-slide executive summary deck for the ML findings."""

    def test_has_real_slide_count(self):
        from pptx_basic.engine import read_presentation

        path = FIXTURES / "ml_findings_addendum.pptx"
        result = read_presentation(str(path))
        assert result["success"] is True
        assert result["slide_count"] == 6


class TestMlAnalyticsWorkbook:
    """Real 5-sheet Excel workbook with genuine formulas, a chart, a named
    range, freeze panes, and autofilter — not a synthetic smoke-test file."""

    def test_has_real_sheets(self):
        from xlsx_basic.engine import list_sheets

        path = FIXTURES / "ml_analytics_workbook.xlsx"
        result = list_sheets(str(path))
        assert result["success"] is True
        names = [s["name"] for s in result["sheets"]]
        assert names == ["Cover", "Model_Comparison", "Feature_Importance", "Clustering", "Math_Formulas"]

    def test_has_real_formulas(self):
        from xlsx_basic.engine import read_cell

        path = FIXTURES / "ml_analytics_workbook.xlsx"
        avg_cell = read_cell(str(path), "Model_Comparison", "D11")
        assert avg_cell["success"] is True
        assert avg_cell["formula"] == "=AVERAGE(D6:D8)"

        sum_cell = read_cell(str(path), "Feature_Importance", "B12")
        assert sum_cell["success"] is True
        assert sum_cell["formula"] == "=SUM(B2:B11)"


class TestAdDataFullAnalysis:
    """Real full-dataset (16,834-row) Excel workbook: Raw Data, a native
    Excel PivotTable, and a Dashboard — built live against the running
    mcp-office container in the same session that fixed the create_from_csv
    numeric-coercion bug this fixture exercises."""

    def test_raw_data_has_all_real_rows(self):
        from xlsx_basic.engine import get_sheet_summary

        path = FIXTURES / "ad_data_full_analysis.xlsx"
        result = get_sheet_summary(str(path), "Raw Data")
        assert result["success"] is True
        assert result["dimensions"]["rows"] == 16835  # header + 16,834 data rows

    def test_raw_data_numeric_columns_are_real_numbers(self):
        """Regression guard for the create_from_csv text-coercion bug: a
        spend cell must read back as a number, not the string '0'."""
        from xlsx_basic.engine import read_cell

        path = FIXTURES / "ad_data_full_analysis.xlsx"
        result = read_cell(str(path), "Raw Data", "M5")
        assert result["success"] is True
        assert isinstance(result["value"], (int, float))

    def test_pivot_summary_has_real_nonzero_totals(self):
        """Regression guard for the add_pivot_table-surfaced bug: at least
        one platform x device spend total must be nonzero."""
        from xlsx_basic.engine import read_cell_range

        path = FIXTURES / "ad_data_full_analysis.xlsx"
        result = read_cell_range(str(path), "Pivot Summary", "B2:D3")
        assert result["success"] is True
        values = [cell["value"] for row in result["data"] for cell in row]
        assert any(isinstance(v, (int, float)) and v > 0 for v in values)

    def test_dashboard_has_kpi_formulas(self):
        from xlsx_basic.engine import read_cell

        path = FIXTURES / "ad_data_full_analysis.xlsx"
        total_spend = read_cell(str(path), "Dashboard", "B2")
        assert total_spend["success"] is True
        assert total_spend["formula"] == "=SUM('Raw Data'!M2:M16835)"
