"""PPTX Design MCP server — thin wrapper over engine.py."""

import argparse
import os

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from pptx_design import engine
from shared.deploy_auth import build_auth, build_oauth_bridge

_VERSION = "0.1.1"  # keep in sync with pyproject.toml [project].version
_HOST = os.environ.get("OFFICE_PPTX_DESIGN_HOST", "127.0.0.1")
_PORT = int(os.environ.get("OFFICE_PPTX_DESIGN_PORT", "8839"))
_oauth_bridge = build_oauth_bridge(
    "OFFICE", state_dir=os.environ.get("OFFICE_PPTX_DESIGN_OAUTH_STATE_DIR", "/tmp/office-pptx-design-oauth-state")
)
_public_origin = os.environ.get("OFFICE_PUBLIC_URL", "").rstrip("/")
_public_url = f"{_public_origin}/pptx-design" if _public_origin else None
_token_verifier, _auth_settings = build_auth("OFFICE", _HOST, _PORT, _oauth_bridge, public_url=_public_url)

mcp = FastMCP(
    "pptx-design",
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
def set_background(
    file_path: str,
    slide_index: int,
    color_hex: str = "",
    image_path: str = "",
) -> dict:
    """Set slide background to color/image. slide_index -1 = all slides."""
    return engine.set_background(file_path, slide_index, color_hex, image_path, open_after=True)


@mcp.tool()
def set_font_style(
    file_path: str,
    slide_index: int,
    shape_name: str,
    font_name: str = "",
    font_size: float = 0,
    bold: bool = False,
    color_hex: str = "",
) -> dict:
    """Apply font name, size, bold, color to all runs in a shape."""
    return engine.set_font_style(
        file_path, slide_index, shape_name, font_name, font_size, bold, color_hex, open_after=True
    )


@mcp.tool()
def add_table(
    file_path: str,
    slide_index: int,
    rows: int,
    cols: int,
    data: list,
    left: float = 1.0,
    top: float = 2.0,
    width: float = 8.0,
    height: float = 3.0,
) -> dict:
    """Insert a table with row/col data on a slide."""
    return engine.add_table(file_path, slide_index, rows, cols, data, left, top, width, height, open_after=True)


@mcp.tool()
def add_chart(
    file_path: str,
    slide_index: int,
    chart_type: str,
    data: dict,
    title: str = "",
    left: float = 1.0,
    top: float = 2.0,
    width: float = 6.0,
    height: float = 4.5,
) -> dict:
    """Add chart to slide. type: bar, line, pie. data: {categories, series}."""
    return engine.add_chart(file_path, slide_index, chart_type, data, title, left, top, width, height, open_after=True)


@mcp.tool()
def duplicate_slide(
    file_path: str,
    slide_index: int,
    insert_at: int = -1,
) -> dict:
    """Copy slide N to position insert_at (-1 = append at end)."""
    return engine.duplicate_slide(file_path, slide_index, insert_at, open_after=True)


@mcp.tool()
def export_pdf(
    file_path: str,
    output_path: str = "",
    return_content: bool = False,
) -> dict:
    """Export .pptx to PDF (needs LibreOffice/PowerPoint). Can embed bytes."""
    return engine.export_pdf(file_path, output_path, open_after=True, return_content=return_content)


@mcp.tool()
def add_image_to_all_slides(
    file_path: str,
    image_path: str,
    left: float = 0.1,
    top: float = 0.1,
    width: float = 1.0,
    height: float = 0.5,
) -> dict:
    """Add the same image (logo/watermark) to every slide at given position."""
    return engine.add_image_to_all_slides(file_path, image_path, left, top, width, height, open_after=True)


@mcp.tool()
def set_font_all_slides(
    file_path: str,
    font_name: str = "",
    font_size: float = 0,
    bold: bool = False,
    color_hex: str = "",
) -> dict:
    """Apply font name/size/bold/color to every text run on all slides."""
    return engine.set_font_all_slides(file_path, font_name, font_size, bold, color_hex, open_after=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="pptx_design MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.environ.get("OFFICE_PPTX_DESIGN_TRANSPORT", "stdio"),
    )
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
