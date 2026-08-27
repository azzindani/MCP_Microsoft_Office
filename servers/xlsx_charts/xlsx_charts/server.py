"""XLSX Charts MCP server — thin wrapper over engine.py."""

import argparse
import os

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from shared.deploy_auth import build_auth, build_oauth_bridge
from shared.strict_args import enforce_known_arguments
from shared.token_estimate import measure_responses
from shared.tool_annotations import EDITS
from xlsx_charts import engine

_VERSION = "0.1.1"  # keep in sync with pyproject.toml [project].version
_HOST = os.environ.get("OFFICE_XLSX_CHARTS_HOST", "127.0.0.1")
_PORT = int(os.environ.get("OFFICE_XLSX_CHARTS_PORT", "8836"))
_oauth_bridge = build_oauth_bridge(
    "OFFICE", state_dir=os.environ.get("OFFICE_XLSX_CHARTS_OAUTH_STATE_DIR", "/tmp/office-xlsx-charts-oauth-state")
)
_public_origin = os.environ.get("OFFICE_PUBLIC_URL", "").rstrip("/")
_public_url = f"{_public_origin}/xlsx-charts" if _public_origin else None
_token_verifier, _auth_settings = build_auth("OFFICE", _HOST, _PORT, _oauth_bridge, public_url=_public_url)

mcp = FastMCP(
    "xlsx-charts",
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


@mcp.tool(annotations=EDITS)
def add_chart(
    file_path: str,
    sheet_name: str,
    chart_type: str,
    data_range: str,
    title: str = "",
    anchor_cell: str = "",
    width: float = 15.0,
    height: float = 10.0,
    dest_cell: str = "",
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
        dest_cell=dest_cell,
    )


@mcp.tool(annotations=EDITS)
def delete_chart(
    file_path: str,
    sheet_name: str,
    chart_index: int,
) -> dict:
    """Remove chart by zero-based index from sheet."""
    return engine.delete_chart(file_path, sheet_name, chart_index, open_after=True)


@mcp.tool(annotations=EDITS)
def update_chart(
    file_path: str,
    sheet_name: str,
    chart_index: int,
    title: str = "",
    data_range: str = "",
) -> dict:
    """Update chart title and/or data range by index."""
    return engine.update_chart(file_path, sheet_name, chart_index, title, data_range, open_after=True)


@mcp.tool(annotations=EDITS)
def add_pivot_table(
    file_path: str,
    sheet_name: str,
    source_range: str = "",
    dest_cell: str = "",
    rows: str = "",
    values: str = "",
    cols: str = "",
    anchor_cell: str = "",
) -> dict:
    """Sum values per rows group. cols optional: adds a second axis."""
    return engine.add_pivot_table(
        file_path,
        sheet_name,
        source_range,
        dest_cell,
        rows,
        cols,
        values,
        open_after=True,
        anchor_cell=anchor_cell,
    )


@mcp.tool(annotations=EDITS)
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


# The bundled FastMCP ignores an argument a tool does not declare, so a wrong
# name yields a plausible answer with the argument silently dropped. Refuse it,
# and name the ones that would have worked.
enforce_known_arguments(mcp)
measure_responses(mcp)


def main() -> None:
    parser = argparse.ArgumentParser(description="xlsx_charts MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.environ.get("OFFICE_XLSX_CHARTS_TRANSPORT", "stdio"),
    )
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
