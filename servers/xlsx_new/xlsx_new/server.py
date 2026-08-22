"""XLSX New MCP server — create Excel workbooks from scratch."""

from __future__ import annotations

import argparse
import os

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from shared.deploy_auth import build_auth, build_oauth_bridge
from xlsx_new import engine

_VERSION = "0.1.1"  # keep in sync with pyproject.toml [project].version
_HOST = os.environ.get("OFFICE_XLSX_NEW_HOST", "127.0.0.1")
_PORT = int(os.environ.get("OFFICE_XLSX_NEW_PORT", "8837"))
_oauth_bridge = build_oauth_bridge(
    "OFFICE", state_dir=os.environ.get("OFFICE_XLSX_NEW_OAUTH_STATE_DIR", "/tmp/office-xlsx-new-oauth-state")
)
_public_origin = os.environ.get("OFFICE_PUBLIC_URL", "").rstrip("/")
_public_url = f"{_public_origin}/xlsx-new" if _public_origin else None
_token_verifier, _auth_settings = build_auth("OFFICE", _HOST, _PORT, _oauth_bridge, public_url=_public_url)

mcp = FastMCP(
    "xlsx-new",
    host=_HOST,
    port=_PORT,
    token_verifier=_token_verifier,
    auth=_auth_settings,
)
if _oauth_bridge is not None:
    _oauth_bridge.register_routes(mcp)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    """Liveness check. Unauthenticated."""
    return JSONResponse({"status": "ok", "version": _VERSION})


@mcp.custom_route("/version", methods=["GET"])
async def version(request: Request) -> JSONResponse:
    """Report running version. Unauthenticated."""
    return JSONResponse({"current": _VERSION})


@mcp.tool()
def create_workbook(
    sheet_name: str = "Sheet1",
    output_path: str = "",
    return_content: bool = False,
) -> dict:
    """Create blank .xlsx. return_content=True embeds file bytes (remote)."""
    return engine.create_workbook(output_path, sheet_name, open_after=False, return_content=return_content)


@mcp.tool()
def create_from_data(
    sheet_name: str,
    headers: list,
    rows: list,
    output_path: str = "",
    return_content: bool = False,
) -> dict:
    """Create .xlsx from headers+rows. return_content=True embeds bytes."""
    return engine.create_from_data(
        output_path, sheet_name, headers, rows, open_after=True, return_content=return_content
    )


@mcp.tool()
def create_report(
    title: str,
    sheets: list,
    output_path: str = "",
    return_content: bool = False,
) -> dict:
    """Create multi-sheet .xlsx report from [{name,headers,rows}] list."""
    return engine.create_report(output_path, title, sheets, open_after=True, return_content=return_content)


@mcp.tool()
def create_from_template(
    template_path: str,
    substitutions: dict = {},  # noqa: B006 -- read-only; engine only iterates it
    output_path: str = "",
    return_content: bool = False,
) -> dict:
    """Copy .xlsx template, fill {key: value} substitutions, save."""
    return engine.create_from_template(
        template_path, output_path, substitutions, open_after=True, return_content=return_content
    )


@mcp.tool()
def create_from_csv(
    csv_path: str,
    sheet_name: str = "Data",
    delimiter: str = ",",
    has_header: bool = True,
    output_path: str = "",
    return_content: bool = False,
) -> dict:
    """Import a CSV file into a new Excel workbook."""
    return engine.create_from_csv(
        csv_path,
        output_path,
        sheet_name,
        delimiter,
        has_header,
        open_after=True,
        return_content=return_content,
    )


@mcp.tool()
def create_invoice(
    company_name: str,
    client_name: str,
    invoice_number: str,
    items: list,
    tax_rate: float = 0.0,
    currency: str = "USD",
    output_path: str = "",
    return_content: bool = False,
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
        return_content=return_content,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="xlsx_new MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.environ.get("OFFICE_XLSX_NEW_TRANSPORT", "stdio"),
    )
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
