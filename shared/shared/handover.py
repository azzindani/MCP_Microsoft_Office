"""Universal handover protocol for multi-MCP-server tool call loops.

Workflow steps (server-agnostic, in order):
  COLLECT -> INSPECT -> CLEAN -> PREPARE -> TRAIN -> EVALUATE -> REPORT

Domain routing (which MCP server handles which domain):
  data    -> MCP_Data_Analyst
  ml      -> MCP_Machine_Learning
  office  -> MCP_Microsoft_Office  (this server)
  fs      -> MCP_FileSystem
  search  -> MCP_Search

Every tool response may include two fields for downstream chaining:
  context  = make_context(op, summary, artifacts)
  handover = make_handover(workflow_step, suggested_next, carry_forward)

These fields are optional but strongly recommended for write tools and any
tool whose output is typically consumed by another tool in the same session.
"""

from __future__ import annotations

from datetime import UTC, datetime

WORKFLOW_STEPS: list[str] = ["COLLECT", "INSPECT", "CLEAN", "PREPARE", "TRAIN", "EVALUATE", "REPORT"]

DOMAIN_SERVERS: dict[str, str] = {
    "data": "MCP_Data_Analyst",
    "ml": "MCP_Machine_Learning",
    "office": "MCP_Microsoft_Office",
    "fs": "MCP_FileSystem",
    "search": "MCP_Search",
}

# Office tools mapped to the universal workflow steps.
# COLLECT  : load/open the document
# INSPECT  : read, search, and explore content
# CLEAN    : targeted edits and patches
# PREPARE  : restructure or combine documents
# TRAIN    : (no Office equivalent — empty)
# EVALUATE : verify edits, diff, read receipts
# REPORT   : export, create final output
STEP_TOOLS: dict[str, list[str]] = {
    "COLLECT": [
        "read_document",
        "list_sheets",
        "read_slide",
        "load_dataset",
        "open_workspace",
    ],
    "INSPECT": [
        "search_paragraphs",
        "get_document_index",
        "fetch_section",
        "read_paragraph",
        "list_tables",
        "read_table",
        "list_sheets",
        "read_cell",
        "read_range",
        "list_slides",
        "read_slide",
        "inspect_dataset",
    ],
    "CLEAN": [
        "replace_text",
        "apply_patch",
        "insert_paragraph",
        "delete_paragraph",
        "set_cell",
        "set_formula",
        "set_text",
        "update_shape",
        "add_row",
        "delete_row",
    ],
    "PREPARE": [
        "merge_documents",
        "batch_create",
        "create_document",
        "create_workbook",
        "create_presentation",
        "concat_datasets",
        "merge_datasets",
    ],
    "TRAIN": [],
    "EVALUATE": [
        "diff_versions",
        "read_receipt",
        "get_history",
        "read_paragraph",
        "read_cell",
        "read_slide",
        "statistical_test",
        "regression_analysis",
    ],
    "REPORT": [
        "export_pdf",
        "add_chart",
        "generate_chart",
        "run_eda",
        "generate_dashboard",
        "create_document",
        "create_workbook",
        "create_presentation",
    ],
}


def _normalize_step(step: str) -> str:
    normalized = step.upper()
    if normalized in WORKFLOW_STEPS:
        return normalized
    return normalized


def _next_step(step: str) -> str:
    try:
        idx = WORKFLOW_STEPS.index(step)
        return WORKFLOW_STEPS[idx + 1] if idx + 1 < len(WORKFLOW_STEPS) else ""
    except ValueError:
        return ""


def make_context(
    op: str,
    summary: str,
    artifacts: list[dict] | None = None,
) -> dict:
    """Return a context dict capturing what this tool just did.

    op        : tool/operation name (e.g. "replace_text")
    summary   : plain-English description of what happened and the result
    artifacts : list of {"type": str, "path": str, "role": str, ...} dicts
    """
    return {
        "op": op,
        "summary": summary,
        "artifacts": artifacts or [],
        "timestamp": datetime.now(UTC).isoformat(),
    }


def make_handover(
    workflow_step: str,
    suggested_next: list[dict],
    carry_forward: dict | None = None,
) -> dict:
    """Return a handover dict for inclusion in a tool response.

    workflow_step   : current step (COLLECT/INSPECT/CLEAN/PREPARE/TRAIN/EVALUATE/REPORT)
    suggested_next  : list of {"tool": str, "server": str, "domain": str, "reason": str}
    carry_forward   : exact params the LLM should pass to the next tool call
    """
    step = _normalize_step(workflow_step)
    return {
        "workflow_step": step,
        "workflow_next": _next_step(step),
        "suggested_next": [
            {
                "tool": s.get("tool", ""),
                "server": s.get("server", ""),
                "domain": s.get("domain", "office"),
                "reason": s.get("reason", ""),
            }
            for s in suggested_next
        ],
        "carry_forward": carry_forward or {},
    }


__all__ = [
    "WORKFLOW_STEPS",
    "DOMAIN_SERVERS",
    "STEP_TOOLS",
    "make_context",
    "make_handover",
]
