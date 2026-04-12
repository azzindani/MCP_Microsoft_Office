"""XLSX Charts MCP server — thin wrapper over engine.py."""

from mcp.server.fastmcp import FastMCP

from xlsx_charts import engine

mcp = FastMCP("xlsx-charts")


@mcp.tool()
def add_chart(
    file_path: str,
    sheet_name: str,
    chart_type: str,
    data_range: str,
    title: str,
    anchor_cell: str,
    width: float = 15.0,
    height: float = 10.0,
) -> dict:
    """Create chart from data range. type: bar, line, pie, area, scatter."""
    return engine.add_chart(
        file_path,
        sheet_name,
        chart_type,
        data_range,
        title,
        anchor_cell,
        width,
        height,
        open_after=True,
    )


@mcp.tool()
def delete_chart(
    file_path: str,
    sheet_name: str,
    chart_index: int,
) -> dict:
    """Remove chart by zero-based index from sheet."""
    return engine.delete_chart(file_path, sheet_name, chart_index, open_after=True)


@mcp.tool()
def update_chart(
    file_path: str,
    sheet_name: str,
    chart_index: int,
    title: str = "",
    data_range: str = "",
) -> dict:
    """Update chart title and/or data range by index."""
    return engine.update_chart(file_path, sheet_name, chart_index, title, data_range, open_after=True)


@mcp.tool()
def add_pivot_table(
    file_path: str,
    sheet_name: str,
    source_range: str,
    dest_cell: str,
    rows: str,
    cols: str,
    values: str,
) -> dict:
    """Create pivot summary table from source range data."""
    return engine.add_pivot_table(file_path, sheet_name, source_range, dest_cell, rows, cols, values, open_after=True)


@mcp.tool()
def set_cell_style(
    file_path: str,
    sheet_name: str,
    cell_address: str,
    font_name: str = "",
    font_size: float = 0,
    bold: bool = False,
    fill_color: str = "",
    number_format: str = "",
) -> dict:
    """Apply font, fill color, and number format styling to a cell."""
    return engine.set_cell_style(
        file_path,
        sheet_name,
        cell_address,
        font_name,
        font_size,
        bold,
        fill_color,
        number_format,
        open_after=True,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
