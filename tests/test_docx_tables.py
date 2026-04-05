"""Tests for the docx_tables server engine."""

import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _copy(name: str, tmp_path: Path) -> Path:
    src = FIXTURES / name
    if not src.exists():
        pytest.skip(f"Fixture {name} not found.")
    dst = tmp_path / name
    shutil.copy(src, dst)
    return dst


# ─── list_tables ──────────────────────────────────────────────────────────────


class TestListTables:
    def test_list_tables_returns_dimensions(self, tmp_path):
        from servers.docx_tables.engine import list_tables

        path = _copy("report_tables.docx", tmp_path)
        result = list_tables(str(path))
        assert result["success"] is True
        assert result["table_count"] == 2
        tables = result["tables"]
        assert len(tables) == 2
        assert tables[0]["index"] == 0
        assert tables[0]["rows"] == 5
        assert tables[0]["cols"] == 4

    def test_list_tables_has_progress(self, tmp_path):
        from servers.docx_tables.engine import list_tables

        path = _copy("report_tables.docx", tmp_path)
        result = list_tables(str(path))
        assert "progress" in result
        assert len(result["progress"]) > 0

    def test_list_tables_file_not_found(self, tmp_path):
        from servers.docx_tables.engine import list_tables

        result = list_tables(str(tmp_path / "missing.docx"))
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_list_tables_wrong_type(self, tmp_path):
        from servers.docx_tables.engine import list_tables

        f = tmp_path / "test.xlsx"
        f.write_bytes(b"fake")
        result = list_tables(str(f))
        assert result["success"] is False
        assert ".docx" in result["error"]


# ─── read_table ───────────────────────────────────────────────────────────────


class TestReadTable:
    def test_read_table_returns_2d_array(self, tmp_path):
        from servers.docx_tables.engine import read_table

        path = _copy("report_tables.docx", tmp_path)
        result = read_table(str(path), 0)
        assert result["success"] is True
        assert result["table_index"] == 0
        assert result["rows"] == 5
        assert result["cols"] == 4
        data = result["data"]
        assert len(data) == 5
        # Header row
        assert data[0][0]["text"] == "Region"
        assert data[0][1]["text"] == "Q1"
        assert data[0][2]["text"] == "Q2"
        assert data[0][3]["text"] == "Total"

    def test_read_table_cells_have_col_key(self, tmp_path):
        from servers.docx_tables.engine import read_table

        path = _copy("report_tables.docx", tmp_path)
        result = read_table(str(path), 0)
        for row in result["data"]:
            for cell in row:
                assert "col" in cell
                assert "text" in cell

    def test_read_table_handles_merged_cells(self, tmp_path):
        """Merged cell detection should not crash even on normal tables."""
        from servers.docx_tables.engine import read_table

        path = _copy("report_tables.docx", tmp_path)
        result = read_table(str(path), 0)
        # Verify every cell entry has text key (merged or real)
        assert result["success"] is True
        for row in result["data"]:
            for cell in row:
                assert "text" in cell

    def test_read_table_index_out_of_range(self, tmp_path):
        from servers.docx_tables.engine import read_table

        path = _copy("report_tables.docx", tmp_path)
        result = read_table(str(path), 99)
        assert result["success"] is False
        assert "out of range" in result["error"]
        assert "hint" in result

    def test_read_table_file_not_found(self, tmp_path):
        from servers.docx_tables.engine import read_table

        result = read_table(str(tmp_path / "nope.docx"), 0)
        assert result["success"] is False


# ─── search_table_cells ───────────────────────────────────────────────────────


