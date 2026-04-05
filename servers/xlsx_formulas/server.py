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
) -> dict:
    """Write formula to cell. Formula must start with '='."""
    return engine.set_formula(file_path, sheet_name, cell_address, formula)


@mcp.tool()
def set_named_range(
    file_path: str,
    sheet_name: str,
    range_name: str,
    range_address: str,
) -> dict:
    """Define a named range in the workbook."""
    return engine.set_named_range(file_path, sheet_name, range_name, range_address)


@mcp.tool()
def set_conditional_format(
    file_path: str,
    sheet_name: str,
    range_address: str,
    rule: str,
    value: float,
    color: str,
    value2: float = 0.0,
) -> dict:
    """Apply color rule to range. rule: gt/lt/between/eq. color: green/red/yellow/blue."""
    return engine.set_conditional_format(
        file_path, sheet_name, range_address, rule, value, color, value2
    )


@mcp.tool()
def set_data_validation(
    file_path: str,
    sheet_name: str,
    range_address: str,
    validation_type: str,
    formula1: str = "",
    formula2: str = "",
) -> dict:
    """Add data validation to range. type: list, decimal, whole."""
    return engine.set_data_validation(
        file_path, sheet_name, range_address, validation_type, formula1, formula2
    )


@mcp.tool()
def freeze_panes(
    file_path: str,
    sheet_name: str,
    cell_address: str,
) -> dict:
    """Freeze rows/columns at cell. Empty string to unfreeze."""
    return engine.freeze_panes(file_path, sheet_name, cell_address)


@mcp.tool()
def set_autofilter(
    file_path: str,
    sheet_name: str,
    range_address: str,
) -> dict:
    """Enable AutoFilter on header row range."""
    return engine.set_autofilter(file_path, sheet_name, range_address)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
