"""XLSX Basic MCP server — thin wrapper over engine.py."""

from mcp.server.fastmcp import FastMCP

from xlsx_basic import engine
from xlsx_basic.helpers import copy_sheet as _copy_sheet
from xlsx_basic.helpers import find_duplicates as _find_duplicates
from xlsx_basic.helpers import rename_sheet as _rename_sheet
from xlsx_basic.helpers import sort_sheet as _sort_sheet

mcp = FastMCP("xlsx-basic")


@mcp.tool()
def list_sheets(file_path: str) -> dict:
    """List all sheets with row and column dimensions."""
    return engine.list_sheets(file_path)


@mcp.tool()
def get_sheet_summary(file_path: str, sheet_name: str) -> dict:
    """Return sheet dimensions, header row, and first-column sample."""
    return engine.get_sheet_summary(file_path, sheet_name)


@mcp.tool()
def read_cell(file_path: str, sheet_name: str, cell_address: str) -> dict:
    """Return value, formula, and data type for one cell."""
    return engine.read_cell(file_path, sheet_name, cell_address)


@mcp.tool()
def read_cell_range(file_path: str, sheet_name: str, range_address: str) -> dict:
    """Return 2D cell array for range. Max 200 cells."""
    return engine.read_cell_range(file_path, sheet_name, range_address)


@mcp.tool()
def search_cells(file_path: str, sheet_name: str, query: str, max_results: int = 20) -> dict:
    """Scan cells for text matching query. Returns matching addresses."""
    return engine.search_cells(file_path, sheet_name, query, max_results)


@mcp.tool()
def set_cell(file_path: str, sheet_name: str, cell_address: str, value: str, open_after: bool = False) -> dict:
    """Write a value to a single cell by address."""
    return engine.set_cell(file_path, sheet_name, cell_address, value, open_after)


@mcp.tool()
def set_range(file_path: str, sheet_name: str, start_cell: str, data: list[list], open_after: bool = False) -> dict:
    """Write a 2D list of values starting at start_cell."""
    return engine.set_range(file_path, sheet_name, start_cell, data, open_after)


@mcp.tool()
def insert_row(file_path: str, sheet_name: str, row_index: int, open_after: bool = False) -> dict:
    """Insert empty row at row_index (1-based), shifting rows down."""
    return engine.insert_row(file_path, sheet_name, row_index, open_after)


@mcp.tool()
def delete_row(file_path: str, sheet_name: str, row_index: int, open_after: bool = False) -> dict:
    """Remove row at row_index (1-based), shifting remaining rows up."""
    return engine.delete_row(file_path, sheet_name, row_index, open_after)


@mcp.tool()
def add_sheet(file_path: str, sheet_name: str = "", open_after: bool = False) -> dict:
    """Create a new worksheet with an optional name."""
    return engine.add_sheet(file_path, sheet_name, open_after)


@mcp.tool()
def sort_sheet(
    file_path: str,
    sheet_name: str,
    column: str,
    ascending: bool = True,
    has_header: bool = True,
    open_after: bool = False,
) -> dict:
    """Sort sheet rows by column. column='A'. has_header skips row 1."""
    return _sort_sheet(file_path, sheet_name, column, ascending, has_header, open_after)


@mcp.tool()
def rename_sheet(file_path: str, old_name: str, new_name: str, open_after: bool = False) -> dict:
    """Rename a sheet tab from old_name to new_name."""
    return _rename_sheet(file_path, old_name, new_name, open_after)


@mcp.tool()
def find_duplicates(
    file_path: str,
    sheet_name: str,
    column: str,
    has_header: bool = True,
) -> dict:
    """Find duplicate values in a column. Returns rows where value repeats."""
    return _find_duplicates(file_path, sheet_name, column, has_header)


@mcp.tool()
def copy_sheet(file_path: str, source_sheet: str, new_sheet_name: str, open_after: bool = False) -> dict:
    """Copy source_sheet to a new sheet named new_sheet_name."""
    return _copy_sheet(file_path, source_sheet, new_sheet_name, open_after)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