class TestSearchTableCells:
    def test_search_table_cells_finds_match(self, tmp_path):
        from servers.docx_tables.engine import search_table_cells

        path = _copy("report_tables.docx", tmp_path)
        result = search_table_cells(str(path), "North")
        assert result["success"] is True
        assert len(result["matches"]) > 0
        match = result["matches"][0]
        assert "table_index" in match
        assert "row" in match
        assert "col" in match
        assert "text" in match
        assert "North" in match["text"]

    def test_search_table_cells_no_match(self, tmp_path):
        from servers.docx_tables.engine import search_table_cells

        path = _copy("report_tables.docx", tmp_path)
        result = search_table_cells(str(path), "ZZZNOMATCH")
        assert result["success"] is True
        assert result["matches"] == []

    def test_search_table_cells_empty_query(self, tmp_path):
        from servers.docx_tables.engine import search_table_cells

        path = _copy("report_tables.docx", tmp_path)
        result = search_table_cells(str(path), "")
        assert result["success"] is False

    def test_search_table_cells_respects_max_results(self, tmp_path):
        from servers.docx_tables.engine import search_table_cells

        path = _copy("report_tables.docx", tmp_path)
        # "Region" appears in both tables header row
        result = search_table_cells(str(path), "Region", max_results=1)
        assert result["success"] is True
        assert len(result["matches"]) <= 1

    def test_search_table_cells_case_insensitive(self, tmp_path):
        from servers.docx_tables.engine import search_table_cells

        path = _copy("report_tables.docx", tmp_path)
        result_lower = search_table_cells(str(path), "north")
        result_upper = search_table_cells(str(path), "NORTH")
        assert result_lower["success"] is True
        assert result_upper["success"] is True
        assert len(result_lower["matches"]) == len(result_upper["matches"])


# ─── read_table_row ───────────────────────────────────────────────────────────


class TestReadTableRow:
    def test_read_table_row_returns_cells(self, tmp_path):
        from servers.docx_tables.engine import read_table_row

        path = _copy("report_tables.docx", tmp_path)
        result = read_table_row(str(path), 0, 0)
        assert result["success"] is True
        assert result["table_index"] == 0
        assert result["row"] == 0
        cells = result["cells"]
        assert len(cells) == 4
        assert cells[0]["text"] == "Region"
        assert cells[1]["text"] == "Q1"

    def test_read_table_row_second_row(self, tmp_path):
        from servers.docx_tables.engine import read_table_row

        path = _copy("report_tables.docx", tmp_path)
        result = read_table_row(str(path), 0, 1)
        assert result["success"] is True
        assert result["cells"][0]["text"] == "North"

    def test_read_table_row_out_of_range(self, tmp_path):
        from servers.docx_tables.engine import read_table_row

        path = _copy("report_tables.docx", tmp_path)
        result = read_table_row(str(path), 0, 99)
        assert result["success"] is False
        assert "out of range" in result["error"]

    def test_read_table_row_table_out_of_range(self, tmp_path):
        from servers.docx_tables.engine import read_table_row

        path = _copy("report_tables.docx", tmp_path)
        result = read_table_row(str(path), 99, 0)
        assert result["success"] is False


# ─── set_cell ─────────────────────────────────────────────────────────────────


class TestSetCell:
    def test_set_cell_writes_value(self, tmp_path):
        from servers.docx_tables.engine import read_table, set_cell

        path = _copy("report_tables.docx", tmp_path)
        result = set_cell(str(path), 0, 1, 0, "East")
        assert result["success"] is True
        assert result["new_text"] == "East"
        # Verify by reading back
        read_result = read_table(str(path), 0)
        assert read_result["data"][1][0]["text"] == "East"

    def test_set_cell_creates_snapshot(self, tmp_path):
        from servers.docx_tables.engine import set_cell

        path = _copy("report_tables.docx", tmp_path)
        result = set_cell(str(path), 0, 1, 1, "99999")
        assert result["success"] is True
        assert "backup" in result
        assert result["backup"] is not None
        backup_path = Path(result["backup"])
        assert backup_path.exists()

    def test_set_cell_returns_old_text(self, tmp_path):
        from servers.docx_tables.engine import set_cell

        path = _copy("report_tables.docx", tmp_path)
        result = set_cell(str(path), 0, 1, 0, "NewVal")
        assert result["success"] is True
        assert result["old_text"] == "North"

    def test_set_cell_out_of_range_row(self, tmp_path):
        from servers.docx_tables.engine import set_cell

        path = _copy("report_tables.docx", tmp_path)
        result = set_cell(str(path), 0, 99, 0, "x")
        assert result["success"] is False
        assert "out of range" in result["error"]
        assert "hint" in result

    def test_set_cell_out_of_range_col(self, tmp_path):
        from servers.docx_tables.engine import set_cell

        path = _copy("report_tables.docx", tmp_path)
        result = set_cell(str(path), 0, 0, 99, "x")
        assert result["success"] is False
        assert "out of range" in result["error"]

    def test_set_cell_out_of_range_table(self, tmp_path):
        from servers.docx_tables.engine import set_cell

        path = _copy("report_tables.docx", tmp_path)
        result = set_cell(str(path), 99, 0, 0, "x")
        assert result["success"] is False

    def test_set_cell_has_progress(self, tmp_path):
        from servers.docx_tables.engine import set_cell

        path = _copy("report_tables.docx", tmp_path)
        result = set_cell(str(path), 0, 0, 0, "Header")
        assert "progress" in result
        assert len(result["progress"]) > 0


