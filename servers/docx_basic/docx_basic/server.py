"""DOCX Basic MCP server — thin wrapper over engine.py."""

import argparse
import os

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from docx_basic import engine
from docx_basic.helpers import diff_versions as _diff_versions
from docx_basic.helpers import get_history_tool as _get_history_tool
from docx_basic.helpers import read_receipt_tool as _read_receipt_tool
from docx_basic.helpers import restore_version as _restore_version
from shared.arg_errors import contract_errors
from shared.deploy_auth import build_auth, build_oauth_bridge
from shared.strict_args import enforce_known_arguments
from shared.token_estimate import measure_responses
from shared.tool_annotations import EDITS, READS

_VERSION = "0.1.2"  # keep in sync with pyproject.toml [project].version
_HOST = os.environ.get("OFFICE_DOCX_BASIC_HOST", "127.0.0.1")
_PORT = int(os.environ.get("OFFICE_DOCX_BASIC_PORT", "8830"))
_oauth_bridge = build_oauth_bridge(
    "OFFICE", state_dir=os.environ.get("OFFICE_DOCX_BASIC_OAUTH_STATE_DIR", "/tmp/office-docx-basic-oauth-state")
)
_public_origin = os.environ.get("OFFICE_PUBLIC_URL", "").rstrip("/")
_public_url = f"{_public_origin}/docx-basic" if _public_origin else None
_token_verifier, _auth_settings = build_auth("OFFICE", _HOST, _PORT, _oauth_bridge, public_url=_public_url)

mcp = FastMCP(
    "docx-basic",
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
def get_document_outline(file_path: str) -> dict:
    """Return headings and paragraph indices — structural skeleton."""
    return engine.get_document_outline(file_path)


@mcp.tool(annotations=READS)
def get_document_index(file_path: str) -> dict:
    """Return section tree index. Zero paragraph content returned."""
    return engine.get_document_index(file_path)


@mcp.tool(annotations=READS)
def fetch_section(file_path: str, address: str) -> dict:
    """Fetch one addressed section or paragraph. address: '§1' or '§1.p3'."""
    return engine.fetch_section(file_path, address)


@mcp.tool(annotations=READS)
def read_document(file_path: str) -> dict:
    """Read full doc. Use get_document_index for large files (>10 pages)."""
    return engine.read_document(file_path)


@mcp.tool(annotations=READS)
def read_paragraph(file_path: str, paragraph_index: int = -1, index: int = -1) -> dict:
    """Return one paragraph by paragraph_index, with full run detail. index= ok."""
    chosen = paragraph_index if paragraph_index >= 0 else index
    if chosen < 0:
        return {
            "success": False,
            "op": "read_paragraph",
            "error": "read_paragraph needs a paragraph_index",
            "hint": "Pass paragraph_index=0 for the first paragraph. index= is also accepted.",
            "progress": [],
            "token_estimate": 20,
        }
    return engine.read_paragraph(file_path, chosen)


@mcp.tool(annotations=READS)
def read_paragraph_range(file_path: str, start_index: int, end_index: int) -> dict:
    """Return bounded paragraph range. Max 50 paragraphs."""
    return engine.read_paragraph_range(file_path, start_index, end_index)


@mcp.tool(annotations=READS)
def search_paragraphs(file_path: str, query: str, max_results: int = 10) -> dict:
    """Scan paragraphs for matching text. Returns only matches."""
    return engine.search_paragraphs(file_path, query, max_results)


@mcp.tool(annotations=EDITS)
def replace_text(
    file_path: str,
    match_text: str,
    new_text: str,
    preserve_style: bool = True,
    dry_run: bool = False,
) -> dict:
    """Find text and replace in-place, preserving run formatting."""
    return engine.replace_text(file_path, match_text, new_text, preserve_style, dry_run, open_after=True)


@mcp.tool(annotations=EDITS)
def insert_paragraph(
    file_path: str,
    after_index: int,
    text: str,
    style: str = "Body Text",
) -> dict:
    """Insert paragraph after index N. -1 inserts before the first paragraph."""
    return engine.insert_paragraph(file_path, after_index, text, style, open_after=True)


@mcp.tool(annotations=EDITS)
def delete_paragraph(
    file_path: str,
    paragraph_index: int = -1,
    match_text: str = "",
) -> dict:
    """Delete a paragraph by index or by matching text content."""
    return engine.delete_paragraph(file_path, paragraph_index, match_text, open_after=True)


@mcp.tool(annotations=EDITS)
def append_text(file_path: str, text: str, style: str = "Body Text") -> dict:
    """Append a new paragraph at the end of the document."""
    return engine.append_text(file_path, text, style, open_after=True)


@mcp.tool(annotations=READS)
def get_history(file_path: str) -> dict:
    """Return version snapshot history for a document."""
    return _get_history_tool(file_path)


@mcp.tool(annotations=EDITS)
def restore_version(file_path: str, timestamp: str, create_branch: str = "") -> dict:
    """Restore document to a previous snapshot. Optionally create git branch."""
    return _restore_version(file_path, timestamp, create_branch)


@mcp.tool(annotations=READS)
def diff_versions(file_path: str, timestamp_a: str, timestamp_b: str = "current") -> dict:
    """Compare two document versions. timestamp_b defaults to current file."""
    return _diff_versions(file_path, timestamp_a, timestamp_b)


@mcp.tool(annotations=READS)
def read_receipt(file_path: str, last_n: int = 10) -> dict:
    """Show recent tool operations on this file. last_n: how many to show."""
    return _read_receipt_tool(file_path, last_n)


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
    parser = argparse.ArgumentParser(description="docx_basic MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.environ.get("OFFICE_DOCX_BASIC_TRANSPORT", "stdio"),
    )
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
