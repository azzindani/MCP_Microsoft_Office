"""Every tool must declare its annotations, and they must not overclaim.

All 96 tools here shipped with a bare `@mcp.tool()`. Absent the annotations
field a client applies the MCP spec defaults --

    readOnlyHint     false
    destructiveHint  true
    idempotentHint   false
    openWorldHint    true

-- so `read_document`, which opens a .docx and returns its paragraphs,
advertised itself as a destructive, non-repeatable operation reaching the open
internet. A client that gates destructive tools behind confirmation prompts for
every read; one that trusts openWorldHint believes these servers call out to
the network, which is the opposite of what this project is built on. Checked
against the live endpoints first: 0 of 96 here carried annotations, while the
three sibling repos carried them on all 47 of theirs.

The read-only set was settled by observation: each of the 25 was called against
a seeded workspace holding a real .docx, .pptx and .xlsx, with the directory
fingerprinted before and after. All 25 touched nothing, and the write tools in
the same run each showed their snapshot, their receipt and the changed file --
so the probe discriminates rather than always answering "read".

What is guarded here is what can be checked cheaply and reliably: that every
tool declares annotations at all, that openWorldHint is False everywhere, and
that nothing claiming readOnlyHint is also marked destructive. The last of
those is the mistake that matters -- a tool a client may call without asking
must not be able to write.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SERVERS = [
    "docx_basic",
    "docx_layout",
    "docx_new",
    "docx_tables",
    "pptx_basic",
    "pptx_design",
    "pptx_new",
    "xlsx_basic",
    "xlsx_charts",
    "xlsx_formulas",
    "xlsx_new",
]

# Confirmed by the live probe described above.
READ_ONLY = {
    "get_document_outline",
    "get_document_index",
    "fetch_section",
    "read_document",
    "read_paragraph",
    "read_paragraph_range",
    "search_paragraphs",
    "get_history",
    "diff_versions",
    "read_receipt",
    "list_tables",
    "read_table",
    "search_table_cells",
    "read_table_row",
    "read_presentation",
    "read_slide",
    "search_slides",
    "read_slide_text",
    "list_sheets",
    "get_sheet_summary",
    "read_cell",
    "read_cell_range",
    "search_cells",
    "find_duplicates",
    # Takes no path and opens no file: it returns the block vocabulary
    # `create_from_blocks` accepts. Read-only in the strongest sense the probe
    # measures -- there is nothing on disk for it to reach.
    "list_block_kinds",
}


def load(name: str):
    pkg = ROOT / "servers" / name / name
    if str(pkg.parent) not in sys.path:
        sys.path.insert(0, str(pkg.parent))
    return importlib.import_module(f"{name}.server")


ALL = [(s, n, t) for s in SERVERS for n, t in load(s).mcp._tool_manager._tools.items()]


def annotations_of(tool) -> dict:
    ann = getattr(tool, "annotations", None)
    if ann is None:
        return {}
    if isinstance(ann, dict):
        return ann
    return {k: v for k, v in vars(ann).items() if v is not None}


class TestEveryToolIsAnnotated:
    def test_the_servers_expose_the_tools_this_covers(self):
        # An empty registry would make every case below vacuous.
        assert len(ALL) >= 90, f"only {len(ALL)} tools found"

    @pytest.mark.parametrize("server,name,tool", ALL, ids=[f"{s}.{n}" for s, n, _ in ALL])
    def test_it_declares_annotations(self, server, name, tool):
        assert annotations_of(tool), f"{server}.{name} declares none — the spec defaults apply"

    @pytest.mark.parametrize("server,name,tool", ALL, ids=[f"{s}.{n}" for s, n, _ in ALL])
    def test_it_does_not_claim_to_reach_the_network(self, server, name, tool):
        assert annotations_of(tool).get("openWorldHint") is False, f"{server}.{name}"


class TestTheReadOnlySetIsExactlyWhatWasProbed:
    @pytest.mark.parametrize("server,name,tool", ALL, ids=[f"{s}.{n}" for s, n, _ in ALL])
    def test_read_only_matches_the_probe(self, server, name, tool):
        declared = bool(annotations_of(tool).get("readOnlyHint"))
        expected = name in READ_ONLY
        assert declared is expected, (
            f"{server}.{name}: declares readOnlyHint={declared}, probe says {expected}. "
            "Re-run the probe before changing this list."
        )

    @pytest.mark.parametrize("server,name,tool", ALL, ids=[f"{s}.{n}" for s, n, _ in ALL])
    def test_nothing_is_both_read_only_and_destructive(self, server, name, tool):
        ann = annotations_of(tool)
        if ann.get("readOnlyHint"):
            assert ann.get("destructiveHint") is False, f"{server}.{name}"


class TestTheClassificationIsNotAllOneThing:
    def test_all_three_kinds_are_used(self):
        kinds = {(annotations_of(t).get("readOnlyHint"), annotations_of(t).get("destructiveHint")) for _, _, t in ALL}
        # Reads, creates and edits — if a later edit collapsed everything onto
        # one constant the guards above would still pass.
        assert len(kinds) >= 3, kinds
