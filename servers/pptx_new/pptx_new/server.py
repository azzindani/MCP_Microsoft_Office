"""PPTX New MCP server — create PowerPoint presentations from scratch."""

from __future__ import annotations

import argparse
import os

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from pptx_new import engine
from shared.deploy_auth import build_auth

_VERSION = "0.1.0"  # keep in sync with pyproject.toml [project].version
_HOST = os.environ.get("OFFICE_PPTX_NEW_HOST", "127.0.0.1")
_PORT = int(os.environ.get("OFFICE_PPTX_NEW_PORT", "8840"))
_token_verifier, _auth_settings = build_auth("OFFICE", _HOST, _PORT)

mcp = FastMCP(
    "pptx-new",
    host=_HOST,
    port=_PORT,
    token_verifier=_token_verifier,
    auth=_auth_settings,
)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    """Liveness check. Unauthenticated."""
    return JSONResponse({"status": "ok", "version": _VERSION})


@mcp.custom_route("/version", methods=["GET"])
async def version(request: Request) -> JSONResponse:
    """Report running version. Unauthenticated."""
    return JSONResponse({"current": _VERSION})


@mcp.tool()
def create_presentation(
    title: str = "",
    subtitle: str = "",
    output_path: str = "",
) -> dict:
    """Create a blank PowerPoint with a title slide."""
    return engine.create_presentation(output_path, title, subtitle, open_after=False)


@mcp.tool()
def create_from_outline(
    slides: list[dict],
    output_path: str = "",
) -> dict:
    """Create .pptx from [{title, content, layout}] slide list."""
    return engine.create_from_outline(output_path, slides, open_after=True)


@mcp.tool()
def create_deck_from_data(
    title: str,
    data_slides: list[dict],
    output_path: str = "",
) -> dict:
    """Create .pptx deck from title + [{heading, bullets}] list."""
    return engine.create_deck_from_data(output_path, title, data_slides, open_after=True)


@mcp.tool()
def create_from_template(
    template_path: str,
    output_path: str = "",
) -> dict:
    """Copy .pptx template to output_path as starting point."""
    return engine.create_from_template(template_path, output_path, open_after=True)


@mcp.tool()
def create_agenda(
    meeting_title: str,
    date: str,
    items: list,
    presenter: str = "",
    output_path: str = "",
) -> dict:
    """Create a meeting agenda .pptx from a list of {topic,duration,owner} items."""
    return engine.create_agenda(output_path, meeting_title, date, items, presenter, open_after=True)


@mcp.tool()
def create_from_docx(
    docx_path: str,
    max_slides: int = 20,
    output_path: str = "",
) -> dict:
    """Convert a Word document outline into a PowerPoint presentation."""
    return engine.create_from_docx(docx_path, output_path, max_slides, open_after=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="pptx_new MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.environ.get("OFFICE_PPTX_NEW_TRANSPORT", "stdio"),
    )
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
