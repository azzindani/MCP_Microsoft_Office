"""XLSX Formulas MCP server — thin wrapper over engine.py."""

from mcp.server.fastmcp import FastMCP

from xlsx_formulas import engine

mcp = FastMCP("xlsx-formulas")


@mcp.tool()
def set_formula(
    file_path: str,
    sheet_name: str,
    cell_address: str,
    formula: str,
    open_after: bool = False,
) -> dict:
    """Write formula to cell. Formula must start with '='."""
    return engine.set_formula(file_path, sheet_name, cell_address, formula, open_after)


@mcp.tool()
def set_named_range(
    file_path: str,
    sheet_name: str,
    range_name: str,
    range_address: str,
    open_after: bool = False,
) -> dict:
    """Define a named range in the workbook."""
    return engine.set_named_range(file_path, sheet_name, range_name, range_address, open_after)


@mcp.tool()
def set_conditional_format(
    file_path: str,
    sheet_name: str,
    range_address: str,
    rule: str,
    value: float,
    color: str,
    value2: float = 0.0,
    open_after: bool = False,
) -> dict:
    """Apply color rule to range. rule: gt/lt/between/eq. color: green/red/yellow/blue."""
    return engine.set_conditional_format(
        file_path, sheet_name, range_address, rule, value, color, value2, open_after
    )


@mcp.tool()
def set_data_validation(
    file_path: str,
    sheet_name: str,
    range_address: str,
    validation_type: str,
    formula1: str = "",
    formula2: str = "",
    open_after: bool = False,
) -> dict:
    """Add data validation to range. type: list, decimal, whole."""
    return engine.set_data_validation(
        file_path, sheet_name, range_address, validation_type, formula1, formula2, open_after
    )


@mcp.tool()
def freeze_panes(
    file_path: str,
    sheet_name: str,
    cell_address: str,
    open_after: bool = False,
) -> dict:
    """Freeze rows/columns at cell. Empty string to unfreeze."""
    return engine.freeze_panes(file_path, sheet_name, cell_address, open_after)


@mcp.tool()
def set_autofilter(
    file_path: str,
    sheet_name: str,
    range_address: str,
    open_after: bool = False,
) -> dict:
    """Enable AutoFilter on header row range."""
    return engine.set_autofilter(file_path, sheet_name, range_address, open_after)


@mcp.tool()
def fill_formula_down(
    file_path: str,
    sheet_name: str,
    formula: str,
    start_cell: str,
    end_row: int,
    open_after: bool = False,
) -> dict:
    """Fill formula down from start_cell to end_row, adjusting row refs."""
    return engine.fill_formula_down(file_path, sheet_name, formula, start_cell, end_row, open_after)


@mcp.tool()
def auto_sum(
    file_path: str,
    sheet_name: str,
    data_range: str,
    sum_cell: str,
    function_name: str = "SUM",
    open_after: bool = False,
) -> dict:
    """Add SUM/AVERAGE/COUNT/MAX/MIN formula for a range into sum_cell."""
    return engine.auto_sum(file_path, sheet_name, data_range, sum_cell, function_name, open_after)


@mcp.tool()
def convert_to_values(
    file_path: str,
    sheet_name: str,
    range_address: str,
    open_after: bool = False,
) -> dict:
    """Replace formulas with their calculated values in a range."""
    return engine.convert_to_values(file_path, sheet_name, range_address, open_after)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