# ─── add_row ──────────────────────────────────────────────────────────────────


class TestAddRow:
    def test_add_row_appends_data(self, tmp_path):
        from servers.docx_tables.engine import add_row, list_tables, read_table

        path = _copy("report_tables.docx", tmp_path)
        # Table 0 starts with 5 rows
        result = add_row(str(path), 0, ["East", "15000", "16000", "31000"])
        assert result["success"] is True
        assert result["new_row_index"] == 5
        # Verify row count increased
        tables_result = list_tables(str(path))
        assert tables_result["tables"][0]["rows"] == 6
        # Verify content
        read_result = read_table(str(path), 0)
        last_row = read_result["data"][-1]
        assert last_row[0]["text"] == "East"
        assert last_row[1]["text"] == "15000"

    def test_add_row_creates_snapshot(self, tmp_path):
        from servers.docx_tables.engine import add_row

        path = _copy("report_tables.docx", tmp_path)
        result = add_row(str(path), 0, ["A", "B", "C", "D"])
        assert result["success"] is True
        assert "backup" in result
        backup_path = Path(result["backup"])
        assert backup_path.exists()

    def test_add_row_partial_data(self, tmp_path):
        """Rows with fewer data items than cols should fill remaining with empty."""
        from servers.docx_tables.engine import add_row, read_table

        path = _copy("report_tables.docx", tmp_path)
        result = add_row(str(path), 0, ["OnlyOne"])
        assert result["success"] is True
        read_result = read_table(str(path), 0)
        last_row = read_result["data"][-1]
        assert last_row[0]["text"] == "OnlyOne"
        # Remaining cells should be empty strings
        assert last_row[1]["text"] == ""

    def test_add_row_table_out_of_range(self, tmp_path):
        from servers.docx_tables.engine import add_row

        path = _copy("report_tables.docx", tmp_path)
        result = add_row(str(path), 99, ["x"])
        assert result["success"] is False


# ─── delete_row ───────────────────────────────────────────────────────────────


class TestDeleteRow:
    def test_delete_row_shifts_up(self, tmp_path):
        from servers.docx_tables.engine import delete_row, list_tables, read_table

        path = _copy("report_tables.docx", tmp_path)
        # Row 1 is "North". Delete it — row 2 ("South") becomes new row 1.
        result = delete_row(str(path), 0, 1)
        assert result["success"] is True
        assert result["deleted_row"] == 1
        tables_result = list_tables(str(path))
        assert tables_result["tables"][0]["rows"] == 4
        read_result = read_table(str(path), 0)
        assert read_result["data"][1][0]["text"] == "South"

    def test_delete_row_creates_snapshot(self, tmp_path):
        from servers.docx_tables.engine import delete_row

        path = _copy("report_tables.docx", tmp_path)
        result = delete_row(str(path), 0, 0)
        assert result["success"] is True
        assert "backup" in result
        backup_path = Path(result["backup"])
        assert backup_path.exists()

    def test_delete_row_returns_deleted_text(self, tmp_path):
        from servers.docx_tables.engine import delete_row

        path = _copy("report_tables.docx", tmp_path)
        result = delete_row(str(path), 0, 0)
        assert result["success"] is True
        assert "deleted_text" in result
        assert result["deleted_text"][0] == "Region"

    def test_delete_row_out_of_range(self, tmp_path):
        from servers.docx_tables.engine import delete_row

        path = _copy("report_tables.docx", tmp_path)
        result = delete_row(str(path), 0, 99)
        assert result["success"] is False
        assert "out of range" in result["error"]

    def test_delete_row_table_out_of_range(self, tmp_path):
        from servers.docx_tables.engine import delete_row

        path = _copy("report_tables.docx", tmp_path)
        result = delete_row(str(path), 99, 0)
        assert result["success"] is False


