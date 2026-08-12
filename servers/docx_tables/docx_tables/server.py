"""DOCX Tables MCP server — thin wrapper over engine.py."""

import argparse
import os

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from docx_tables import engine
from shared.deploy_auth import build_auth, build_oauth_bridge

_VERSION = "0.1.1"  # keep in sync with pyproject.toml [project].version
_HOST = os.environ.get("OFFICE_DOCX_TABLES_HOST", "127.0.0.1")
_PORT = int(os.environ.get("OFFICE_DOCX_TABLES_PORT", "8831"))
_oauth_bridge = build_oauth_bridge(
    "OFFICE", state_dir=os.environ.get("OFFICE_DOCX_TABLES_OAUTH_STATE_DIR", "/tmp/office-docx-tables-oauth-state")
)
_token_verifier, _auth_settings = build_auth("OFFICE", _HOST, _PORT, _oauth_bridge)

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


@mcp.tool()
def list_tables(file_path: str) -> dict:
    """List all tables with row/column dimensions."""
    return engine.list_tables(file_path)


@mcp.tool()
def read_table(file_path: str, table_index: int) -> dict:
    """Return full 2-D cell array for one table."""
    return engine.read_table(file_path, table_index)


@mcp.tool()
def search_table_cells(file_path: str, query: str, max_results: int = 10) -> dict:
    """Scan all table cells for matching text. Returns coordinates."""
    return engine.search_table_cells(file_path, query, max_results)


@mcp.tool()
def read_table_row(file_path: str, table_index: int, row: int) -> dict:
    """Return all cells in one table row."""
    return engine.read_table_row(file_path, table_index, row)


@mcp.tool()
def set_cell(file_path: str, table_index: int, row: int, col: int, text: str) -> dict:
    """Write text to a specific table cell. Snapshot taken before write."""
    return engine.set_cell(file_path, table_index, row, col, text, open_after=True)


@mcp.tool()
def add_row(file_path: str, table_index: int, data: list[str]) -> dict:
    """Append a row to table N. data is a list of cell text strings."""
    return engine.add_row(file_path, table_index, data, open_after=True)


@mcp.tool()
def delete_row(file_path: str, table_index: int, row: int) -> dict:
    """Remove row R from table N. Rows below shift up."""
    return engine.delete_row(file_path, table_index, row, open_after=True)


@mcp.tool()
def add_table(
    file_path: str,
    after_paragraph_index: int,
    rows: int,
    cols: int,
    data: list[list[str]] | None = None,
) -> dict:
    """Insert new table after paragraph N. data is optional rows×cols list."""
    return engine.add_table(file_path, after_paragraph_index, rows, cols, data, open_after=True)


@mcp.tool()
def delete_table(file_path: str, table_index: int) -> dict:
    """Remove table N from the document entirely."""
    return engine.delete_table(file_path, table_index, open_after=True)


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
