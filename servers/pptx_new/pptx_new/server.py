"""PPTX New MCP server — create PowerPoint presentations from scratch."""

from __future__ import annotations

import argparse
import os

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from pptx_new import engine
from shared.arg_errors import contract_errors
from shared.deploy_auth import build_auth, build_oauth_bridge
from shared.strict_args import enforce_known_arguments
from shared.token_estimate import measure_responses
from shared.tool_annotations import CREATES

_VERSION = "0.1.2"  # keep in sync with pyproject.toml [project].version
_HOST = os.environ.get("OFFICE_PPTX_NEW_HOST", "127.0.0.1")
_PORT = int(os.environ.get("OFFICE_PPTX_NEW_PORT", "8840"))
_oauth_bridge = build_oauth_bridge(
    "OFFICE", state_dir=os.environ.get("OFFICE_PPTX_NEW_OAUTH_STATE_DIR", "/tmp/office-pptx-new-oauth-state")
)
_public_origin = os.environ.get("OFFICE_PUBLIC_URL", "").rstrip("/")
_public_url = f"{_public_origin}/pptx-new" if _public_origin else None
_token_verifier, _auth_settings = build_auth("OFFICE", _HOST, _PORT, _oauth_bridge, public_url=_public_url)

mcp = FastMCP(
    "pptx-new",
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


@mcp.tool(annotations=CREATES)
def create_presentation(
    title: str = "",
    subtitle: str = "",
    output_path: str = "",
    return_content: bool = False,
) -> dict:
    """Create blank .pptx w/ title slide. return_content=True embeds bytes."""
    return engine.create_presentation(output_path, title, subtitle, open_after=False, return_content=return_content)


@mcp.tool(annotations=CREATES)
def create_from_outline(
    slides: list[dict],
    output_path: str = "",
    return_content: bool = False,
) -> dict:
    """Create .pptx from [{title, content, layout}] slide list."""
    return engine.create_from_outline(output_path, slides, open_after=True, return_content=return_content)


@mcp.tool(annotations=CREATES)
def create_deck_from_data(
    title: str,
    data_slides: list[dict],
    output_path: str = "",
    return_content: bool = False,
) -> dict:
    """Create .pptx deck from title + [{heading, bullets}] list."""
    return engine.create_deck_from_data(output_path, title, data_slides, open_after=True, return_content=return_content)


@mcp.tool(annotations=CREATES)
def create_from_template(
    template_path: str,
    substitutions: dict = {},  # noqa: B006 -- read-only; engine only iterates it
    output_path: str = "",
    return_content: bool = False,
) -> dict:
    """Copy .pptx template, fill {key: value} substitutions, save."""
    return engine.create_from_template(
        template_path, output_path, substitutions, open_after=True, return_content=return_content
    )


@mcp.tool(annotations=CREATES)
def create_agenda(
    meeting_title: str,
    date: str,
    items: list,
    presenter: str = "",
    output_path: str = "",
    return_content: bool = False,
) -> dict:
    """Create a meeting agenda .pptx from {topic,duration,owner} items."""
    return engine.create_agenda(
        output_path,
        meeting_title,
        date,
        items,
        presenter,
        open_after=True,
        return_content=return_content,
    )


@mcp.tool(annotations=CREATES)
def create_from_docx(
    docx_path: str,
    max_slides: int = 20,
    output_path: str = "",
    return_content: bool = False,
) -> dict:
    """Convert a Word document outline into a PowerPoint presentation."""
    return engine.create_from_docx(docx_path, output_path, max_slides, open_after=True, return_content=return_content)


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
