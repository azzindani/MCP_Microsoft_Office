"""Excel charts plotted their own category labels as a data series.

add_chart called openpyxl's add_data(range, titles_from_data=True) and never
set_categories(). add_data makes EVERY column in the range a value series, so
the ordinary shape -- one column of names beside one column of numbers --
came out wrong in two ways at once:

    Platform      Spend        add_chart(data_range="A1:B3")
    Google Ads    1939000      -> series 0: values A2:A3  ("Google Ads", ...)
    Facebook Ads   564100         series 1: values B2:B3  (1939000, 564100)
                                    categories: None

The text column was charted as a quantity, which renders as a flat row of
zeros beside the real bars, and because no categories were set the axis was
numbered 1, 2, 3 -- so the platform names appeared nowhere on the chart at all.
The response said success and named the range back, and the workbook opened
without complaint.

update_chart rebuilt its series through the same two lines and had the same
bug.

A first column of text with no numbers in it is labels, and is now used as the
category axis. An all-numeric first column is still a series, which is what a
scatter's x-values are.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from xlsx_charts.engine import add_chart, update_chart  # type: ignore[reportMissingImports]

HEADERS = ["Platform", "Spend", "Impressions"]
ROWS = [["Google Ads", 1939000, 4100000], ["Facebook Ads", 564100, 776900]]


def _book(path: Path, headers: list, rows: list) -> str:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Spend"  # type: ignore[reportOptionalMemberAccess]
    ws.append(headers)  # type: ignore[reportOptionalMemberAccess]
    for row in rows:
        ws.append(row)  # type: ignore[reportOptionalMemberAccess]
    wb.save(str(path))
    return str(path)


def _chart(path: str, index: int = 0):
    return openpyxl.load_workbook(path)["Spend"]._charts[index]  # type: ignore[reportAttributeAccessIssue]


def _series_refs(chart) -> list[str | None]:
    return [s.val.numRef.f if s.val and s.val.numRef else None for s in chart.series]


def _category_ref(chart) -> str | None:
    cat = chart.series[0].cat
    if cat is None:
        return None
    return (cat.numRef.f if cat.numRef else None) or (cat.strRef.f if cat.strRef else None)


@pytest.fixture()
def book(tmp_path: Path) -> str:
    return _book(tmp_path / "spend.xlsx", HEADERS, ROWS)


class TestALabelColumnBecomesTheAxis:
    def test_the_text_column_is_not_charted_as_a_series(self, book: str):
        add_chart(book, "Spend", "bar", "A1:B3", "Total spend by platform", "E2")
        refs = _series_refs(_chart(book))
        assert not any(r and "$A$" in r for r in refs), refs

    def test_there_is_one_series_not_two(self, book: str):
        add_chart(book, "Spend", "bar", "A1:B3", "Total spend by platform", "E2")
        assert len(_chart(book).series) == 1

    def test_the_series_is_the_number_column(self, book: str):
        add_chart(book, "Spend", "bar", "A1:B3", "Total spend by platform", "E2")
        assert _series_refs(_chart(book)) == ["'Spend'!$B$2:$B$3"]

    def test_the_platform_names_are_the_categories(self, book: str):
        add_chart(book, "Spend", "bar", "A1:B3", "Total spend by platform", "E2")
        assert _category_ref(_chart(book)) == "'Spend'!$A$2:$A$3"

    def test_two_value_columns_give_two_series_and_still_keep_labels(self, book: str):
        add_chart(book, "Spend", "bar", "A1:C3", "Spend and impressions", "E2")
        chart = _chart(book)
        assert _series_refs(chart) == ["'Spend'!$B$2:$B$3", "'Spend'!$C$2:$C$3"]
        assert _category_ref(chart) == "'Spend'!$A$2:$A$3"

    def test_the_progress_says_the_first_column_was_used_as_labels(self, book: str):
        r = add_chart(book, "Spend", "bar", "A1:B3", "t", "E2")
        assert "labels" in str(r["progress"]), r["progress"]

    @pytest.mark.parametrize("chart_type", ["bar", "line", "pie", "area"])
    def test_every_chart_type_gets_its_labels(self, tmp_path: Path, chart_type: str):
        path = _book(tmp_path / f"{chart_type}.xlsx", HEADERS, ROWS)
        r = add_chart(path, "Spend", chart_type, "A1:B3", "t", "E2")
        assert r["success"] is True, r.get("error")
        assert _category_ref(_chart(path)) == "'Spend'!$A$2:$A$3"


class TestAnAllNumericFirstColumnIsStillData:
    """A scatter's x-values live in the first column and are not labels."""

    @pytest.fixture()
    def numeric_book(self, tmp_path: Path) -> str:
        return _book(tmp_path / "nums.xlsx", ["X", "Y"], [[1, 10], [2, 20], [3, 30]])

    def test_both_columns_stay_series(self, numeric_book: str):
        add_chart(numeric_book, "Spend", "scatter", "A1:B4", "xy", "E2")
        assert len(_chart(numeric_book).series) == 2

    def test_no_categories_are_invented(self, numeric_book: str):
        add_chart(numeric_book, "Spend", "scatter", "A1:B4", "xy", "E2")
        assert _category_ref(_chart(numeric_book)) is None


class TestASingleColumnRangeIsUnchanged:
    def test_one_column_cannot_be_both_labels_and_data(self, book: str):
        add_chart(book, "Spend", "bar", "B1:B3", "just spend", "E2")
        chart = _chart(book)
        assert _series_refs(chart) == ["'Spend'!$B$2:$B$3"]
        assert _category_ref(chart) is None


class TestUpdateChartRebuildsItTheSameWay:
    def test_it_does_not_reintroduce_the_label_series(self, book: str):
        add_chart(book, "Spend", "bar", "A1:B3", "t", "E2")
        r = update_chart(book, "Spend", 0, data_range="A1:C3")
        assert r["success"] is True, r.get("error")
        chart = _chart(book)
        assert _series_refs(chart) == ["'Spend'!$B$2:$B$3", "'Spend'!$C$2:$C$3"]

    def test_it_sets_the_categories_too(self, book: str):
        add_chart(book, "Spend", "bar", "A1:B3", "t", "E2")
        update_chart(book, "Spend", 0, data_range="A1:C3")
        assert _category_ref(_chart(book)) == "'Spend'!$A$2:$A$3"

    def test_a_title_only_update_leaves_the_series_alone(self, book: str):
        add_chart(book, "Spend", "bar", "A1:B3", "t", "E2")
        update_chart(book, "Spend", 0, title="Renamed")
        assert _series_refs(_chart(book)) == ["'Spend'!$B$2:$B$3"]


class TestTheRangeStillParses:
    def test_a_sheet_qualified_range_works(self, book: str):
        r = add_chart(book, "Spend", "bar", "Spend!A1:B3", "t", "E2")
        assert r["success"] is True, r.get("error")
        assert _category_ref(_chart(book)) == "'Spend'!$A$2:$A$3"

    def test_a_malformed_range_does_not_crash_the_tool(self, book: str):
        r = add_chart(book, "Spend", "bar", "not-a-range", "t", "E2")
        assert r["success"] in (True, False)
        assert isinstance(r.get("error", ""), str)
