"""Every xlsx server answered a wrong sheet name with a second call to make.

    read_cell(book, "Q3", "A1")
      error: "Sheet 'Q3' not found"
      hint : "Use list_sheets to get available sheet names."

The workbook is open in front of the tool at that point, so the names it is
telling the caller to go and fetch are already in hand. Every other server in
the fleet spends them inline -- read_column_stats lists the columns,
statistical_test lists the columns, fs_write lists the valid ops -- and a sweep
that guesses a sheet name wrong should recover in one call, not two.

Found by calling read tools with a valid file and an identifier that isn't in
it, then asking of each error: does it name what *is* there?
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shared.file_utils import sheet_names_hint
from xlsx_basic.engine import (  # type: ignore[reportMissingImports]
    add_sheet,
    get_sheet_summary,
    read_cell,
    read_cell_range,
    search_cells,
)
from xlsx_basic.helpers import copy_sheet, rename_sheet  # type: ignore[reportMissingImports]
from xlsx_charts.engine import add_chart  # type: ignore[reportMissingImports]
from xlsx_formulas.engine import set_formula  # type: ignore[reportMissingImports]
from xlsx_new.engine import create_from_data  # type: ignore[reportMissingImports]

GHOST = "NoSuchSheet"


@pytest.fixture()
def book(tmp_path: Path) -> str:
    p = tmp_path / "book.xlsx"
    create_from_data(str(p), "Data", ["a", "b"], [[1, 2], [3, 4]], open_after=False)
    add_sheet(str(p), "Summary")
    return str(p)


def call(name: str, book: str):
    return {
        "get_sheet_summary": lambda: get_sheet_summary(book, GHOST),
        "read_cell": lambda: read_cell(book, GHOST, "A1"),
        "read_cell_range": lambda: read_cell_range(book, GHOST, "A1:B2"),
        "search_cells": lambda: search_cells(book, GHOST, "x"),
        "rename_sheet": lambda: rename_sheet(book, GHOST, "new"),
        "copy_sheet": lambda: copy_sheet(book, GHOST, "cp"),
        "set_formula": lambda: set_formula(book, GHOST, "A9", "=SUM(A1:A2)"),
        "add_chart": lambda: add_chart(book, GHOST, "bar", "A1:A2", "T", "D2"),
    }[name]()


TOOLS = [
    "get_sheet_summary",
    "read_cell",
    "read_cell_range",
    "search_cells",
    "rename_sheet",
    "copy_sheet",
    "set_formula",
    "add_chart",
]


class TestTheHintNamesTheSheetsThatExist:
    @pytest.mark.parametrize("tool", TOOLS)
    def test_it_fails(self, tool: str, book: str):
        assert call(tool, book)["success"] is False

    @pytest.mark.parametrize("tool", TOOLS)
    def test_the_hint_lists_the_real_sheets(self, tool: str, book: str):
        hint = call(tool, book)["hint"]
        assert "Data" in hint and "Summary" in hint, f"{tool}: {hint}"

    @pytest.mark.parametrize("tool", TOOLS)
    def test_the_error_still_names_the_sheet_that_was_asked_for(self, tool: str, book: str):
        assert GHOST in call(tool, book)["error"], tool

    @pytest.mark.parametrize("tool", TOOLS)
    def test_it_no_longer_only_defers_to_list_sheets(self, tool: str, book: str):
        hint = call(tool, book)["hint"]
        assert hint != "Use list_sheets to get available sheet names.", tool

    def test_every_tool_gives_the_same_hint(self, book: str):
        hints = {t: call(t, book)["hint"] for t in TOOLS}
        assert len(set(hints.values())) == 1, hints


class TestTheHelperItself:
    def test_it_names_a_single_sheet(self):
        assert sheet_names_hint(["Only"]) == "Available sheets: Only"

    def test_it_names_a_few_sheets(self):
        assert sheet_names_hint(["A", "B", "C"]) == "Available sheets: A, B, C"

    def test_it_caps_a_wide_workbook_and_says_how_many_are_left(self):
        hint = sheet_names_hint([f"S{i}" for i in range(20)])
        assert "(+8 more)" in hint, hint
        assert "list_sheets" in hint, hint

    def test_the_cap_keeps_the_hint_short(self):
        assert len(sheet_names_hint([f"Sheet number {i}" for i in range(200)])) < 300

    def test_an_empty_workbook_points_at_add_sheet(self):
        assert "add_sheet" in sheet_names_hint([])


class TestTheRightSheetNameIsUnaffected:
    def test_read_cell_still_reads(self, book: str):
        r = read_cell(book, "Data", "A2")
        assert r["success"] is True, r.get("error")

    def test_get_sheet_summary_still_summarises(self, book: str):
        r = get_sheet_summary(book, "Data")
        assert r["success"] is True, r.get("error")

    def test_set_formula_still_writes(self, book: str):
        r = set_formula(book, "Data", "C1", "=SUM(A2:A3)")
        assert r["success"] is True, r.get("error")

    def test_rename_still_renames(self, book: str):
        r = rename_sheet(book, "Summary", "Totals")
        assert r["success"] is True, r.get("error")
