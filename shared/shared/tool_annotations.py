"""What a client may assume about each tool, per the MCP spec.

Every tool on these eleven servers shipped with a bare `@mcp.tool()`. That is
not neutral: absent the annotations field, a client applies the spec defaults --

    readOnlyHint     false
    destructiveHint  true
    idempotentHint   false
    openWorldHint    true

-- so `read_document`, which opens a .docx and returns its paragraphs,
advertised itself as a destructive, non-repeatable operation that reaches the
open internet. A client that gates destructive tools behind a confirmation
prompts for every read; one that trusts openWorldHint believes these servers
call out to the network, which is the opposite of what this project is built
on.

The sibling repos (Math, Machine_Learning, File_System) already declare theirs.
This brings the largest one in line, and uses File_System's `ToolAnnotations`
form since both run the FastMCP bundled in the `mcp` SDK.

The read-only set was settled by observation rather than by reading names: each
candidate was called against a seeded workspace holding a real .docx, .pptx and
.xlsx, with the directory fingerprinted before and after. All 25 touched
nothing; the write tools in the same run all showed their snapshot, their
receipt and the changed file, so the probe discriminates.

    READS    25  touches nothing on disk
    CREATES  21  writes a new file — the create_* families and export_pdf
    EDITS    50  writes back over the document it was given, snapshotting first

`openWorldHint` is False throughout: these servers are offline-first by
construction and no tool reaches a network at runtime.
"""

from __future__ import annotations

from mcp.types import ToolAnnotations

READS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

CREATES = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

# Not idempotent: add_row, append_text, add_slide and their kin append, so
# calling one twice does not leave the document it left the first time.
EDITS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=False,
)

__all__ = ["CREATES", "EDITS", "READS"]
