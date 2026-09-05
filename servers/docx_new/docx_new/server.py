"""DOCX New MCP server — create Word documents from scratch."""

from __future__ import annotations

import argparse
import os

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from docx_new import engine
from shared.arg_errors import contract_errors
from shared.deploy_auth import build_auth, build_oauth_bridge
from shared.strict_args import enforce_known_arguments
from shared.token_estimate import measure_responses
from shared.tool_annotations import CREATES

_VERSION = "0.1.2"  # keep in sync with pyproject.toml [project].version
_HOST = os.environ.get("OFFICE_DOCX_NEW_HOST", "127.0.0.1")
_PORT = int(os.environ.get("OFFICE_DOCX_NEW_PORT", "8833"))
_oauth_bridge = build_oauth_bridge(
    "OFFICE", state_dir=os.environ.get("OFFICE_DOCX_NEW_OAUTH_STATE_DIR", "/tmp/office-docx-new-oauth-state")
)
_public_origin = os.environ.get("OFFICE_PUBLIC_URL", "").rstrip("/")
_public_url = f"{_public_origin}/docx-new" if _public_origin else None
_token_verifier, _auth_settings = build_auth("OFFICE", _HOST, _PORT, _oauth_bridge, public_url=_public_url)

mcp = FastMCP(
    "docx-new",
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
def create_document(output_path: str = "", return_content: bool = False) -> dict:
    """Create blank .docx. return_content=True embeds file bytes (remote)."""
    return engine.create_document(output_path, open_after=False, return_content=return_content)


@mcp.tool(annotations=CREATES)
def create_from_text(
    paragraphs: list[dict],
    output_path: str = "",
    return_content: bool = False,
) -> dict:
    """Create .docx from list of {text, style} paragraph dicts."""
    return engine.create_from_text(output_path, paragraphs, open_after=True, return_content=return_content)


@mcp.tool(annotations=CREATES)
def create_from_sections(
    title: str,
    sections: list[dict],
    output_path: str = "",
    return_content: bool = False,
) -> dict:
    """Create structured .docx from title + [{heading, body}] sections."""
    return engine.create_from_sections(output_path, title, sections, open_after=True, return_content=return_content)


@mcp.tool(annotations=CREATES)
def create_from_blocks(
    title: str,
    blocks: list[dict],
    output_path: str = "",
    accent: str = "",
    return_content: bool = False,
) -> dict:
    """Blocks to .docx: heading text bullets table kpi callout image rule pagebreak."""
    return engine.create_from_blocks(output_path, title, blocks, accent, open_after=True, return_content=return_content)


@mcp.tool(annotations=CREATES)
def create_from_template(
    template_path: str,
    substitutions: dict = {},  # noqa: B006 -- read-only; engine only iterates it
    output_path: str = "",
    return_content: bool = False,
) -> dict:
    """Copy template .docx, fill {key: value} substitutions, save."""
    return engine.create_from_template(
        template_path, output_path, substitutions, open_after=True, return_content=return_content
    )


@mcp.tool(annotations=CREATES)
def create_letter(
    from_name: str,
    to_name: str,
    subject: str,
    body: str,
    output_path: str = "",
    return_content: bool = False,
) -> dict:
    """Create a formatted business letter .docx."""
    return engine.create_letter(
        output_path,
        from_name,
        to_name,
        subject,
        body,
        open_after=True,
        return_content=return_content,
    )


@mcp.tool(annotations=CREATES)
def merge_documents(
    file_paths: list,
    output_path: str = "",
    add_page_break: bool = True,
    return_content: bool = False,
) -> dict:
    """Merge multiple .docx files into one document."""
    return engine.merge_documents(
        file_paths, output_path, add_page_break, open_after=True, return_content=return_content
    )


@mcp.tool(annotations=CREATES)
def batch_create_from_template(
    template_path: str,
    data_list: list,
    output_dir: str,
    filename_key: str = "",
) -> dict:
    """Generate N .docx files from a template + list of {key:value} dicts."""
    return engine.batch_create_from_template(template_path, data_list, output_dir, filename_key, open_after=True)


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
    parser = argparse.ArgumentParser(description="docx_new MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.environ.get("OFFICE_DOCX_NEW_TRANSPORT", "stdio"),
    )
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
