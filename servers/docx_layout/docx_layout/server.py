"""DOCX Layout MCP server — styles, fonts, margins, images, export."""

import argparse
import os

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from docx_layout import engine
from shared.deploy_auth import build_auth, build_oauth_bridge

_VERSION = "0.1.1"  # keep in sync with pyproject.toml [project].version
_HOST = os.environ.get("OFFICE_DOCX_LAYOUT_HOST", "127.0.0.1")
_PORT = int(os.environ.get("OFFICE_DOCX_LAYOUT_PORT", "8832"))
_oauth_bridge = build_oauth_bridge(
    "OFFICE", state_dir=os.environ.get("OFFICE_DOCX_LAYOUT_OAUTH_STATE_DIR", "/tmp/office-docx-layout-oauth-state")
)
_token_verifier, _auth_settings = build_auth("OFFICE", _HOST, _PORT, _oauth_bridge)

mcp = FastMCP(
    "docx-layout",
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
def set_heading(file_path: str, paragraph_index: int, level: int) -> dict:
    """Apply Heading 1-6 style to paragraph N. level must be 1-6."""
    return engine.set_heading(file_path, paragraph_index, level, open_after=True)


@mcp.tool()
def set_font(
    file_path: str,
    paragraph_index: int,
    font_name: str = "",
    font_size: float = 0,
    bold: bool = False,
    italic: bool = False,
) -> dict:
    """Set font name/size/bold/italic on all runs in paragraph N."""
    return engine.set_font(file_path, paragraph_index, font_name, font_size, bold, italic, open_after=True)


@mcp.tool()
def set_paragraph_style(file_path: str, paragraph_index: int, style_name: str) -> dict:
    """Apply named style from document gallery to paragraph N."""
    return engine.set_paragraph_style(file_path, paragraph_index, style_name, open_after=True)


@mcp.tool()
def add_image(
    file_path: str,
    paragraph_index: int,
    image_path: str,
    width_inches: float = 4.0,
) -> dict:
    """Insert image into paragraph N. Formats: PNG, JPG, GIF, BMP, TIFF."""
    return engine.add_image(file_path, paragraph_index, image_path, width_inches, open_after=True)


@mcp.tool()
def set_page_margins(
    file_path: str,
    top: float = 2.54,
    bottom: float = 2.54,
    left: float = 2.54,
    right: float = 2.54,
) -> dict:
    """Set page margins in cm (top/bottom/left/right) for all sections."""
    return engine.set_page_margins(file_path, top, bottom, left, right, open_after=True)


@mcp.tool()
def add_header_footer(
    file_path: str,
    text: str,
    location: str = "header",
) -> dict:
    """Set header or footer text. location: 'header' or 'footer'."""
    return engine.add_header_footer(file_path, text, location, open_after=True)


@mcp.tool()
def export_pdf(file_path: str, output_path: str = "") -> dict:
    """Export .docx to PDF. Requires Word (Win/Mac) or LibreOffice."""
    return engine.export_pdf(file_path, output_path, open_after=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="docx_layout MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.environ.get("OFFICE_DOCX_LAYOUT_TRANSPORT", "stdio"),
    )
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