# ─── add_table ────────────────────────────────────────────────────────────────


class TestAddTable:
    def test_add_table_at_position(self, tmp_path):
        from servers.docx_tables.engine import add_table, list_tables

        path = _copy("report_tables.docx", tmp_path)
        result = add_table(str(path), 0, rows=2, cols=3)
        assert result["success"] is True
        assert result["rows"] == 2
        assert result["cols"] == 3
        tables_result = list_tables(str(path))
        assert tables_result["table_count"] == 3

    def test_add_table_with_data(self, tmp_path):
        from servers.docx_tables.engine import add_table, list_tables

        path = _copy("report_tables.docx", tmp_path)
        data = [["Name", "Score"], ["Alice", "95"]]
        result = add_table(str(path), 0, rows=2, cols=2, data=data)
        assert result["success"] is True
        # The new table should contain the data (it's the 3rd table now)
        tables_result = list_tables(str(path))
        assert tables_result["table_count"] == 3

    def test_add_table_creates_snapshot(self, tmp_path):
        from servers.docx_tables.engine import add_table

        path = _copy("report_tables.docx", tmp_path)
        result = add_table(str(path), 0, rows=2, cols=2)
        assert result["success"] is True
        assert "backup" in result
        backup_path = Path(result["backup"])
        assert backup_path.exists()

    def test_add_table_paragraph_out_of_range(self, tmp_path):
        from servers.docx_tables.engine import add_table

        path = _copy("report_tables.docx", tmp_path)
        result = add_table(str(path), 9999, rows=2, cols=2)
        assert result["success"] is False
        assert "out of range" in result["error"]

    def test_add_table_invalid_dimensions(self, tmp_path):
        from servers.docx_tables.engine import add_table

        path = _copy("report_tables.docx", tmp_path)
        result = add_table(str(path), 0, rows=0, cols=2)
        assert result["success"] is False


# ─── delete_table ─────────────────────────────────────────────────────────────


class TestDeleteTable:
    def test_delete_table_removes_correctly(self, tmp_path):
        from servers.docx_tables.engine import delete_table, list_tables

        path = _copy("report_tables.docx", tmp_path)
        result = delete_table(str(path), 0)
        assert result["success"] is True
        assert result["deleted_rows"] == 5
        assert result["deleted_cols"] == 4
        tables_result = list_tables(str(path))
        assert tables_result["table_count"] == 1

    def test_delete_table_creates_snapshot(self, tmp_path):
        from servers.docx_tables.engine import delete_table

        path = _copy("report_tables.docx", tmp_path)
        result = delete_table(str(path), 0)
        assert result["success"] is True
        assert "backup" in result
        backup_path = Path(result["backup"])
        assert backup_path.exists()

    def test_delete_table_out_of_range(self, tmp_path):
        from servers.docx_tables.engine import delete_table

        path = _copy("report_tables.docx", tmp_path)
        result = delete_table(str(path), 99)
        assert result["success"] is False
        assert "out of range" in result["error"]
        assert "hint" in result

    def test_delete_table_second_table(self, tmp_path):
        from servers.docx_tables.engine import delete_table, list_tables

        path = _copy("report_tables.docx", tmp_path)
        result = delete_table(str(path), 1)
        assert result["success"] is True
        tables_result = list_tables(str(path))
        assert tables_result["table_count"] == 1
