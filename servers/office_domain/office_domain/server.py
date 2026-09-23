"""Every Office tool as ten domain tools -- one endpoint, `action` plus `args`.

The eleven tier servers list 99 tools between them; a model connected to all of
them reads 99 names on every turn, nine of them twice over for different file
types. This endpoint lists ten: read, edit and create for each of Word, Excel
and PowerPoint, plus one for any file's history. Each `action` is a tier tool
by its own name, so `set_cell` is a docx_edit action and an xlsx_edit action,
each the right one. Schemas, validation, wrappers and answers are the tiers'
own: see shared/domain_tools.py. The tier endpoints keep serving unchanged.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

_root = str(Path(__file__).resolve().parents[3])
if _root not in sys.path:
    sys.path.insert(0, _root)

from mcp.server.fastmcp import FastMCP  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402

from servers.docx_basic.docx_basic.server import mcp as docx_basic  # noqa: E402
from servers.docx_layout.docx_layout.server import mcp as docx_layout  # noqa: E402
from servers.docx_new.docx_new.server import mcp as docx_new  # noqa: E402
from servers.docx_tables.docx_tables.server import mcp as docx_tables  # noqa: E402
from servers.pptx_basic.pptx_basic.server import mcp as pptx_basic  # noqa: E402
from servers.pptx_design.pptx_design.server import mcp as pptx_design  # noqa: E402
from servers.pptx_new.pptx_new.server import mcp as pptx_new  # noqa: E402
from servers.xlsx_basic.xlsx_basic.server import mcp as xlsx_basic  # noqa: E402
from servers.xlsx_charts.xlsx_charts.server import mcp as xlsx_charts  # noqa: E402
from servers.xlsx_formulas.xlsx_formulas.server import mcp as xlsx_formulas  # noqa: E402
from servers.xlsx_new.xlsx_new.server import mcp as xlsx_new  # noqa: E402
from shared.arg_errors import contract_errors  # noqa: E402
from shared.deploy_auth import build_auth, build_oauth_bridge  # noqa: E402
from shared.domain_tools import register_domains  # noqa: E402
from shared.strict_args import enforce_known_arguments  # noqa: E402

_VERSION = "0.2.0"  # keep in sync with pyproject.toml [project].version

_oauth_bridge = build_oauth_bridge(
    "OFFICE", state_dir=os.environ.get("OFFICE_DOMAIN_OAUTH_STATE_DIR", "/tmp/office-domain-oauth-state")
)
_public_origin = os.environ.get("OFFICE_PUBLIC_URL", "").rstrip("/")
_HOST = os.environ.get("OFFICE_DOMAIN_HOST", "127.0.0.1")
_PORT = int(os.environ.get("OFFICE_DOMAIN_PORT", "8841"))
_token_verifier, _auth_settings = build_auth("OFFICE", _HOST, _PORT, _oauth_bridge, public_url=_public_origin or None)

mcp = FastMCP("office", host=_HOST, port=_PORT, token_verifier=_token_verifier, auth=_auth_settings)
if _oauth_bridge is not None:
    _oauth_bridge.register_routes(mcp)

# Each domain: what it is for, then its actions -- each an existing tier tool.
DOMAINS = {
    "docx_read": (
        "Read a Word document without changing it: outline, sections, paragraphs, search, tables, version diff.",
        [
            (docx_basic, "get_document_outline"),
            (docx_basic, "get_document_index"),
            (docx_basic, "fetch_section"),
            (docx_basic, "read_document"),
            (docx_basic, "read_paragraph"),
            (docx_basic, "read_paragraph_range"),
            (docx_basic, "search_paragraphs"),
            (docx_tables, "list_tables"),
            (docx_tables, "read_table"),
            (docx_tables, "search_table_cells"),
            (docx_tables, "read_table_row"),
            (docx_basic, "diff_versions"),
        ],
    ),
    "docx_edit": (
        "Change a Word document: text, paragraphs, tables, cells, styles, fonts, images, margins, headers, PDF export.",
        [
            (docx_basic, "replace_text"),
            (docx_basic, "insert_paragraph"),
            (docx_basic, "delete_paragraph"),
            (docx_basic, "append_text"),
            (docx_tables, "set_cell"),
            (docx_tables, "add_row"),
            (docx_tables, "delete_row"),
            (docx_tables, "add_table"),
            (docx_tables, "delete_table"),
            (docx_tables, "set_cell_style"),
            (docx_layout, "set_heading"),
            (docx_layout, "set_font"),
            (docx_layout, "set_paragraph_style"),
            (docx_layout, "add_image"),
            (docx_layout, "set_page_margins"),
            (docx_layout, "add_header_footer"),
            (docx_layout, "export_pdf"),
        ],
    ),
    "docx_create": (
        "Make a new Word document: blank, from text, sections, blocks, a template, a letter, or by merging.",
        [
            (docx_new, "create_document"),
            (docx_new, "create_from_text"),
            (docx_new, "create_from_sections"),
            (docx_new, "list_block_kinds"),
            (docx_new, "create_from_blocks"),
            (docx_new, "create_from_template"),
            (docx_new, "create_letter"),
            (docx_new, "merge_documents"),
            (docx_new, "batch_create_from_template"),
        ],
    ),
    "xlsx_read": (
        "Read a workbook without changing it: sheets, summary, cells, ranges, search, duplicates.",
        [
            (xlsx_basic, "list_sheets"),
            (xlsx_basic, "get_sheet_summary"),
            (xlsx_basic, "read_cell"),
            (xlsx_basic, "read_cell_range"),
            (xlsx_basic, "search_cells"),
            (xlsx_basic, "find_duplicates"),
        ],
    ),
    "xlsx_edit": (
        "Change a workbook: cells, ranges, rows, sheets, formulas, named ranges, formats, validation, charts, pivots.",
        [
            (xlsx_basic, "set_cell"),
            (xlsx_basic, "set_range"),
            (xlsx_basic, "insert_row"),
            (xlsx_basic, "delete_row"),
            (xlsx_basic, "add_sheet"),
            (xlsx_basic, "sort_sheet"),
            (xlsx_basic, "rename_sheet"),
            (xlsx_basic, "copy_sheet"),
            (xlsx_formulas, "set_formula"),
            (xlsx_formulas, "set_named_range"),
            (xlsx_formulas, "set_conditional_format"),
            (xlsx_formulas, "set_data_validation"),
            (xlsx_formulas, "freeze_panes"),
            (xlsx_formulas, "set_autofilter"),
            (xlsx_formulas, "fill_formula_down"),
            (xlsx_formulas, "auto_sum"),
            (xlsx_formulas, "convert_to_values"),
            (xlsx_charts, "add_chart"),
            (xlsx_charts, "delete_chart"),
            (xlsx_charts, "update_chart"),
            (xlsx_charts, "add_pivot_table"),
            (xlsx_charts, "set_cell_style"),
        ],
    ),
    "xlsx_create": (
        "Make a new workbook: blank, from data, a report, a template, a CSV, an invoice.",
        [
            (xlsx_new, "create_workbook"),
            (xlsx_new, "create_from_data"),
            (xlsx_new, "create_report"),
            (xlsx_new, "create_from_template"),
            (xlsx_new, "create_from_csv"),
            (xlsx_new, "create_invoice"),
        ],
    ),
    "pptx_read": (
        "Read a presentation without changing it: slides, text, search, version diff.",
        [
            (pptx_basic, "read_presentation"),
            (pptx_basic, "read_slide"),
            (pptx_basic, "search_slides"),
            (pptx_basic, "read_slide_text"),
            (pptx_basic, "diff_versions"),
        ],
    ),
    "pptx_edit": (
        "Change a presentation: text, slides, order, text boxes, background, fonts, tables, charts, images, PDF export.",
        [
            (pptx_basic, "set_text"),
            (pptx_basic, "add_slide"),
            (pptx_basic, "delete_slide"),
            (pptx_basic, "reorder_slide"),
            (pptx_basic, "add_text_box"),
            (pptx_design, "set_background"),
            (pptx_design, "set_font_style"),
            (pptx_design, "add_table"),
            (pptx_design, "add_chart"),
            (pptx_design, "duplicate_slide"),
            (pptx_design, "export_pdf"),
            (pptx_design, "add_image_to_all_slides"),
            (pptx_design, "set_font_all_slides"),
        ],
    ),
    "pptx_create": (
        "Make a new presentation: blank, from an outline, from data, a template, an agenda, or from a document.",
        [
            (pptx_new, "create_presentation"),
            (pptx_new, "create_from_outline"),
            (pptx_new, "create_deck_from_data"),
            (pptx_new, "create_from_template"),
            (pptx_new, "create_agenda"),
            (pptx_new, "create_from_docx"),
        ],
    ),
    "office_history": (
        "Any Office file's history: its snapshots, restoring one, and the operations done to it.",
        [
            (docx_basic, "get_history"),
            (docx_basic, "restore_version"),
            (docx_basic, "read_receipt"),
        ],
    ),
}
register_domains(mcp, DOMAINS)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    """Liveness check. Unauthenticated."""
    return JSONResponse({"status": "ok", "version": _VERSION, "tools": len(DOMAINS)})


# A wrong-typed `args` or an unknown top-level key gets the fleet's failure
# shape, as on every tier; per-action arguments are checked by the dispatcher.
contract_errors(mcp)
enforce_known_arguments(mcp)


def main() -> None:
    parser = argparse.ArgumentParser(description="office domain MCP Server")
    parser.add_argument(
        "--transport", choices=["stdio", "http"], default=os.environ.get("OFFICE_DOMAIN_TRANSPORT", "stdio")
    )
    args = parser.parse_args()
    mcp.run(transport="streamable-http" if args.transport == "http" else "stdio")


if __name__ == "__main__":
    main()
