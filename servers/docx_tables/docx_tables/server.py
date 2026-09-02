"""DOCX Tables MCP server — thin wrapper over engine.py."""

import argparse
import os

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from docx_tables import engine
from shared.arg_errors import contract_errors
from shared.deploy_auth import build_auth, build_oauth_bridge
from shared.strict_args import enforce_known_arguments
from shared.token_estimate import measure_responses
from shared.tool_annotations import EDITS, READS

_VERSION = "0.1.2"  # keep in sync with pyproject.toml [project].version
_HOST = os.environ.get("OFFICE_DOCX_TABLES_HOST", "127.0.0.1")
_PORT = int(os.environ.get("OFFICE_DOCX_TABLES_PORT", "8831"))
_oauth_bridge = build_oauth_bridge(
    "OFFICE", state_dir=os.environ.get("OFFICE_DOCX_TABLES_OAUTH_STATE_DIR", "/tmp/office-docx-tables-oauth-state")
)
_public_origin = os.environ.get("OFFICE_PUBLIC_URL", "").rstrip("/")
_public_url = f"{_public_origin}/docx-tables" if _public_origin else None
_token_verifier, _auth_settings = build_auth("OFFICE", _HOST, _PORT, _oauth_bridge, public_url=_public_url)

mcp = FastMCP(
    "docx-tables",
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


@mcp.tool(annotations=READS)
def list_tables(file_path: str) -> dict:
    """List all tables with row/column dimensions."""
    return engine.list_tables(file_path)


@mcp.tool(annotations=READS)
def read_table(file_path: str, table_index: int) -> dict:
    """Return the full 2-D cell array. Args: table_index (0-based)."""
    return engine.read_table(file_path, table_index)


@mcp.tool(annotations=READS)
def search_table_cells(file_path: str, query: str, max_results: int = 10) -> dict:
    """Scan all table cells for matching text. Returns coordinates."""
    return engine.search_table_cells(file_path, query, max_results)


@mcp.tool(annotations=READS)
def read_table_row(file_path: str, table_index: int, row: int) -> dict:
    """Return one table row. Args: table_index, row (both 0-based)."""
    return engine.read_table_row(file_path, table_index, row)


@mcp.tool(annotations=EDITS)
def set_cell(file_path: str, table_index: int, row: int, col: int, text: str) -> dict:
    """Write text to one cell. Args: table_index, row, col, text."""
    return engine.set_cell(file_path, table_index, row, col, text, open_after=True)


@mcp.tool(annotations=EDITS)
def add_row(file_path: str, table_index: int, data: list[str]) -> dict:
    """Append a row. Args: table_index, data (list of cell strings)."""
    return engine.add_row(file_path, table_index, data, open_after=True)


@mcp.tool(annotations=EDITS)
def delete_row(file_path: str, table_index: int, row: int) -> dict:
    """Remove a row; rows below shift up. Args: table_index, row."""
    return engine.delete_row(file_path, table_index, row, open_after=True)


@mcp.tool(annotations=EDITS)
def add_table(
    file_path: str,
    after_paragraph_index: int,
    rows: int,
    cols: int,
    data: list[list[str]] | None = None,
) -> dict:
    """Insert table after paragraph N (-1 = first). Args: rows, cols, data."""
    return engine.add_table(file_path, after_paragraph_index, rows, cols, data, open_after=True)


@mcp.tool(annotations=EDITS)
def delete_table(file_path: str, table_index: int) -> dict:
    """Remove one table entirely. Args: table_index (0-based)."""
    return engine.delete_table(file_path, table_index, open_after=True)


@mcp.tool(annotations=EDITS)
def set_cell_style(
    file_path: str,
    table_index: int,
    fill: str = "",
    bold: str = "",
    color: str = "",
    align: str = "",
    row: int = -1,
    col: int = -1,
    band_fill: str = "",
) -> dict:
    """Shade/format cells. Hex colors. row/col -1 = all. band_fill stripes."""
    return engine.set_cell_style(file_path, table_index, fill, bold, color, align, row, col, band_fill, open_after=True)


# The bundled FastMCP ignores an argument a tool does not declare, so a wrong
# name yields a plausible answer with the argument silently dropped. Refuse it,
# and name the ones that would have worked.
enforce_known_arguments(mcp)
# A known argument with the WRONG TYPE is rejected by pydantic before any of
# this runs, and used to escape as a raw dump with no success/hint/token_estimate
# and a pydantic.dev URL. Give it the fleet's failure shape instead.
contract_errors(mcp)
measure_responses(mcp)


def main() -> None:
    parser = argparse.ArgumentParser(description="docx_tables MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.environ.get("OFFICE_DOCX_TABLES_TRANSPORT", "stdio"),
    )
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
