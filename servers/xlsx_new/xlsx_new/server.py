"""XLSX New MCP server — create Excel workbooks from scratch."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from xlsx_new import engine

mcp = FastMCP("xlsx-new")


@mcp.tool()
def create_workbook(
    output_path: str,
    sheet_name: str = "Sheet1",
    open_after: bool = True,
) -> dict:
    """Create a blank Excel workbook with one sheet."""
    return engine.create_workbook(output_path, sheet_name, open_after)


@mcp.tool()
def create_from_data(
    output_path: str,
    sheet_name: str,
    headers: list,
    rows: list,
    open_after: bool = True,
) -> dict:
    """Create .xlsx from headers list and rows (list of lists)."""
    return engine.create_from_data(output_path, sheet_name, headers, rows, open_after)


@mcp.tool()
def create_report(
    output_path: str,
    title: str,
    sheets: list,
    open_after: bool = True,
) -> dict:
    """Create multi-sheet .xlsx report from [{name,headers,rows}] list."""
    return engine.create_report(output_path, title, sheets, open_after)


@mcp.tool()
def create_from_template(
    template_path: str,
    output_path: str,
    replacements: dict,
    open_after: bool = True,
) -> dict:
    """Copy .xlsx template, replace cell values, save to output_path."""
    return engine.create_from_template(template_path, output_path, replacements, open_after)


@mcp.tool()
def create_from_csv(
    csv_path: str,
    output_path: str,
    sheet_name: str = "Data",
    delimiter: str = ",",
    has_header: bool = True,
    open_after: bool = True,
) -> dict:
    """Import a CSV file into a new Excel workbook."""
    return engine.create_from_csv(
        csv_path, output_path, sheet_name, delimiter, has_header, open_after
    )


@mcp.tool()
def create_invoice(
    output_path: str,
    company_name: str,
    client_name: str,
    invoice_number: str,
    items: list,
    tax_rate: float = 0.0,
    currency: str = "USD",
    open_after: bool = True,
) -> dict:
    """Create a formatted invoice .xlsx with items, totals, and tax formula."""
    return engine.create_invoice(
        output_path,
        company_name,
        client_name,
        invoice_number,
        items,
        tax_rate,
        currency,
        open_after,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
