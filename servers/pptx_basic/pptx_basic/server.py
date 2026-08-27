"""PPTX Basic MCP server — thin wrapper over engine.py."""

import argparse
import os

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from pptx_basic import engine
from shared.deploy_auth import build_auth, build_oauth_bridge
from shared.strict_args import enforce_known_arguments
from shared.token_estimate import measure_responses
from shared.tool_annotations import EDITS, READS

_VERSION = "0.1.1"  # keep in sync with pyproject.toml [project].version
_HOST = os.environ.get("OFFICE_PPTX_BASIC_HOST", "127.0.0.1")
_PORT = int(os.environ.get("OFFICE_PPTX_BASIC_PORT", "8838"))
_oauth_bridge = build_oauth_bridge(
    "OFFICE", state_dir=os.environ.get("OFFICE_PPTX_BASIC_OAUTH_STATE_DIR", "/tmp/office-pptx-basic-oauth-state")
)
_public_origin = os.environ.get("OFFICE_PUBLIC_URL", "").rstrip("/")
_public_url = f"{_public_origin}/pptx-basic" if _public_origin else None
_token_verifier, _auth_settings = build_auth("OFFICE", _HOST, _PORT, _oauth_bridge, public_url=_public_url)

mcp = FastMCP(
    "pptx-basic",
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
def read_presentation(file_path: str) -> dict:
    """Read presentation index: slides, layouts, and structure."""
    return engine.read_presentation(file_path)


@mcp.tool(annotations=READS)
def read_slide(file_path: str, slide_index: int) -> dict:
    """Read all shapes on one slide with name, type, and text."""
    return engine.read_slide(file_path, slide_index)


@mcp.tool(annotations=READS)
def search_slides(file_path: str, query: str) -> dict:
    """Search all slides for query text, return matching shapes."""
    return engine.search_slides(file_path, query)


@mcp.tool(annotations=READS)
def read_slide_text(file_path: str, slide_index: int) -> dict:
    """Return text of all shapes on one slide (no formatting)."""
    return engine.read_slide_text(file_path, slide_index)


@mcp.tool(annotations=EDITS)
def set_text(file_path: str, slide_index: int, shape_name: str, new_text: str) -> dict:
    """Replace shape text using run-level editing."""
    return engine.set_text(file_path, slide_index, shape_name, new_text, open_after=True)


@mcp.tool(annotations=EDITS)
def add_slide(file_path: str, layout_name: str, title: str = "", body: str = "") -> dict:
    """Append a slide with given layout, title, and body text."""
    return engine.add_slide(file_path, layout_name, title, body, open_after=True)


@mcp.tool(annotations=EDITS)
def delete_slide(file_path: str, slide_index: int) -> dict:
    """Remove a slide by index."""
    return engine.delete_slide(file_path, slide_index, open_after=True)


@mcp.tool(annotations=EDITS)
def reorder_slide(file_path: str, from_index: int, to_index: int) -> dict:
    """Move a slide from one position to another."""
    return engine.reorder_slide(file_path, from_index, to_index, open_after=True)


@mcp.tool(annotations=EDITS)
def add_text_box(
    file_path: str,
    slide_index: int,
    text: str,
    left: float = 1.0,
    top: float = 1.0,
    width: float = 5.0,
    height: float = 1.0,
) -> dict:
    """Add a text box to a slide at given position in inches."""
    return engine.add_text_box(file_path, slide_index, text, left, top, width, height, open_after=True)


@mcp.tool(annotations=READS)
def diff_versions(file_path: str, timestamp_a: str, timestamp_b: str = "current") -> dict:
    """Compare two presentation versions by snapshot timestamp."""
    return engine.diff_versions(file_path, timestamp_a, timestamp_b)


# The bundled FastMCP ignores an argument a tool does not declare, so a wrong
# name yields a plausible answer with the argument silently dropped. Refuse it,
# and name the ones that would have worked.
enforce_known_arguments(mcp)
measure_responses(mcp)


def main() -> None:
    parser = argparse.ArgumentParser(description="pptx_basic MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.environ.get("OFFICE_PPTX_BASIC_TRANSPORT", "stdio"),
    )
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
