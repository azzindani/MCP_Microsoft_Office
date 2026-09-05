"""The board paper carries risks, actions, links and a brand.

The user review's verdict on the executive summary it read:

    `Credit_Risk_Executive_Summary.docx` (37 KB, 7 paras) -- CORRECT BUT POOR
    Fetched section 1: H1 + 3xH2 + 3 Normal. Numbers match. No tables, KPIs,
    chart refs.
    AGI: KPI table + findings table + risks table + checklist; embed thumbnails
    or `public_url` links to the HTML charts; add `image` block support.

KPI tables, findings tables and image blocks shipped earlier. The three that did
not are here, plus the brand tokens from the same review's ask list.

**A link has to be a link.** The paper "references charts that live in separate
HTML files", and blue underlined text that does nothing when clicked would be a
worse answer than the bare URL it replaced. These tests read the .docx as a zip
and check for a real `w:hyperlink` with an external relationship behind it,
because that is the difference and it is invisible from the response.

**A risk is never lost to a spelling.** An unrecognised severity is written
through uncoloured and reported, not dropped. A risk register that silently
discards the row someone typed "critical" into is worse than one with a
mis-coloured cell.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from servers.docx_new.docx_new import engine
from servers.docx_new.docx_new.engine import BLOCK_KINDS, RISK_LEVELS

pytest.importorskip("docx")


def xml_of(path: Path, member: str = "word/document.xml") -> str:
    with zipfile.ZipFile(path) as book:
        return book.read(member).decode("utf-8")


def external_targets(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as book:
        rels = book.read("word/_rels/document.xml.rels").decode("utf-8")
    return re.findall(r'Target="([^"]+)" TargetMode="External"', rels)


def build(tmp_path: Path, blocks: list[dict], **kwargs):
    out = tmp_path / "brief.docx"
    result = engine.create_from_blocks(str(out), "Credit Risk", blocks, open_after=False, **kwargs)
    assert result["success"] is True, result.get("error")
    return result, out


class TestTheNewKindsAreReachable:
    @pytest.mark.parametrize("kind", ["links", "risks", "checklist"])
    def test_the_kind_is_declared(self, kind):
        assert kind in BLOCK_KINDS

    @pytest.mark.parametrize("kind", ["links", "risks", "checklist"])
    def test_the_tool_forwards_the_brand_arguments(self, kind):
        """A kind the validator knows and the renderer cannot draw is a dead op."""
        import inspect

        from servers.docx_new.docx_new import server

        params = inspect.signature(server.create_from_blocks).parameters
        assert "font" in params and "heading_font" in params

    def test_every_declared_kind_is_rendered_by_the_engine(self):
        """The census the review asked for: validator, renderer, description agree."""
        source = Path(engine.__file__).read_text(encoding="utf-8")
        for kind in BLOCK_KINDS:
            assert f'kind == "{kind}"' in source, f"{kind} is a declared kind nothing draws"


class TestTheChartsAreLinked:
    @pytest.fixture()
    def paper(self, tmp_path):
        return build(
            tmp_path,
            [
                {
                    "kind": "links",
                    "title": "Charts",
                    "items": [
                        {
                            "label": "Correlation heatmap",
                            "url": "https://files.example.test/Credit_Risk_correlation.html",
                            "note": "24x24",
                        },
                        {"url": "https://files.example.test/Credit_Risk_dashboard.html"},
                    ],
                }
            ],
        )

    def test_the_response_counts_them(self, paper):
        result, _out = paper
        assert result["links_embedded"] == 2

    def test_they_are_real_hyperlink_elements(self, paper):
        _result, out = paper
        assert xml_of(out).count("<w:hyperlink") == 2

    def test_each_one_has_an_external_relationship_behind_it(self, paper):
        """Without this the text is blue and does nothing when clicked."""
        _result, out = paper
        assert external_targets(out) == [
            "https://files.example.test/Credit_Risk_correlation.html",
            "https://files.example.test/Credit_Risk_dashboard.html",
        ]

    def test_the_label_is_shown_and_the_note_beside_it(self, paper):
        _result, out = paper
        from docx import Document

        text = "\n".join(p.text for p in Document(str(out)).paragraphs)
        assert "Correlation heatmap" in text
        assert "24x24" in text

    def test_an_item_with_no_label_falls_back_to_the_url(self, paper):
        _result, out = paper
        assert "Credit_Risk_dashboard.html" in xml_of(out)

    def test_a_links_block_with_no_urls_writes_nothing_and_says_so(self, tmp_path):
        result, out = build(tmp_path, [{"kind": "links", "items": [{"label": "nowhere"}]}])
        assert result["links_embedded"] == 0
        assert result["skipped"]
        assert external_targets(out) == []


class TestTheRiskRegister:
    @pytest.fixture()
    def register(self, tmp_path):
        return build(
            tmp_path,
            [
                {
                    "kind": "risks",
                    "items": [
                        {
                            "risk": "Model leaks post-outcome features",
                            "level": "high",
                            "impact": "0.9628 accuracy is not real",
                            "mitigation": "Drop total_payment, retrain on a time split",
                            "owner": "Risk",
                        },
                        {"risk": "emp_title has 28,525 categories", "level": "medium"},
                        {"risk": "application_type is constant", "level": "low"},
                    ],
                }
            ],
        )

    def test_it_is_a_table(self, register):
        result, _out = register
        assert result["blocks_by_kind"]["risks"] == 1

    def test_every_risk_reaches_the_document(self, register):
        _result, out = register
        body = xml_of(out)
        for risk in ("post-outcome", "28,525", "application_type"):
            assert risk in body

    def test_the_levels_are_coloured(self, register):
        _result, out = register
        body = xml_of(out)
        for fill in ("C0392B", "D68910", "1E8449"):
            assert fill in body, f"no cell shaded {fill}"

    def test_the_columns_that_were_given_are_the_columns_shown(self, register):
        """Owner was given once; Impact once. Both appear."""
        _result, out = register
        body = xml_of(out)
        assert "Mitigation" in body and "Owner" in body and "Impact" in body

    def test_a_column_nobody_filled_is_not_shown(self, tmp_path):
        _result, out = build(tmp_path, [{"kind": "risks", "items": [{"risk": "r", "level": "low"}]}])
        body = xml_of(out)
        assert "Risk" in body and "Level" in body
        assert "Mitigation" not in body and "Owner" not in body

    def test_an_unknown_level_keeps_its_row(self, tmp_path):
        """Losing a risk to a spelling is the one failure a register must not have."""
        result, out = build(
            tmp_path,
            [{"kind": "risks", "items": [{"risk": "Unscored thing", "level": "critical"}]}],
        )
        assert "Unscored thing" in xml_of(out)
        assert any("critical" in note for note in result["skipped"])

    def test_the_levels_are_the_three_the_fleet_already_uses(self):
        assert RISK_LEVELS == ("high", "medium", "low")

    def test_an_empty_register_writes_no_table(self, tmp_path):
        result, _out = build(tmp_path, [{"kind": "risks", "items": []}])
        assert result["blocks_by_kind"].get("risks") is None
        assert result["skipped"]


class TestTheChecklist:
    @pytest.fixture()
    def actions(self, tmp_path):
        return build(
            tmp_path,
            [
                {
                    "kind": "checklist",
                    "items": [
                        {"text": "Drop id/member_id", "done": True},
                        {"text": "Re-split by issue_date", "done": False},
                        "Recalibrate probabilities",
                    ],
                }
            ],
        )

    def test_done_and_open_are_drawn_differently(self, actions):
        _result, out = actions
        body = xml_of(out)
        assert body.count("☒") == 1
        assert body.count("☐") == 2

    def test_a_bare_string_is_an_open_item(self, actions):
        _result, out = actions
        assert "Recalibrate probabilities" in xml_of(out)

    def test_it_uses_glyphs_rather_than_form_controls(self, actions):
        """A `w:sdt` check box is an empty grey rectangle outside a form."""
        _result, out = actions
        assert "<w:sdt>" not in xml_of(out)


class TestTheBrandTokens:
    def test_the_body_and_heading_faces_are_set_on_the_styles(self, tmp_path):
        result, out = build(
            tmp_path,
            [{"kind": "heading", "text": "Findings", "level": 2}, {"kind": "text", "text": "Body."}],
            font="Georgia",
            heading_font="Arial",
        )
        assert result["fonts"] == {"body": "Georgia", "headings": "Arial"}
        styles = xml_of(out, "word/styles.xml")
        assert 'w:ascii="Georgia"' in styles
        assert 'w:ascii="Arial"' in styles

    def test_one_font_covers_both(self, tmp_path):
        result, _out = build(tmp_path, [{"kind": "text", "text": "x"}], font="Verdana")
        assert result["fonts"] == {"body": "Verdana", "headings": "Verdana"}

    def test_no_font_is_not_an_error(self, tmp_path):
        result, _out = build(tmp_path, [{"kind": "text", "text": "x"}])
        assert result["fonts"] == {}

    def test_the_accent_still_applies(self, tmp_path):
        result, out = build(
            tmp_path,
            [{"kind": "table", "header": ["a"], "rows": [["b"]]}],
            accent="0B1D3A",
        )
        assert result["accent"] == "#0B1D3A"
        assert "0B1D3A" in xml_of(out)


class TestTheWholePaper:
    def test_every_new_kind_together(self, tmp_path):
        result, out = build(
            tmp_path,
            [
                {"kind": "kpi", "items": [{"value": "38,576", "label": "rows"}]},
                {"kind": "table", "header": ["Finding"], "rows": [["r = 0.9936"]]},
                {"kind": "risks", "items": [{"risk": "Leakage", "level": "high"}]},
                {"kind": "checklist", "items": [{"text": "Drop id", "done": True}]},
                {"kind": "links", "items": [{"label": "Dashboard", "url": "https://example.test/d.html"}]},
            ],
            accent="0B1D3A",
            font="Georgia",
        )
        assert result["skipped"] == []
        assert result["block_count"] == 5
        assert result["links_embedded"] == 1
        assert len(external_targets(out)) == 1
