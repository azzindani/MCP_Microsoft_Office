"""XLSX New MCP server — create Excel workbooks from scratch."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from xlsx_new import engine

mcp = FastMCP("xlsx-new")


@mcp.tool()
def create_workbook(
    sheet_name: str = "Sheet1",
    output_path: str = "",
) -> dict:
    """Create a blank Excel workbook with one sheet."""
    return engine.create_workbook(output_path, sheet_name, open_after=False)


@mcp.tool()
def create_from_data(
    sheet_name: str,
    headers: list,
    rows: list,
    output_path: str = "",
) -> dict:
    """Create .xlsx from headers list and rows (list of lists)."""
    return engine.create_from_data(output_path, sheet_name, headers, rows, open_after=True)


@mcp.tool()
def create_report(
    title: str,
    sheets: list,
    output_path: str = "",
) -> dict:
    """Create multi-sheet .xlsx report from [{name,headers,rows}] list."""
    return engine.create_report(output_path, title, sheets, open_after=True)


@mcp.tool()
def create_from_template(
    template_path: str,
    replacements: dict,
    output_path: str = "",
) -> dict:
    """Copy .xlsx template, replace cell values, save to output_path."""
    return engine.create_from_template(template_path, output_path, replacements, open_after=True)


@mcp.tool()
def create_from_csv(
    csv_path: str,
    sheet_name: str = "Data",
    delimiter: str = ",",
    has_header: bool = True,
    output_path: str = "",
) -> dict:
    """Import a CSV file into a new Excel workbook."""
    return engine.create_from_csv(csv_path, output_path, sheet_name, delimiter, has_header, open_after=True)


@mcp.tool()
def create_invoice(
    company_name: str,
    client_name: str,
    invoice_number: str,
    items: list,
    tax_rate: float = 0.0,
    currency: str = "USD",
    output_path: str = "",
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
        open_after=True,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
