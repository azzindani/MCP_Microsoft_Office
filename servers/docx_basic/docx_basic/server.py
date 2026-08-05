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
from shared.deploy_auth import build_auth

_VERSION = "0.1.0"  # keep in sync with pyproject.toml [project].version
_HOST = os.environ.get("OFFICE_DOCX_BASIC_HOST", "127.0.0.1")
_PORT = int(os.environ.get("OFFICE_DOCX_BASIC_PORT", "8830"))
_token_verifier, _auth_settings = build_auth("OFFICE", _HOST, _PORT)

mcp = FastMCP(
    "docx-basic",
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
def get_document_outline(file_path: str) -> dict:
    """Return headings and paragraph indices — structural skeleton."""
    return engine.get_document_outline(file_path)


@mcp.tool()
def get_document_index(file_path: str) -> dict:
    """Return section tree index. Zero paragraph content returned."""
    return engine.get_document_index(file_path)


@mcp.tool()
def fetch_section(file_path: str, address: str) -> dict:
    """Fetch content of addressed section or paragraph only."""
    return engine.fetch_section(file_path, address)


@mcp.tool()
def read_document(file_path: str) -> dict:
    """Read full doc. Use get_document_index for large files (>10 pages)."""
    return engine.read_document(file_path)


@mcp.tool()
def read_paragraph(file_path: str, index: int) -> dict:
    """Return one paragraph with full run detail including formatting."""
    return engine.read_paragraph(file_path, index)


@mcp.tool()
def read_paragraph_range(file_path: str, start_index: int, end_index: int) -> dict:
    """Return bounded paragraph range. Max 50 paragraphs."""
    return engine.read_paragraph_range(file_path, start_index, end_index)


@mcp.tool()
def search_paragraphs(file_path: str, query: str, max_results: int = 10) -> dict:
    """Scan paragraphs for matching text. Returns only matches."""
    return engine.search_paragraphs(file_path, query, max_results)


@mcp.tool()
def replace_text(
    file_path: str,
    match_text: str,
    new_text: str,
    preserve_style: bool = True,
    dry_run: bool = False,
) -> dict:
    """Find text and replace in-place, preserving run formatting."""
    return engine.replace_text(file_path, match_text, new_text, preserve_style, dry_run, open_after=True)


@mcp.tool()
def insert_paragraph(
    file_path: str,
    after_index: int,
    text: str,
    style: str = "Body Text",
) -> dict:
    """Insert paragraph after index N with the given style."""
    return engine.insert_paragraph(file_path, after_index, text, style, open_after=True)


@mcp.tool()
def delete_paragraph(
    file_path: str,
    paragraph_index: int = -1,
    match_text: str = "",
) -> dict:
    """Delete a paragraph by index or by matching text content."""
    return engine.delete_paragraph(file_path, paragraph_index, match_text, open_after=True)


@mcp.tool()
def append_text(file_path: str, text: str, style: str = "Body Text") -> dict:
    """Append a new paragraph at the end of the document."""
    return engine.append_text(file_path, text, style, open_after=True)


@mcp.tool()
def get_history(file_path: str) -> dict:
    """Return version snapshot history for a document."""
    return _get_history_tool(file_path)


@mcp.tool()
def restore_version(file_path: str, timestamp: str, create_branch: str = "") -> dict:
    """Restore document to a previous snapshot. Optionally create git branch."""
    return _restore_version(file_path, timestamp, create_branch)


@mcp.tool()
def diff_versions(file_path: str, timestamp_a: str, timestamp_b: str = "current") -> dict:
    """Compare two document versions. timestamp_b defaults to current file."""
    return _diff_versions(file_path, timestamp_a, timestamp_b)


@mcp.tool()
def read_receipt(file_path: str, last_n: int = 10) -> dict:
    """Show recent tool operations on this file. last_n: how many to show."""
    return _read_receipt_tool(file_path, last_n)


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
