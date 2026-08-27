"""XLSX Formulas MCP server — thin wrapper over engine.py."""

import argparse
import os

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from shared.deploy_auth import build_auth, build_oauth_bridge
from shared.strict_args import enforce_known_arguments
from shared.token_estimate import measure_responses
from shared.tool_annotations import EDITS
from xlsx_formulas import engine

_VERSION = "0.1.1"  # keep in sync with pyproject.toml [project].version
_HOST = os.environ.get("OFFICE_XLSX_FORMULAS_HOST", "127.0.0.1")
_PORT = int(os.environ.get("OFFICE_XLSX_FORMULAS_PORT", "8835"))
_oauth_bridge = build_oauth_bridge(
    "OFFICE", state_dir=os.environ.get("OFFICE_XLSX_FORMULAS_OAUTH_STATE_DIR", "/tmp/office-xlsx-formulas-oauth-state")
)
_public_origin = os.environ.get("OFFICE_PUBLIC_URL", "").rstrip("/")
_public_url = f"{_public_origin}/xlsx-formulas" if _public_origin else None
_token_verifier, _auth_settings = build_auth("OFFICE", _HOST, _PORT, _oauth_bridge, public_url=_public_url)

mcp = FastMCP(
    "xlsx-formulas",
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
def set_formula(
    file_path: str,
    sheet_name: str,
    cell_address: str,
    formula: str,
) -> dict:
    """Write formula to cell. Formula must start with '='."""
    return engine.set_formula(file_path, sheet_name, cell_address, formula, open_after=True)


@mcp.tool(annotations=EDITS)
def set_named_range(
    file_path: str,
    sheet_name: str,
    range_name: str,
    range_address: str,
) -> dict:
    """Define a named range in the workbook."""
    return engine.set_named_range(file_path, sheet_name, range_name, range_address, open_after=True)


@mcp.tool(annotations=EDITS)
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
        file_path, sheet_name, range_address, rule, value, color, value2, open_after=True
    )


@mcp.tool(annotations=EDITS)
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
        file_path, sheet_name, range_address, validation_type, formula1, formula2, open_after=True
    )


@mcp.tool(annotations=EDITS)
def freeze_panes(
    file_path: str,
    sheet_name: str,
    cell_address: str,
) -> dict:
    """Freeze rows/columns at cell. Empty string to unfreeze."""
    return engine.freeze_panes(file_path, sheet_name, cell_address, open_after=True)


@mcp.tool(annotations=EDITS)
def set_autofilter(
    file_path: str,
    sheet_name: str,
    range_address: str,
) -> dict:
    """Enable AutoFilter on header row range."""
    return engine.set_autofilter(file_path, sheet_name, range_address, open_after=True)


@mcp.tool(annotations=EDITS)
def fill_formula_down(
    file_path: str,
    sheet_name: str,
    formula: str,
    start_cell: str,
    end_row: int,
) -> dict:
    """Fill formula down from start_cell to end_row, adjusting row refs."""
    return engine.fill_formula_down(file_path, sheet_name, formula, start_cell, end_row, open_after=True)


@mcp.tool(annotations=EDITS)
def auto_sum(
    file_path: str,
    sheet_name: str,
    data_range: str,
    sum_cell: str,
    function_name: str = "SUM",
) -> dict:
    """Add SUM/AVERAGE/COUNT/MAX/MIN formula for a range into sum_cell."""
    return engine.auto_sum(file_path, sheet_name, data_range, sum_cell, function_name, open_after=True)


@mcp.tool(annotations=EDITS)
def convert_to_values(
    file_path: str,
    sheet_name: str,
    range_address: str,
) -> dict:
    """Replace formulas with their calculated values in a range."""
    return engine.convert_to_values(file_path, sheet_name, range_address, open_after=True)


# The bundled FastMCP ignores an argument a tool does not declare, so a wrong
# name yields a plausible answer with the argument silently dropped. Refuse it,
# and name the ones that would have worked.
enforce_known_arguments(mcp)
measure_responses(mcp)


def main() -> None:
    parser = argparse.ArgumentParser(description="xlsx_formulas MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.environ.get("OFFICE_XLSX_FORMULAS_TRANSPORT", "stdio"),
    )
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
