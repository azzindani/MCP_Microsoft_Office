"""DOCX Tables MCP server — thin wrapper over engine.py."""

from mcp.server.fastmcp import FastMCP

from docx_tables import engine

mcp = FastMCP("docx-tables")


@mcp.tool()
def list_tables(file_path: str) -> dict:
    """List all tables with row/column dimensions."""
    return engine.list_tables(file_path)


@mcp.tool()
def read_table(file_path: str, table_index: int) -> dict:
    """Return full 2-D cell array for one table."""
    return engine.read_table(file_path, table_index)


@mcp.tool()
def search_table_cells(
    file_path: str, query: str, max_results: int = 10
) -> dict:
    """Scan all table cells for matching text. Returns coordinates."""
    return engine.search_table_cells(file_path, query, max_results)


@mcp.tool()
def read_table_row(file_path: str, table_index: int, row: int) -> dict:
    """Return all cells in one table row."""
    return engine.read_table_row(file_path, table_index, row)


@mcp.tool()
def set_cell(
    file_path: str, table_index: int, row: int, col: int, text: str
) -> dict:
    """Write text to a specific table cell. Snapshot taken before write."""
    return engine.set_cell(file_path, table_index, row, col, text)


@mcp.tool()
def add_row(file_path: str, table_index: int, data: list[str]) -> dict:
    """Append a row to table N. data is a list of cell text strings."""
    return engine.add_row(file_path, table_index, data)


@mcp.tool()
def delete_row(file_path: str, table_index: int, row: int) -> dict:
    """Remove row R from table N. Rows below shift up."""
    return engine.delete_row(file_path, table_index, row)


@mcp.tool()
def add_table(
    file_path: str,
    after_paragraph_index: int,
    rows: int,
    cols: int,
    data: list[list[str]] | None = None,
) -> dict:
    """Insert new table after paragraph N. data is optional rows×cols list."""
    return engine.add_table(file_path, after_paragraph_index, rows, cols, data)


@mcp.tool()
def delete_table(file_path: str, table_index: int) -> dict:
    """Remove table N from the document entirely."""
    return engine.delete_table(file_path, table_index)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
