"""The advice offered a choice between two empty strings.

add_pivot_table reads the first row of its source range as the header row and,
when the column a caller named is not among them, lists what is. On a blank
sheet every one of those headers is "", so the hint came out as:

    Pass rows= one of these headers: ,

which is not a list of anything. Worse, it points at the wrong place: the caller
reads it as "my column name is wrong" and tries other names, when the actual
problem is that the range they gave has no header row at all.

Round 12 hit this by handing the tool a workbook with one blank sheet. The
refusal itself was correct -- the pivot genuinely cannot be built -- so this is
not about whether to refuse but about whether the reason survives the trip.

When no header is usable the hint now says so and names the row it looked at.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "shared"), str(ROOT / "servers" / "xlsx_charts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from xlsx_charts import engine  # noqa: E402


@pytest.fixture
def blank(tmp_path) -> str:
    import openpyxl

    wb = openpyxl.Workbook()
    p = tmp_path / "blank.xlsx"
    wb.save(str(p))
    return str(p)


@pytest.fixture
def populated(tmp_path) -> str:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Region", "Category", "Revenue"])
    ws.append(["EMEA", "Widgets", 10])
    ws.append(["APAC", "Widgets", 20])
    p = tmp_path / "data.xlsx"
    wb.save(str(p))
    return str(p)


class TestABlankSheetSaysSo:
    def test_it_still_refuses(self, blank):
        r = engine.add_pivot_table(blank, "Sheet", source_range="A1:C3", dest_cell="E1", rows="A", values="B")
        assert r["success"] is False

    def test_the_hint_does_not_list_empty_names(self, blank):
        r = engine.add_pivot_table(blank, "Sheet", source_range="A1:C3", dest_cell="E1", rows="A", values="B")
        hint = r["hint"]
        assert "headers: ," not in hint, hint
        assert not hint.rstrip().endswith(":"), hint

    def test_it_names_the_row_it_looked_at(self, blank):
        r = engine.add_pivot_table(blank, "Sheet", source_range="A1:C3", dest_cell="E1", rows="A", values="B")
        assert "Row 1" in r["hint"], r["hint"]

    def test_it_says_what_to_do_instead(self, blank):
        r = engine.add_pivot_table(blank, "Sheet", source_range="A1:C3", dest_cell="E1", rows="A", values="B")
        assert "set_range" in r["hint"], r["hint"]

    def test_a_missing_rows_argument_gets_the_same_treatment(self, blank):
        r = engine.add_pivot_table(blank, "Sheet", source_range="A1:C3", dest_cell="E1", rows="", values="B")
        assert r["success"] is False
        assert "headers: ," not in r["hint"], r["hint"]


class TestARealSheetStillListsItsHeaders:
    def test_a_wrong_column_name_is_told_the_right_ones(self, populated):
        r = engine.add_pivot_table(
            populated, "Sheet", source_range="A1:C3", dest_cell="E1", rows="Rgion", values="Revenue"
        )
        assert r["success"] is False
        assert "Region" in r["hint"], r["hint"]

    def test_the_hint_lists_every_named_header(self, populated):
        r = engine.add_pivot_table(
            populated, "Sheet", source_range="A1:C3", dest_cell="E1", rows="nope", values="Revenue"
        )
        for h in ("Region", "Category", "Revenue"):
            assert h in r["hint"], r["hint"]

    def test_a_missing_argument_is_caught_earlier_and_says_something_real(self, populated):
        # An absent rows= is refused before the header row is ever read, by a
        # guard whose hint names source_range rather than listing columns. That
        # is fine; what matters is that no branch offers empty names.
        r = engine.add_pivot_table(populated, "Sheet", source_range="A1:C3", dest_cell="E1", rows="", values="Revenue")
        assert r["success"] is False
        assert "headers: ," not in r["hint"], r["hint"]
        assert "source_range" in r["hint"], r["hint"]

    def test_a_valid_pivot_still_builds(self, populated):
        r = engine.add_pivot_table(
            populated, "Sheet", source_range="A1:C3", dest_cell="E1", rows="Region", values="Revenue"
        )
        assert r["success"] is True, r.get("error")


class TestTheResponseContract:
    def test_the_refusal_carries_a_token_estimate(self, blank):
        r = engine.add_pivot_table(blank, "Sheet", source_range="A1:C3", dest_cell="E1", rows="A", values="B")
        assert isinstance(r["token_estimate"], int)

    def test_the_error_still_names_the_column(self, populated):
        r = engine.add_pivot_table(
            populated, "Sheet", source_range="A1:C3", dest_cell="E1", rows="nope", values="Revenue"
        )
        assert "nope" in r["error"], r["error"]
