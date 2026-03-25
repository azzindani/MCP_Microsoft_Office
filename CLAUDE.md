# CLAUDE.md — office-mcp

This file is the authoritative guide for Claude Code (and any AI coding agent) working
in this repository. Read it fully before writing, editing, or deleting any code.
Every architectural decision, naming rule, constraint, and workflow is documented here.
When in doubt, this file overrides your defaults.

---

## Table of contents

1. [Project overview](#1-project-overview)
2. [Repository layout](#2-repository-layout)
3. [Architecture principles](#3-architecture-principles)
4. [Technology stack](#4-technology-stack)
5. [Monorepo and workspace setup](#5-monorepo-and-workspace-setup)
6. [Shared module — shared/](#6-shared-module--shared)
7. [Server structure — every server follows the same pattern](#7-server-structure--every-server-follows-the-same-pattern)
8. [Tool inventory and tier rules](#8-tool-inventory-and-tier-rules)
9. [Patch protocol — the JSON op format](#9-patch-protocol--the-json-op-format)
9b. [Surgical addressing protocol — token-efficient document access](#9b-surgical-addressing-protocol--token-efficient-document-access)
10. [DOCX engine rules](#10-docx-engine-rules)
11. [XLSX engine rules](#11-xlsx-engine-rules)
12. [PPTX engine rules](#12-pptx-engine-rules)
13. [Version control layer](#13-version-control-layer)
14. [Error handling contract](#14-error-handling-contract)
15. [Testing rules](#15-testing-rules)
16. [MCP tool schema rules](#16-mcp-tool-schema-rules)
17. [LM Studio and local model constraints](#17-lm-studio-and-local-model-constraints)
18. [Installer and distribution](#18-installer-and-distribution)
19. [Naming conventions](#19-naming-conventions)
20. [What Claude must never do](#20-what-claude-must-never-do)
21. [Adding a new tool — step-by-step checklist](#21-adding-a-new-tool--step-by-step-checklist)
22. [Adding a new server — step-by-step checklist](#22-adding-a-new-server--step-by-step-checklist)
23. [Common failure modes and how to avoid them](#23-common-failure-modes-and-how-to-avoid-them)
24. [Dependency policy](#24-dependency-policy)
25. [Git and PR rules](#25-git-and-pr-rules)
26. [Source code editing protocol — line-level edits](#26-source-code-editing-protocol--line-level-edits)
27. [Git integration for document edits](#27-git-integration-for-document-edits)
28. [Document diff engine](#28-document-diff-engine)
29. [Project build progress tracker](#29-project-build-progress-tracker)

---

## 1. Project overview

`office-mcp` is an open-source monorepo of MCP (Model Context Protocol) servers that
give local LLMs full programmatic control over Microsoft Office file formats — Word
(.docx), Excel (.xlsx), and PowerPoint (.pptx) — plus PDF reading.

The primary target runtime is LM Studio 0.4.x running Qwen 3.5 (9B) or comparable
local models. The design is deliberately constrained to work within the tool-count and
context-length limits of 9B parameter models. Servers are split by complexity tier so
the user loads only the tools their task requires.

### Goals

- Every tool executes a deterministic, structured operation. The LLM generates a JSON
  patch array. The engine applies it. No AI inference happens inside the tool itself.
- Documents are never fully rewritten. Every edit is a targeted patch at the paragraph,
  run, cell, or shape level.
- Files on disk are safe. Every write operation is preceded by a version snapshot.
  Rollback is always possible.
- Zero cloud dependency. All servers run locally. No API keys required for core
  functionality.
- Non-developer installable. A user who can double-click an installer and paste JSON
  should be able to get this running.

### Non-goals

- This is not a general-purpose document library. Tools are intentionally narrow and
  opinionated for LLM consumption.
- This project does not render documents visually or provide a document viewer UI.
- This project does not integrate with cloud storage (OneDrive, Google Drive) in the
  core servers. That is a separate optional layer.

---

## 2. Repository layout

```
office-mcp/
│
├── shared/                         # imported by ALL servers — never duplicate this
│   ├── __init__.py
│   ├── version_control.py          # snapshot, patch log, rollback
│   ├── patch_validator.py          # validate op arrays before apply
│   └── file_utils.py               # safe path resolution, backup copy, JSON helpers
│
├── servers/
│   ├── docx_basic/                 # 8 tools — read, CRUD paragraphs, history
│   │   ├── __init__.py
│   │   ├── server.py               # FastMCP setup + tool definitions (thin)
│   │   ├── engine.py               # pure python-docx logic (no MCP imports)
│   │   └── pyproject.toml
│   │
│   ├── docx_tables/                # 7 tools — table CRUD
│   │   ├── __init__.py
│   │   ├── server.py
│   │   ├── engine.py
│   │   └── pyproject.toml
│   │
│   ├── docx_layout/                # 7 tools — styles, fonts, margins, export
│   │   ├── __init__.py
│   │   ├── server.py
│   │   ├── engine.py
│   │   └── pyproject.toml
│   │
│   ├── xlsx_basic/                 # 9 tools — read, cell CRUD, sheets
│   │   ├── __init__.py
│   │   ├── server.py
│   │   ├── engine.py
│   │   └── pyproject.toml
│   │
│   ├── xlsx_formulas/              # 6 tools — formulas, validation, freeze
│   │   ├── __init__.py
│   │   ├── server.py
│   │   ├── engine.py
│   │   └── pyproject.toml
│   │
│   ├── xlsx_charts/                # 5 tools — charts, pivot tables, cell styles
│   │   ├── __init__.py
│   │   ├── server.py
│   │   ├── engine.py
│   │   └── pyproject.toml
│   │
│   ├── pptx_basic/                 # 8 tools — read, slide CRUD, text, images
│   │   ├── __init__.py
│   │   ├── server.py
│   │   ├── engine.py
│   │   └── pyproject.toml
│   │
│   └── pptx_design/                # 6 tools — background, fonts, tables, charts
│       ├── __init__.py
│       ├── server.py
│       ├── engine.py
│       └── pyproject.toml
│
├── tests/
│   ├── fixtures/                   # real .docx .xlsx .pptx files for testing
│   │   ├── contract_simple.docx
│   │   ├── contract_complex.docx   # multi-run, tracked changes, tables
│   │   ├── report_tables.docx
│   │   ├── budget_simple.xlsx
│   │   ├── budget_formulas.xlsx
│   │   ├── dashboard.xlsx
│   │   ├── deck_simple.pptx
│   │   └── deck_images.pptx
│   ├── conftest.py                 # shared pytest fixtures
│   ├── test_shared.py
│   ├── test_docx_basic.py
│   ├── test_docx_tables.py
│   ├── test_docx_layout.py
│   ├── test_xlsx_basic.py
│   ├── test_xlsx_formulas.py
│   ├── test_xlsx_charts.py
│   ├── test_pptx_basic.py
│   └── test_pptx_design.py
│
├── install/
│   ├── install.sh                  # Linux / macOS
│   ├── install.bat                 # Windows
│   └── mcp_config_writer.py        # safe JSON patcher for LM Studio mcp.json
│
├── pyproject.toml                  # root workspace — uv workspaces config
├── uv.lock                         # single lockfile for entire repo
├── .python-version                 # pinned Python version (3.11)
├── CLAUDE.md                       # this file
└── README.md
```

Every server directory has exactly four files: `__init__.py`, `server.py`, `engine.py`,
`pyproject.toml`. No exceptions. If a server grows complex enough to need helpers, add
`helpers.py` in the same directory — do not create subdirectories inside a server.

---

## 3. Architecture principles

### P1 — engine.py has zero MCP imports

`engine.py` is pure Python. It imports `python-docx`, `openpyxl`, `python-pptx`, or
`pdfplumber` and the `shared/` module. It never imports `mcp`, `fastmcp`, or anything
from the MCP protocol layer. This makes the engine directly testable with pytest without
spinning up a server process.

### P2 — server.py is a thin wrapper only

`server.py` does three things: initialises the `FastMCP` instance, defines tool
functions with `@mcp.tool()` decorators, and calls into `engine.py`. Tool functions in
`server.py` must not contain business logic. If you find yourself writing document
manipulation logic in `server.py`, move it to `engine.py`.

### P3 — tools never rewrite entire files

Every write operation targets a specific node: a paragraph by index, a cell by address,
a shape by name, a slide by index. If an operation requires reading the whole document
first, that is two separate tool calls — one `read_*` and one targeted write. The LLM
is responsible for reading state before writing.

### P4 — snapshot before every write

Every tool that modifies a file calls `shared.version_control.snapshot(path)` before
applying any change. This is enforced in `shared/patch_validator.py`. If a tool skips
the snapshot, it is a bug.

### P5 — return structured JSON, never prose

Every tool returns a Python dict that becomes JSON. Never return a plain string sentence
like `"Done."` or `"Operation successful."`. Return `{"success": true, "op": "replace_text",
"paragraph_index": 4, "new_text": "..."}`. The LLM uses the returned JSON to confirm
what happened and decide the next step.

### P6 — fail loudly with actionable messages

When a tool fails, it returns `{"success": false, "error": "<specific reason>",
"hint": "<what the model should try instead>"}`. Never swallow exceptions silently.
Never return a success response when the operation did not complete.

### P7 — shared/ is read-only from server perspective

Servers import from `shared/` but never modify it. If you find a bug in `shared/`,
fix it there. Do not work around it by duplicating logic in `engine.py`.

### P8 — tool descriptions must be ≤ 80 characters

LM Studio passes tool descriptions as part of the context. Long descriptions consume
tokens and reduce the effective context available for document content. Every `@mcp.tool()`
description must be 80 characters or fewer. Descriptions longer than 80 characters
are a CI failure.

### P9 — tool parameter names are lowercase snake_case nouns

`file_path`, `paragraph_index`, `sheet_name`, `cell_address`. Never verb-first names
like `get_file_path` or camelCase like `filePath`. The LLM maps parameter names to
meaning — consistent naming reduces hallucinated arguments.

### P10 — no optional parameters with complex defaults

If a parameter is optional, its default must be `None` or a primitive scalar (`""`,
`0`, `false`). Never use a mutable default like `[]` or `{}`. Never use a computed
default. The JSON schema must be unambiguous.

---

## 4. Technology stack

| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.11 | Document libraries live here |
| MCP framework | FastMCP ≥ 1.2.0 | Official SDK, decorator-based tools |
| Package manager | uv | Workspace support, fast, single lockfile |
| DOCX manipulation | python-docx ≥ 1.1.0 | Mature, MIT, run-level access |
| DOCX run-safe edit | docxedit ≥ 1.2.0 | Preserves formatting on replace |
| XLSX read+write | openpyxl ≥ 3.1.0 | Read+write on existing files |
| XLSX create+charts | xlsxwriter ≥ 3.2.0 | Write-only, best chart support |
| PPTX | python-pptx ≥ 0.6.23 | Only mature open-source pptx lib |
| PDF read | pdfplumber ≥ 0.11.0 | Table + text extraction |
| PDF generate | reportlab ≥ 4.2.0 | Only for net-new PDF creation |
| Testing | pytest ≥ 8.0 | Standard |
| Type checking | pyright (strict) | Enforced in CI |
| Linting | ruff | Fast, replaces flake8+isort+black |

Python version is pinned to 3.11. Do not upgrade to 3.12+ without testing all document
libraries. `python-docx` has had compatibility issues with minor Python versions.

---

## 5. Monorepo and workspace setup

The root `pyproject.toml` declares a uv workspace:

```toml
[tool.uv.workspace]
members = [
    "servers/docx_basic",
    "servers/docx_tables",
    "servers/docx_layout",
    "servers/xlsx_basic",
    "servers/xlsx_formulas",
    "servers/xlsx_charts",
    "servers/pptx_basic",
    "servers/pptx_design",
]

[tool.uv.sources]
shared = { workspace = true }
```

The `shared/` directory is declared as a package:

```toml
# shared/pyproject.toml
[project]
name = "shared"
version = "0.1.0"
dependencies = []
```

Every server's `pyproject.toml` lists `shared` as a dependency:

```toml
[project]
dependencies = [
    "mcp[cli]>=1.2.0",
    "python-docx>=1.1.0",
    "docxedit>=1.2.0",
    "shared",
]
```

### Running commands

```bash
# Install everything (run once after clone)
uv sync

# Run a specific server (for development)
uv run --directory servers/docx_basic docx-basic

# Run all tests
uv run pytest tests/

# Run tests for one server only
uv run pytest tests/test_docx_basic.py

# Type check one server
uv run pyright servers/docx_basic/

# Lint everything
uv run ruff check .

# Format everything
uv run ruff format .
```

### mcp.json entry format for LM Studio

Each server registers itself in the user's LM Studio `mcp.json` with this pattern:

```json
{
  "mcpServers": {
    "docx-basic": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "/absolute/path/to/office-mcp/servers/docx_basic",
        "docx-basic"
      ],
      "env": {}
    }
  }
}
```

The `install/mcp_config_writer.py` script generates this automatically with the correct
absolute path for the current machine. Users should never edit this JSON manually.

---

## 6. Shared module — shared/

### version_control.py

Exports three functions. Every server uses these and must not reimplement them.

```python
def snapshot(file_path: str) -> str:
    """
    Copy file_path to .mcp_versions/{filename}_{iso_timestamp}.bak
    Returns the backup path.
    Raises FileNotFoundError if file_path does not exist.
    """

def restore(file_path: str, timestamp: str) -> bool:
    """
    Copy .mcp_versions/{filename}_{timestamp}.bak back over file_path.
    Returns True on success, False if backup not found.
    """

def get_history(file_path: str) -> list[dict]:
    """
    Return list of snapshots for file_path, newest first.
    Each dict: {"timestamp": str, "backup_path": str, "size_bytes": int}
    """
```

Snapshots are stored in a `.mcp_versions/` directory in the same folder as the file
being edited. This directory is created automatically on first snapshot.

The `.mcp_versions/` directory must be listed in `.gitignore`.

### patch_validator.py

Exports one function:

```python
def validate_ops(ops: list[dict], allowed_ops: list[str]) -> tuple[bool, str]:
    """
    Validate a patch op array before applying.
    Returns (True, "") on valid, (False, error_message) on invalid.
    Checks: ops is a list, each op has "op" key, op value is in allowed_ops,
    required fields for each op type are present and correctly typed.
    """
```

Every engine function that accepts a patch array calls `validate_ops` before doing
anything. If validation fails, the function returns immediately with an error dict.
No snapshot is taken on validation failure.

### file_utils.py

```python
def resolve_path(path: str) -> Path:
    """
    Expand ~ and environment variables, resolve to absolute path.
    Raises ValueError if path traverses outside allowed directories.
    """

def safe_copy(src: str, dst: str) -> None:
    """
    Copy src to dst. Creates parent directories if needed.
    Raises on permission errors.
    """

def read_mcp_json(path: str) -> dict:
    """
    Parse mcp.json safely. Handles trailing commas and inline comments
    using json5 library. Returns empty dict if file does not exist.
    """

def write_mcp_json(path: str, data: dict) -> None:
    """
    Write mcp.json. Pretty-prints with 2-space indent.
    Writes to a temp file first, then atomically renames to avoid
    partial writes corrupting the config.
    """
```

---

## 7. Server structure — every server follows the same pattern

### server.py template

```python
from mcp.server.fastmcp import FastMCP
from . import engine

mcp = FastMCP("docx-basic")          # name matches pyproject.toml project name


@mcp.tool()
def read_document(file_path: str) -> dict:
    """Extract full document text and paragraph index as JSON."""
    return engine.read_document(file_path)


@mcp.tool()
def replace_text(
    file_path: str,
    match_text: str,
    new_text: str,
    preserve_style: bool = True,
) -> dict:
    """Find text and replace in-place, preserving run formatting."""
    return engine.replace_text(file_path, match_text, new_text, preserve_style)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
```

Rules for `server.py`:
- One `@mcp.tool()` per exported tool. No helper functions in this file.
- Tool function body is always a single `return engine.function_name(...)` call.
- Type annotations on all parameters. Return type is always `dict`.
- Docstring is the tool description shown to the model. Keep it ≤ 80 chars.
- `main()` function required for the `project.scripts` entry point.

### engine.py template

```python
from pathlib import Path
from docx import Document
from shared.version_control import snapshot
from shared.patch_validator import validate_ops
from shared.file_utils import resolve_path


def read_document(file_path: str) -> dict:
    path = resolve_path(file_path)
    try:
        doc = Document(str(path))
        paragraphs = [
            {
                "index": i,
                "text": p.text,
                "style": p.style.name,
            }
            for i, p in enumerate(doc.paragraphs)
        ]
        return {
            "success": True,
            "file": str(path),
            "paragraph_count": len(paragraphs),
            "paragraphs": paragraphs,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "hint": "Check that file_path points to a valid .docx file.",
        }


def replace_text(
    file_path: str,
    match_text: str,
    new_text: str,
    preserve_style: bool = True,
) -> dict:
    path = resolve_path(file_path)
    backup = snapshot(str(path))
    try:
        # implementation using run-level editing
        ...
        return {
            "success": True,
            "op": "replace_text",
            "match": match_text,
            "replaced_in_paragraphs": [...],
            "backup": backup,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "backup": backup,
            "hint": "Use restore_version to undo.",
        }
```

Rules for `engine.py`:
- Every function returns a dict with at minimum `"success": bool`.
- Snapshot before every write. Include `"backup"` path in return dict.
- Never raise exceptions to the caller. Catch and return error dict.
- No print statements. No logging to stdout (breaks MCP stdio transport).
  Use `import logging; logger = logging.getLogger(__name__)` and log to
  stderr via `logging.basicConfig(stream=sys.stderr)` if needed.

---

## 8. Tool inventory and tier rules

### Tool count constraint

The maximum tool count for a single server is **10 tools**. This is a hard limit, not
a guideline. LM Studio running a 9B model becomes unreliable with more than 10-12 tools
in context. If a natural grouping exceeds 10 tools, split into two servers.

The recommended tool count per server is **6-9 tools**.

### Allowed tool counts per server

| Server | Tools | Surgical tools included |
|---|---|---|
| docx_basic | 10 | `get_document_outline`, `search_paragraphs`, `read_paragraph`, `read_paragraph_range`, `replace_text`, `insert_paragraph`, `delete_paragraph`, `append_text`, `get_history`, `restore_version` |
| docx_tables | 9 | `search_table_cells`, `read_table_row`, `list_tables`, `read_table`, `set_cell`, `add_row`, `delete_row`, `add_table`, `delete_table` |
| docx_layout | 7 | `set_heading`, `set_font`, `set_paragraph_style`, `add_image`, `set_page_margins`, `add_header_footer`, `export_pdf` |
| xlsx_basic | 10 | `get_sheet_summary`, `search_cells`, `read_cell_range`, `list_sheets`, `read_cell`, `set_cell`, `set_range`, `insert_row`, `delete_row`, `add_sheet` |
| xlsx_formulas | 6 | `set_formula`, `set_named_range`, `set_conditional_format`, `set_data_validation`, `freeze_panes`, `set_autofilter` |
| xlsx_charts | 5 | `add_chart`, `update_chart`, `delete_chart`, `add_pivot_table`, `set_cell_style` |
| pptx_basic | 10 | `search_slides`, `read_slide_text`, `read_presentation`, `read_slide`, `set_text`, `add_slide`, `delete_slide`, `reorder_slide`, `add_text_box`, `add_image` |
| pptx_design | 6 | `set_background`, `set_font_style`, `add_table`, `add_chart`, `duplicate_slide`, `export_pdf` |

Total: 63 tools across 8 servers. Maximum loaded simultaneously: 16 (any two servers).
Surgical tools (`search_*`, `get_*_outline`, `read_*_range`, `get_*_summary`) are
required — not optional. They are what make the protocol work on documents longer
than ~20 pages on a 9B model.

### Recommended server combinations for common tasks

- Contract editing → `docx_basic` only (8 tools)
- Report with tables → `docx_basic` + `docx_tables` (15 tools)
- Document formatting → `docx_layout` only (7 tools)
- Data entry + formulas → `xlsx_basic` + `xlsx_formulas` (15 tools)
- Dashboard creation → `xlsx_charts` only (5 tools)
- Presentation creation → `pptx_basic` only (8 tools)
- Branded deck → `pptx_basic` + `pptx_design` (14 tools)

These combinations are documented in the README and shown in the installer UI.

---

## 9. Patch protocol — the JSON op format

When a tool accepts a list of operations (batch apply), the format is always an array
of op objects. Every op object has an `"op"` field as its first key. Additional fields
depend on the op type.

### DOCX ops

```json
[
  {
    "op": "replace_text",
    "match": "PARTY_A_NAME",
    "new_text": "Acme Corporation",
    "preserve_style": true
  },
  {
    "op": "insert_after",
    "match": "Section 3. Termination.",
    "new_text": "Either party may terminate this agreement...",
    "style": "Body Text"
  },
  {
    "op": "delete_paragraph",
    "match": "INTENTIONALLY LEFT BLANK"
  },
  {
    "op": "replace_table_cell",
    "table_index": 0,
    "row": 2,
    "col": 1,
    "new_text": "$5,000 USD"
  }
]
```

### XLSX ops

```json
[
  {
    "op": "set_cell",
    "sheet": "Q3 Revenue",
    "cell": "B5",
    "value": 142500
  },
  {
    "op": "set_formula",
    "sheet": "Q3 Revenue",
    "cell": "D5",
    "formula": "=SUM(B5:C5)*1.1"
  },
  {
    "op": "set_conditional_format",
    "sheet": "Q3 Revenue",
    "range": "B2:B20",
    "rule": "greater_than",
    "value": 100000,
    "color": "green"
  }
]
```

### PPTX ops

```json
[
  {
    "op": "set_text",
    "slide_index": 0,
    "shape_name": "Title 1",
    "new_text": "Q3 2026 Results"
  },
  {
    "op": "add_slide",
    "after_index": 2,
    "layout": "Title and Content",
    "title": "Key Metrics",
    "body": "Revenue up 12%\nCAC down 8%"
  }
]
```

### Validation rules enforced by patch_validator

- `ops` must be a list. Never a single object.
- Each element must be a dict with an `"op"` key.
- `"op"` value must be in the server's `allowed_ops` list.
- Required fields per op type must be present and correctly typed.
- Unknown extra fields are allowed (ignored) to support forward compatibility.
- Maximum 50 ops per batch. Larger batches must be split across multiple calls.

---

## 9b. Surgical addressing protocol — token-efficient document access

This section defines the core design pattern that makes the MCP servers viable for
large documents. It supersedes naive full-read approaches wherever performance matters.

### The problem: full reads are fatal for large documents

A 100-page Word document extracts to approximately 40,000-60,000 tokens. A 9B local
model has an effective working context of ~28,000 tokens after tool schemas and system
prompt. This means `read_document` on any substantial document either truncates silently
or overflows the context entirely. Either way, the model fails.

The solution is a **two-phase addressing protocol**: index first, fetch only what is
needed, write back only what changed. The model never sees the full document.

### Phase 1 — Index (structure only, zero content)

An index tool scans the full document and returns a structural map. No paragraph text
is included. No cell values are returned. The index is always small — typically
50-150 tokens regardless of document size.

#### DOCX index format

```python
def get_document_index(file_path: str) -> dict:
    """Return document structure map. No paragraph content included."""
    # Returns section tree built from heading paragraphs
    # Each section: address, heading text, paragraph count, table count
```

```json
{
  "success": true,
  "file": "contract.docx",
  "total_paragraphs": 312,
  "total_tables": 4,
  "total_pages_approx": 18,
  "sections": [
    {
      "address": "§1",
      "heading": "Parties to the Agreement",
      "level": 1,
      "para_count": 6,
      "table_count": 0,
      "para_range": [0, 5]
    },
    {
      "address": "§2",
      "heading": "Scope of Work",
      "level": 1,
      "para_count": 24,
      "table_count": 1,
      "para_range": [6, 29]
    },
    {
      "address": "§3",
      "heading": "Payment Terms",
      "level": 1,
      "para_count": 12,
      "table_count": 2,
      "para_range": [30, 41]
    }
  ]
}
```

The model reads this ~100-token response and knows exactly which section contains the
clause it needs to modify. It never reads sections it does not need.

#### XLSX index format

```json
{
  "success": true,
  "file": "budget.xlsx",
  "sheets": [
    {
      "name": "Q3 Revenue",
      "used_range": "A1:F52",
      "header_row": 1,
      "headers": ["Region", "Jan", "Feb", "Mar", "Q3 Total", "YoY%"],
      "data_rows": 50,
      "named_ranges": ["TotalRevenue", "CostBase", "GrossMargin"],
      "chart_count": 2
    },
    {
      "name": "Dashboard",
      "used_range": "A1:L30",
      "header_row": null,
      "data_rows": 0,
      "named_ranges": [],
      "chart_count": 4
    }
  ]
}
```

#### PPTX index format

```json
{
  "success": true,
  "file": "deck.pptx",
  "slide_count": 24,
  "available_layouts": ["Title Slide", "Title and Content", "Two Content", "Blank"],
  "slides": [
    {
      "index": 0,
      "title": "Q3 2026 Business Review",
      "shape_count": 3,
      "has_table": false,
      "has_chart": false,
      "has_image": true
    },
    {
      "index": 1,
      "title": "Revenue Performance",
      "shape_count": 5,
      "has_table": false,
      "has_chart": true,
      "has_image": false
    }
  ]
}
```

### Phase 2 — Fetch (only the addressed node)

After reading the index, the model calls a fetch tool with a specific address. The
fetch tool returns only the content of that node.

#### Address syntax — DOCX

Addresses use section notation built from heading hierarchy:

| Address | Meaning |
|---|---|
| `§2` | All content of section 2 (heading level 1) |
| `§2.1` | Subsection 1 within section 2 (heading level 2) |
| `§2.p4` | Paragraph 4 within section 2 (zero-indexed) |
| `§2.t0` | First table in section 2 |
| `§2.t0.r3.c1` | Row 3, column 1 of first table in section 2 |
| `p47` | Absolute paragraph 47 (fallback when no headings present) |

Documents with no headings fall back to absolute paragraph indexing (`p0`, `p1`, ...).
The index tool reports which scheme is active via `"address_scheme": "sectioned"` or
`"address_scheme": "flat"`.

```python
def fetch_section(file_path: str, address: str) -> dict:
    """Fetch content of addressed section or paragraph only."""
```

```json
{
  "success": true,
  "address": "§3",
  "heading": "Payment Terms",
  "paragraphs": [
    {"addr": "§3.p0", "text": "Payment shall be made within 30 days...", "style": "Body Text"},
    {"addr": "§3.p1", "text": "Late payments shall incur a penalty...", "style": "Body Text"},
    {"addr": "§3.p2", "text": "All amounts are in USD unless...", "style": "Body Text"}
  ],
  "tables": []
}
```

Token cost: ~150 tokens for a 3-paragraph section. Compare to ~40,000 for full document.

#### Address syntax — XLSX

XLSX already has a natural address system (Excel notation). The fetch layer adds
range-level access on top of cell-level access:

```python
def fetch_range(file_path: str, sheet: str, range: str) -> dict:
    """Fetch only the specified cell range from a sheet."""
```

```json
{
  "success": true,
  "sheet": "Q3 Revenue",
  "range": "A1:F5",
  "headers": ["Region", "Jan", "Feb", "Mar", "Q3 Total", "YoY%"],
  "rows": [
    {"addr": "A2:F2", "values": ["North", 120000, 135000, 118000, 373000, 0.12]},
    {"addr": "A3:F3", "values": ["South", 98000, 102000, 115000, 315000, 0.08]},
    {"addr": "A4:F4", "values": ["East", 87000, 91000, 95000, 273000, 0.15]},
    {"addr": "A5:F5", "values": ["West", 143000, 138000, 151000, 432000, 0.21]}
  ]
}
```

The model fetches only the rows it needs to analyse or edit. A 50-row sheet with 6
columns does not need to be fetched in full if only rows 2-5 are relevant.

#### Address syntax — PPTX

```python
def fetch_slide(file_path: str, slide_index: int) -> dict:
    """Fetch all shapes and text content of one slide only."""

def fetch_shape(file_path: str, slide_index: int, shape_name: str) -> dict:
    """Fetch text content of one specific shape only."""
```

```json
{
  "success": true,
  "slide_index": 1,
  "title": "Revenue Performance",
  "shapes": [
    {
      "name": "Title 1",
      "addr": "slide[1]/shape[Title 1]",
      "type": "text",
      "paragraphs": [
        {"addr": "slide[1]/shape[Title 1]/p0", "text": "Revenue Performance"}
      ]
    },
    {
      "name": "Content Placeholder 2",
      "addr": "slide[1]/shape[Content Placeholder 2]",
      "type": "text",
      "paragraphs": [
        {"addr": "slide[1]/shape[Content Placeholder 2]/p0", "text": "Q3 total: $1.4M"},
        {"addr": "slide[1]/shape[Content Placeholder 2]/p1", "text": "Up 18% YoY"}
      ]
    }
  ]
}
```

### Phase 3 — Surgical write (address + new content only)

The write tool receives a precise address and replacement content. It opens the file,
navigates directly to the addressed node, applies the change, saves, and closes.
No other content is read. No other content is written.

#### DOCX surgical write

```python
def replace_at(file_path: str, address: str, new_text: str) -> dict:
    """Replace content at exact address. Preserves all run formatting."""

def insert_at(file_path: str, address: str, new_text: str, style: str = "Body Text") -> dict:
    """Insert new paragraph after address. Snapshot taken before write."""

def delete_at(file_path: str, address: str) -> dict:
    """Delete paragraph or section at address."""
```

```json
{
  "success": true,
  "op": "replace_at",
  "address": "§3.p0",
  "old_text": "Payment shall be made within 30 days...",
  "new_text": "Payment shall be made within 14 days...",
  "backup": ".mcp_versions/contract_2026-03-25T14-30-00Z.bak",
  "tokens_read": 0,
  "tokens_written": 12
}
```

The `tokens_read` and `tokens_written` fields are informational — they show how
efficient the operation was. A surgical write reads 0 content tokens because it
navigates by address, not by scanning.

#### XLSX surgical write

`set_cell` and `set_formula` already operate this way. The address (`sheet`, `cell`)
is sufficient to navigate directly. No range needs to be read before writing a cell.

```python
def set_cell(file_path: str, sheet: str, cell: str, value: ...) -> dict:
    """Write value to exact cell address. Zero surrounding cells read."""
```

#### PPTX surgical write

```python
def set_text_at(file_path: str, address: str, new_text: str) -> dict:
    """Replace text at shape/paragraph address. Run formatting preserved."""
```

```json
{
  "success": true,
  "op": "set_text_at",
  "address": "slide[1]/shape[Title 1]/p0",
  "old_text": "Revenue Performance",
  "new_text": "Q3 Revenue Performance",
  "backup": ".mcp_versions/deck_2026-03-25T14-30-00Z.bak"
}
```

### Address resolution in shared/

Address parsing and resolution lives in `shared/address_resolver.py`. This is the
module that translates a string like `"§3.p1"` or `"slide[2]/shape[Title 1]/p0"`
into the actual document node — paragraph object, cell object, or shape object.

```python
# shared/address_resolver.py

def resolve_docx_address(doc: Document, address: str) -> DocxNode:
    """
    Parse address string and return the corresponding document node.
    Returns DocxNode with .paragraph, .table, .cell as appropriate.
    Raises AddressError if address does not resolve to an existing node.
    """

def resolve_xlsx_address(wb: Workbook, sheet: str, cell_or_range: str) -> XlsxNode:
    """
    Parse cell address or range string.
    Returns XlsxNode with .cell or .cells as appropriate.
    """

def resolve_pptx_address(prs: Presentation, address: str) -> PptxNode:
    """
    Parse slide/shape/paragraph address string.
    Returns PptxNode with .slide, .shape, .paragraph as appropriate.
    """

def build_docx_index(doc: Document) -> list[dict]:
    """
    Scan document and build section index from heading paragraphs.
    Returns section list with addresses, heading text, para_range.
    """
```

### Tool count impact

The surgical addressing layer adds these tools to existing servers:

| Server | New tools added | Purpose |
|---|---|---|
| `docx_basic` | `get_document_index`, `fetch_section`, `replace_at`, `insert_at`, `delete_at` | Surgical DOCX access |
| `xlsx_basic` | `get_sheet_index`, `fetch_range` | Surgical XLSX access |
| `pptx_basic` | `get_presentation_index`, `fetch_slide`, `fetch_shape`, `set_text_at` | Surgical PPTX access |

The legacy `read_document`, `read_sheet`, and `read_slide` tools remain in the servers
but are now marked as **large-document unsafe** in their docstrings:

```python
@mcp.tool()
def read_document(file_path: str) -> dict:
    """Read full doc. Use get_document_index for large files (>10 pages)."""
```

This keeps backward compatibility while steering the model toward surgical tools when
context budget is limited.

### Surgical addressing in patch_validator

The patch validator gains two new validations for surgical ops:

1. **Address format check** — addresses must match the regex pattern for their format
   (`§\d+(\.\d+)*(\.p\d+|\.t\d+(\.\w+)*)?` for DOCX, Excel notation for XLSX,
   `slide\[\d+\]/shape\[.+\](/p\d+)?` for PPTX).

2. **Address existence check** — before any write, the validator resolves the address
   against the actual document to confirm the node exists. A write to a non-existent
   address returns an error before the snapshot is taken.

### Rule: index before fetch, fetch before write

The model must follow this sequence for any document larger than 10 pages (DOCX) or
any sheet with more than 30 rows (XLSX):

1. Call the index tool (`get_document_index` / `get_sheet_index` / `get_presentation_index`)
2. Identify the target address from the index
3. Call the fetch tool (`fetch_section` / `fetch_range` / `fetch_slide`) to confirm
   the exact paragraph/cell/shape address
4. Call the surgical write tool (`replace_at` / `set_cell` / `set_text_at`)

Skipping step 1 or 2 for large documents is a protocol violation. The tools enforce
this by returning a warning in the response when `read_document` is called on a file
with more than 50 paragraphs:

```json
{
  "success": true,
  "paragraph_count": 312,
  "truncated": true,
  "truncated_at": 150,
  "warning": "Large document. Use get_document_index + fetch_section for targeted access.",
  "paragraphs": [...]
}
```

---

## 10. DOCX engine rules

### The run-level editing rule — most important rule in this file

A Word paragraph (`<w:p>`) contains runs (`<w:r>`). Each run is a sequence of characters
with identical formatting. A single visible word can be split across multiple runs for
reasons unrelated to content (autocorrect history, paste events, tracked changes).

**NEVER do this:**
```python
paragraph.text = "new content"
```

This collapses all runs into one and silently destroys all formatting — bold, italic,
font, color, size, hyperlinks. This is the single most destructive bug possible in
DOCX editing.

**Always do this instead (using docxedit):**
```python
import docxedit
docxedit.replace_string(doc, old_string=match_text, new_string=new_text)
```

`docxedit.replace_string` operates on runs. It finds the match across run boundaries,
replaces only the affected run text, and leaves all other runs untouched.

For cases where `docxedit` cannot handle the operation, edit runs directly:
```python
for run in paragraph.runs:
    if match_text in run.text:
        run.text = run.text.replace(match_text, new_text)
        # run.bold, run.italic, run.font.* are preserved automatically
```

### Paragraph index stability

Paragraph indices are stable within a single document session but shift when paragraphs
are inserted or deleted. The rule is:

- Always re-read the document state after any insert or delete operation.
- Do not use paragraph indices as references across multiple tool calls without
  re-reading in between.
- When matching a paragraph for editing, prefer `match_text` (content-based) over
  `paragraph_index` (position-based) in tool parameters, since content is more stable
  than position.

### Style names

Use the paragraph style name exactly as it appears in the document's style gallery.
Common style names: `"Normal"`, `"Body Text"`, `"Heading 1"` through `"Heading 9"`,
`"List Paragraph"`, `"Quote"`, `"Caption"`. Style names are case-sensitive and
space-sensitive. If the style does not exist in the document, `python-docx` creates
it with default attributes.

### Table indexing

Tables are zero-indexed. `table_index=0` is the first table in the document in reading
order. Row and column indices are also zero-indexed. Return table dimensions in every
`list_tables` response so the LLM can validate indices before writing.

### Export to PDF

The `export_pdf` tool in `docx_layout` uses `docx2pdf`. This requires Microsoft Word
to be installed on Windows and macOS. On Linux it requires LibreOffice. The tool
detects the platform and returns a clear error if neither is available. Never silently
fail a PDF export — return an error dict with instructions.

---

## 11. XLSX engine rules

### openpyxl vs xlsxwriter — when to use each

Use `openpyxl` for all tools that read or modify **existing** `.xlsx` files. This
covers `xlsx_basic`, `xlsx_formulas`, and most of `xlsx_charts`.

Use `xlsxwriter` only for tools that **create a new file from scratch**. `xlsxwriter`
cannot read existing files — it will overwrite them completely. If a tool receives a
`file_path` to an existing file, it must use `openpyxl`. Never use `xlsxwriter` on an
existing file.

### Cell address format

All cell addresses use Excel notation: `"A1"`, `"B5"`, `"Z100"`. Never use row/column
integer tuples in the tool interface — those are internal openpyxl details. Convert to
Excel notation in the engine:

```python
from openpyxl.utils import get_column_letter, column_index_from_string

# row and col are 1-indexed in openpyxl
cell_address = f"{get_column_letter(col)}{row}"
```

### Formula strings

Formula values passed to `set_formula` must include the leading `=` sign:
`"=SUM(B2:B10)"`, not `"SUM(B2:B10)"`. Validate this in `patch_validator`.

The engine stores formula strings verbatim. openpyxl does not evaluate formulas —
the file will contain the formula string, and Excel/LibreOffice will evaluate it when
the file is opened.

### JSON state companion file

Each workbook that has been modified by `xlsx_basic` or higher gets a companion JSON
file at `{filename}.mcp_state.json`. This file tracks the current known cell values
and patch history, allowing the LLM to understand file state without re-reading the
entire workbook on every call.

```json
{
  "version": 3,
  "file": "budget_q3.xlsx",
  "last_modified": "2026-03-25T14:30:00Z",
  "sheets": {
    "Q3 Revenue": {
      "B5": {"value": 142500, "formula": null, "type": "number"},
      "D5": {"value": null, "formula": "=SUM(B5:C5)*1.1", "type": "formula"}
    }
  },
  "patches": [
    {"version": 1, "timestamp": "2026-03-25T10:00:00Z", "op_count": 3},
    {"version": 2, "timestamp": "2026-03-25T12:15:00Z", "op_count": 1}
  ]
}
```

The `read_sheet` tool returns the state JSON alongside the sheet data. Update the
state JSON after every write operation.

### Chart creation

Charts are created with `openpyxl` chart objects for editing existing files. The tool
interface is:

```python
def add_chart(
    file_path: str,
    sheet_name: str,
    chart_type: str,           # "bar", "line", "pie", "area", "scatter"
    data_range: str,           # e.g. "Sheet1!A1:D10"
    title: str,
    anchor_cell: str,          # top-left cell where chart is placed, e.g. "F2"
    width: float = 15.0,       # cm
    height: float = 10.0,      # cm
) -> dict:
```

Supported chart types: `"bar"`, `"line"`, `"pie"`, `"area"`, `"scatter"`. Return an
error dict for unsupported types — do not silently fall back to a default.

---

## 12. PPTX engine rules

### Shape name vs shape index

Always prefer `shape_name` over `shape_index` in tool parameters. Shape names are
stable across slide editing. Shape indices can shift. The `read_slide` tool returns
both the name and index for every shape — the LLM should use the name for subsequent
write operations.

Every slide created by `pptx_basic` has shapes with auto-generated names following
PowerPoint convention: `"Title 1"`, `"Content Placeholder 2"`, etc. Document this in
`read_slide` output.

### Slide layouts

`python-pptx` slide layouts come from the presentation's slide master. The layout
names available depend on the template. The `read_presentation` tool must return the
list of available layout names alongside slide metadata. Do not assume a layout name
exists — validate it from the list before applying.

Common layouts in default PowerPoint templates:
- `"Title Slide"` — large title, subtitle
- `"Title and Content"` — title + content placeholder
- `"Two Content"` — title + two side-by-side placeholders
- `"Blank"` — no placeholders
- `"Title Only"` — title bar only

### Text frames and paragraphs in PPTX

Each shape has a text frame. The text frame contains paragraphs. Each paragraph
contains runs. The same run-level editing rules from the DOCX section apply here.
Never overwrite `shape.text_frame.text` directly — it destroys paragraph-level
formatting. Edit at the paragraph or run level.

### Image insertion

Images are inserted with:

```python
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

slide.shapes.add_picture(
    image_file,
    left=Inches(x),
    top=Inches(y),
    width=Inches(width),
    height=Inches(height),
)
```

The `add_image` tool accepts `x`, `y`, `width`, `height` in inches as float values.
Validate that the image file exists before attempting to insert. Return an error dict
if the file is not found or is not a supported image format (PNG, JPG, GIF, BMP, TIFF).

### Export to PDF

Same constraint as DOCX — requires Word/LibreOffice. Detect platform, return clear
error if unavailable.

---

## 13. Surgical edit protocol — pull only what you need

This section is the most critical performance constraint in the project. Every tool
design decision in sections 10-12 flows from these rules. Read this before implementing
any engine function.

### The problem this solves

A 200-page contract is approximately 60,000-80,000 tokens when fully extracted. A 9B
model has a 32K context window. Reading the whole document is physically impossible,
and even on larger models it wastes the entire context budget on content the model
will never need. The solution is that tools never return the whole document — they
return only the exact nodes the operation requires.

This is the same principle as a database query: you do not `SELECT *` and filter in
Python. You `SELECT` only the columns and rows you need, with a `WHERE` clause. Every
MCP tool in this project is a structured query against a document.

### The four-tool pattern — the fundamental loop

Every document editing task follows this exact sequence. The LLM must never skip steps.

```
Step 1: LOCATE    — find the node(s) by searching, not by reading everything
Step 2: INSPECT   — read only those node(s) to confirm content and structure
Step 3: PATCH     — apply the targeted edit to only those node(s)
Step 4: VERIFY    — read back only the edited node(s) to confirm correctness
```

Example — changing a payment clause in a 200-page contract:

```
User: "Change the payment term from 30 days to 45 days"

Round 1: search_paragraphs(file, query="payment term") 
         → returns [{index: 47, text: "Payment is due within 30 days..."}]
         (reads ~50 tokens, not 60,000)

Round 2: read_paragraph(file, index=47)
         → returns full paragraph with run details
         (reads ~200 tokens)

Round 3: replace_text(file, match="30 days", new_text="45 days", 
                      paragraph_index=47)
         → applies edit, returns confirmation + backup path
         (writes 0 tokens of document content to context)

Round 4: read_paragraph(file, index=47)
         → confirms "Payment is due within 45 days..."
         (reads ~200 tokens)

Total document tokens consumed: ~450
If full read_document had been used: ~60,000+ tokens
```

### DOCX surgical tools — required implementations

These tools enable the four-tool pattern for Word documents. Every `docx_basic` server
must implement all of them.

#### `search_paragraphs(file_path, query, max_results=10)`

Scans paragraphs for text matching `query` (case-insensitive substring match).
Returns only matching paragraphs — never the full document.

```python
# Return format
{
    "success": True,
    "query": "payment term",
    "matches": [
        {"index": 47, "text": "Payment is due within 30 days of invoice.", "style": "Body Text"},
        {"index": 112, "text": "Payment terms are subject to change.", "style": "Body Text"}
    ],
    "total_paragraphs_scanned": 847,
    "truncated": False
}
```

Rules:
- Never return more than `max_results` matches (default 10, max 50).
- Always return `total_paragraphs_scanned` so the model knows document size.
- If `query` is empty string, return `{"success": false, "error": "query cannot be empty"}`.
- Scan is O(n) over paragraphs but returns O(k) where k << n. This is the point.

#### `read_paragraph(file_path, index)`

Returns a single paragraph by index with full run detail. Used in Step 2 (INSPECT)
and Step 4 (VERIFY) of the four-tool pattern.

```python
{
    "success": True,
    "index": 47,
    "text": "Payment is due within 30 days of invoice.",
    "style": "Body Text",
    "runs": [
        {"text": "Payment is due within ", "bold": False, "italic": False, "font": "Calibri", "size": 11},
        {"text": "30 days", "bold": True, "italic": False, "font": "Calibri", "size": 11},
        {"text": " of invoice.", "bold": False, "italic": False, "font": "Calibri", "size": 11}
    ]
}
```

Rules:
- Returns one paragraph. Never more.
- `runs` array shows every run with its formatting — this is what the model needs
  to generate a precise `replace_text` call that preserves formatting.
- If `index` is out of range, return error with `"total_paragraphs"` hint.

#### `search_table_cells(file_path, query, max_results=10)`

Scans all table cells for text matching `query`. Returns cell coordinates, not full
tables.

```python
{
    "success": True,
    "query": "contract value",
    "matches": [
        {"table_index": 0, "row": 3, "col": 0, "text": "Contract Value"},
        {"table_index": 0, "row": 3, "col": 1, "text": "$25,000 USD"}
    ]
}
```

#### `read_table_row(file_path, table_index, row)`

Returns a single row from a table. Used before editing a table cell.

```python
{
    "success": True,
    "table_index": 0,
    "row": 3,
    "cells": [
        {"col": 0, "text": "Contract Value"},
        {"col": 1, "text": "$25,000 USD"},
        {"col": 2, "text": "USD"}
    ]
}
```

#### `get_document_outline(file_path)`

Returns only headings and their paragraph indices — the document's structural skeleton.
This is the equivalent of a table of contents as a navigation index.

```python
{
    "success": True,
    "total_paragraphs": 847,
    "outline": [
        {"index": 0,   "level": 1, "text": "Service Agreement"},
        {"index": 4,   "level": 2, "text": "1. Parties"},
        {"index": 18,  "level": 2, "text": "2. Scope of Work"},
        {"index": 45,  "level": 2, "text": "3. Payment Terms"},
        {"index": 89,  "level": 2, "text": "4. Termination"},
        ...
    ]
}
```

Rules:
- Only returns paragraphs with Heading 1-6 styles.
- Always returns `total_paragraphs` so the model knows document size without
  reading the full content.
- This is the first tool to call on any document the model has never seen.
  It provides a map to navigate by index range.

#### `read_paragraph_range(file_path, start_index, end_index)`

Returns a contiguous range of paragraphs. Used when context says "the payment terms
section starts at paragraph 45" — read from 45 to 88 (next heading minus one).

```python
{
    "success": True,
    "start_index": 45,
    "end_index": 60,
    "paragraphs": [
        {"index": 45, "text": "3. Payment Terms", "style": "Heading 2"},
        {"index": 46, "text": "Invoices are issued monthly.", "style": "Body Text"},
        ...
    ],
    "truncated": False,
    "hint": "Range exceeds 50 paragraphs. Use smaller ranges."
}
```

Rules:
- Maximum range is 50 paragraphs. If `end_index - start_index > 50`, return error
  with the hint above. Force the model to work in bounded windows.
- Always return `"truncated": false` explicitly. The model should never be uncertain
  about whether it got everything it asked for.

### XLSX surgical tools — required implementations

#### `search_cells(file_path, sheet_name, query, max_results=20)`

Scans cell values for text matching `query`. Returns cell addresses only.

```python
{
    "success": True,
    "sheet": "Q3 Revenue",
    "query": "total",
    "matches": [
        {"cell": "A10", "value": "Total Revenue"},
        {"cell": "A20", "value": "Total Expenses"},
        {"cell": "D10", "value": "=SUM(D2:D9)"}
    ]
}
```

#### `read_cell_range(file_path, sheet_name, range_address)`

Returns a bounded cell range as a 2D array. Maximum 200 cells per call.

```python
# read_cell_range(file, "Q3 Revenue", "A1:D10")
{
    "success": True,
    "sheet": "Q3 Revenue",
    "range": "A1:D10",
    "cell_count": 40,
    "data": [
        [{"cell": "A1", "value": "Region", "formula": null}, ...],
        ...
    ]
}
```

Rules:
- Maximum 200 cells (10×20 or 5×40, etc.). Return error if range exceeds this.
  Force the model to work in bounded windows.
- Include both `value` (evaluated result) and `formula` (raw formula string if any)
  for every cell.

#### `get_sheet_summary(file_path, sheet_name)`

Returns sheet dimensions and a sample of the first row and first column — enough
context to understand the sheet's structure without reading all the data.

```python
{
    "success": True,
    "sheet": "Q3 Revenue",
    "dimensions": {"rows": 150, "cols": 8, "last_cell": "H150"},
    "header_row": [
        {"cell": "A1", "value": "Region"},
        {"cell": "B1", "value": "Q1"},
        {"cell": "C1", "value": "Q2"},
        {"cell": "D1", "value": "Q3"}
    ],
    "first_col_sample": [
        {"cell": "A2", "value": "North"},
        {"cell": "A3", "value": "South"},
        {"cell": "A4", "value": "East"},
        {"cell": "A5", "value": "West"},
        "... 146 more rows"
    ]
}
```

### PPTX surgical tools — required implementations

#### `read_slide_text(file_path, slide_index)`

Returns only the text content of all shapes on one slide — no formatting details.
Used for quick content scanning.

```python
{
    "success": True,
    "slide_index": 3,
    "shapes": [
        {"name": "Title 1", "text": "Q3 Financial Results"},
        {"name": "Content Placeholder 2", "text": "Revenue: $2.1M\nGrowth: 12%"}
    ]
}
```

#### `search_slides(file_path, query)`

Scans all slide text for `query`. Returns slide indices and shape names only.

```python
{
    "success": True,
    "query": "revenue",
    "matches": [
        {"slide_index": 3, "shape_name": "Title 1", "text": "Q3 Financial Results"},
        {"slide_index": 3, "shape_name": "Content Placeholder 2", "text": "Revenue: $2.1M"},
        {"slide_index": 7, "shape_name": "Content Placeholder 2", "text": "Revenue target: $3M"}
    ],
    "total_slides_scanned": 12
}
```

### The token budget discipline — hard rules for every tool

These rules are enforced by the tool implementations, not by the model. The model
cannot be trusted to limit its own reads. The tools must enforce limits.

| Tool category | Maximum output size | Enforcement |
|---|---|---|
| Full document read (`read_document`) | 500 paragraphs or truncate | `"truncated": true` flag |
| Paragraph range read | 50 paragraphs | Error if exceeded |
| Table read | 20 rows × 10 cols = 200 cells | Error if exceeded |
| Cell range read | 200 cells | Error if exceeded |
| Search results | 50 matches | `max_results` parameter |
| Slide read | 1 slide | Single slide only |
| Sheet summary | header + 5 sample rows | Fixed |

Every tool that returns content must include a `"token_estimate"` field in its
response. This is calculated as `len(str(response)) // 4` (rough approximation).
The model uses this to budget its remaining context.

```python
# Add to every tool response
response["token_estimate"] = len(str(response)) // 4
```

### Prohibited patterns — what tools must never do

These patterns are explicitly banned. If you find code in `engine.py` that does any
of these, it is a bug:

**NEVER return the full document text from a write tool.**
A `replace_text` call returns confirmation of what changed. It does not return the
updated document content. If the model wants to verify, it calls `read_paragraph`.

**NEVER implement a "read then write" in a single tool.**
No tool does both reading and writing in one call. Read is read. Write is write.
The model does two tool calls. This keeps tools composable and testable.

**NEVER return all paragraphs from `search_paragraphs` when zero matches found.**
Return `{"success": true, "matches": [], "hint": "Try a different search term."}`.
Do not fall back to returning the full document as a "helpful" response.

**NEVER load an entire workbook into memory to find one cell.**
Use openpyxl's `read_only=True` mode for search operations:
```python
wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
```
This streams the file and avoids loading all cell data into RAM.

**NEVER return raw XML from any tool.**
The OOXML format underneath `.docx` and `.xlsx` is noisy and opaque. Return clean
Python dicts. If a caller needs raw XML for debugging, that is a developer operation,
not a tool operation.

### Adding surgical tools to the tool inventory

Every server tier must have at minimum one `search_*` tool and one bounded `read_*`
tool before any write tools are considered complete. The checklist in section 26
(progress tracker) reflects this — search and bounded read are listed before write
tools for every server.

The surgical tools count toward the per-server tool limit of 10. This is intentional:
surgical read tools are just as important as write tools and deserve to occupy slots
in the tool inventory.

---

## 14. Version control layer

### Snapshot naming convention

```
.mcp_versions/budget_q3_2026-03-25T14-30-00Z.bak
```

The timestamp uses ISO 8601 with colons replaced by hyphens for filesystem
compatibility. The base filename (without extension) is preserved. The `.bak`
extension is always used regardless of the original file type.

### Patch log

Each server that accepts patch arrays writes a companion patch log alongside the
snapshot:

```
.mcp_versions/budget_q3_2026-03-25T14-30-00Z.patch.json
```

This file contains the full op array that was applied. This allows post-hoc
inspection of what changed and why.

### Rollback

The `restore_version` tool is available in every `_basic` server. It takes `file_path`
and `timestamp` and copies the backup over the working file. It does NOT take a new
snapshot before restoring — the user is intentionally reverting to a past state.

### History retention

`.mcp_versions/` retains all snapshots indefinitely. The project does not
auto-prune history. Users who want to clean up can delete the `.mcp_versions/`
directory manually. Document this in the README.

### Cross-server version control

The `shared/version_control.py` module is used by all servers. Version history is
per-file, not per-server. A file's history shows all edits regardless of which server
made them.

---

## 14. Error handling contract

Every engine function must return a dict. Never raise. The return dict must follow
this schema:

**On success:**
```python
{
    "success": True,
    "op": "name_of_operation",
    # operation-specific fields
}
```

**On failure:**
```python
{
    "success": False,
    "error": "Human-readable description of what went wrong.",
    "hint": "What the model should try instead or check.",
    # include "backup" if a snapshot was taken before the failure
}
```

### Standard error messages

Use these exact error messages for common failure types so the model can learn to
recognize them:

| Situation | Error message | Hint |
|---|---|---|
| File not found | `"File not found: {path}"` | `"Check that file_path is absolute and the file exists."` |
| Wrong file type | `"Expected .docx file, got .{ext}"` | `"Use the correct server for this file type."` |
| Match not found | `"match_text not found in document"` | `"Use read_document to verify the exact text before replacing."` |
| Invalid op | `"Unknown op: {op_name}"` | `"Allowed ops for this server: {allowed_ops}"` |
| Index out of range | `"paragraph_index {n} out of range (0-{max})"` | `"Use read_document to get current paragraph count."` |
| Sheet not found | `"Sheet '{name}' not found"` | `"Use list_sheets to get available sheet names."` |
| Cell address invalid | `"Invalid cell address: {addr}"` | `"Use Excel notation like B5 or C12."` |

---

## 15. Testing rules

### Test structure

Every test file mirrors one server. Tests are co-located in `tests/` (not inside
server directories). Tests import directly from `engine.py` — not from `server.py`.
This keeps tests independent of the MCP protocol layer.

```python
# tests/test_docx_basic.py
from servers.docx_basic.engine import read_document, replace_text

def test_read_document_returns_paragraphs(simple_contract_path):
    result = read_document(str(simple_contract_path))
    assert result["success"] is True
    assert result["paragraph_count"] > 0
    assert all("text" in p for p in result["paragraphs"])

def test_replace_text_preserves_bold(complex_contract_path, tmp_path):
    # copy fixture to tmp_path to avoid mutating fixtures
    import shutil
    target = tmp_path / "contract.docx"
    shutil.copy(complex_contract_path, target)

    result = replace_text(str(target), "PARTY_A_NAME", "Acme Corp")
    assert result["success"] is True

    # verify formatting preserved
    from docx import Document
    doc = Document(str(target))
    for para in doc.paragraphs:
        if "Acme Corp" in para.text:
            for run in para.runs:
                if "Acme Corp" in run.text:
                    assert run.bold is True  # was bold before replace
```

### Fixture rules

Test fixtures in `tests/fixtures/` are committed to the repo. They are real office
files, not programmatically generated ones. This is critical — bugs in run-level
editing only appear in real documents with real formatting complexity.

Required fixtures:
- `contract_simple.docx` — basic paragraphs, no tables, minimal formatting
- `contract_complex.docx` — multi-run paragraphs, bold/italic mixed within runs,
  tables, headers, footers
- `report_tables.docx` — multiple tables, merged cells
- `budget_simple.xlsx` — flat data, no formulas
- `budget_formulas.xlsx` — SUM, IF, VLOOKUP formulas
- `dashboard.xlsx` — existing charts, conditional formatting
- `deck_simple.pptx` — title + content slides
- `deck_images.pptx` — slides with embedded images

Fixtures must not be regenerated by tests. If you need a modified version, use
`tmp_path` to copy and modify within the test.

### Coverage requirements

- `shared/` modules: 100% line coverage
- `engine.py` for all servers: ≥ 90% line coverage
- Error paths must be explicitly tested — at least one test per error condition
  listed in section 14

### What must be tested for every write operation

1. Success case on the correct file type
2. The written content is readable back and correct
3. A snapshot was created in `.mcp_versions/`
4. A `"backup"` key is present in the return dict
5. Failure case: file does not exist
6. Failure case: wrong file type (e.g., passing `.xlsx` to a DOCX tool)
7. Formatting preservation (for DOCX operations that touch styled text)

---

## 16. MCP tool schema rules

FastMCP generates JSON schemas from Python type annotations. Follow these rules to
produce clean schemas that 9B local models can reliably interpret.

### Required parameter types

Only use these types for tool parameters:
- `str` — for file paths, text content, cell addresses, sheet names, op names
- `int` — for indices (paragraph_index, row, col, slide_index)
- `float` — for dimensions (width, height in inches or cm)
- `bool` — for flags (preserve_style, include_headers)
- `list[dict]` — for op arrays (batch operations only)

Do not use `Optional[T]`, `Union[T, S]`, `Any`, `dict`, or custom Pydantic models
as parameter types. If a parameter is optional, use a default value:
```python
def replace_text(file_path: str, match: str, new_text: str, preserve_style: bool = True)
```

### Enum values

When a parameter accepts only specific string values (e.g., `chart_type`), document
the allowed values in the docstring, not the type annotation. Do not use Python `Enum`
classes as parameter types — they generate complex JSON schemas that confuse small
models.

```python
def add_chart(
    file_path: str,
    chart_type: str,   # allowed: "bar", "line", "pie", "area", "scatter"
    ...
) -> dict:
    """Create chart from data range. chart_type: bar, line, pie, area, scatter."""
```

### Tool naming

Tool function names are lowercase snake_case verbs: `read_document`, `replace_text`,
`add_chart`, `set_formula`, `delete_paragraph`. The verb comes first. Do not use
nouns-first names like `document_read` or `chart_add`.

The verb set is restricted to: `read`, `list`, `set`, `add`, `delete`, `insert`,
`replace`, `restore`, `export`, `get`. Do not invent new verbs without a compelling
reason.

---

## 17. LM Studio and local model constraints

### Context window budget

LM Studio running Qwen 3.5 9B effectively uses a 32K token context window. The MCP
tool schemas consume approximately 60-120 tokens per tool depending on parameter count.

Budget allocation when 8 tools are loaded (docx_basic):
- Tool schemas: ~700 tokens
- System prompt: ~200 tokens
- Available for document content + conversation: ~31,000 tokens

A 50-page Word document extracts to approximately 15,000-20,000 tokens of text. This
fits comfortably. A 200-page document may not. The `read_document` tool should truncate
output if it exceeds 20,000 tokens and return a `"truncated": true` flag with a
`"hint"` telling the model to use `read_paragraph` to access specific sections.

### Tool description length

Tool descriptions are part of the tool schema sent to the model on every turn. They
are not just documentation — they consume real context budget. Keep them ≤ 80 chars.
Test this with `len(description) <= 80` in CI.

### Parameter description length

Parameter descriptions (in the `Field(description=...)` if used) are also included in
the schema. Do not use `Field()` for parameters unless the name is genuinely ambiguous.
The parameter name itself should be self-documenting: `cell_address` is better than
`cell: str = Field(description="The cell address in A1 notation")`.

### Model self-correction

When a tool returns `{"success": false, "error": "...", "hint": "..."}`, the local
model needs the `"hint"` field to recover without human intervention. The hint must
be actionable in one step: `"Use read_document to get current paragraph count."` is
good. `"Invalid input."` is not acceptable.

### Streaming tool calls

LM Studio 0.4.x streams tool calls. The tool result is sent back to the model before
it finishes generating. Engine functions must return quickly — avoid operations that
take more than 5 seconds. For large files, truncate output rather than processing the
entire file.

---

## 18. Installer and distribution

### install.sh (Linux / macOS)

The script does exactly these steps in order:

1. Check Python version ≥ 3.11. If not found, print install URL and exit 1.
2. Check if `uv` is installed. If not, install via `curl -LsSf https://astral.sh/uv/install.sh | sh`.
3. Run `uv sync` from the repo root.
4. Ask the user which servers they want to register (numbered menu).
5. Run `python install/mcp_config_writer.py --servers <selected> --config <detected_path>`.
6. Print: "Done. Restart LM Studio and you should see the tools."

The script must be idempotent — running it twice should not duplicate entries in
`mcp.json` or break an existing installation.

### install.bat (Windows)

Same logic as `install.sh` using Windows batch syntax. Detect Python via `py --version`
and `python --version`. `uv` installs via PowerShell: 
`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`.

### mcp_config_writer.py

Detects the LM Studio `mcp.json` path by OS:
- macOS: `~/Library/Application Support/LM Studio/mcp.json`
- Windows: `%APPDATA%\LM Studio\mcp.json`
- Linux: `~/.config/LM Studio/mcp.json`

Reads existing config using `json5` (handles comments + trailing commas). Adds new
server entries. Skips servers that are already registered (keyed by server name).
Writes atomically via temp file + rename.

Never removes existing server entries. Never modifies existing entries. Append-only.

### GitHub release artifacts

On release tag, CI builds:
- `office-mcp-windows-x64.zip` — repo + install.bat + all server deps pre-bundled
- `office-mcp-macos.tar.gz` — repo + install.sh + all server deps pre-bundled
- `office-mcp-linux.tar.gz` — repo + install.sh + all server deps pre-bundled

Pre-bundling deps means the user does not need internet access after downloading the
release archive. `uv export --frozen > requirements.txt` + download wheels.

---

## 19. Naming conventions

### Files and directories

- Server directories: `{app}_{tier}` — `docx_basic`, `xlsx_charts`, `pptx_design`
- Python files: `snake_case.py`
- Test files: `test_{server_name}.py`
- Fixture files: `{description}_{complexity}.{ext}` — `contract_simple.docx`

### Python identifiers

- Functions: `snake_case` verbs — `read_document`, `apply_patch`
- Classes: `PascalCase` — `PatchValidator`, `VersionSnapshot`
- Constants: `UPPER_SNAKE_CASE` — `MAX_OPS_PER_BATCH = 50`
- Module-level variables: `snake_case`
- Private helpers: `_snake_case` with leading underscore

### MCP tool names (as registered in FastMCP)

Tool names are derived from the function name automatically by FastMCP. Function names
become the tool name. Keep them unique across all servers so the user can identify
which server a tool belongs to when reading logs:

`docx_basic` tools use names like `read_document`, `replace_text`.
`xlsx_basic` tools use names like `read_sheet`, `set_cell`.
`pptx_basic` tools use names like `read_presentation`, `add_slide`.

If two servers could have a tool with the same natural name (e.g., both `docx_layout`
and `pptx_design` could have `export_pdf`), that is acceptable — each server is
registered separately in `mcp.json` and they are never both loaded at once.

### Commit messages

Format: `{type}({scope}): {description}`

Types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`
Scope: server name or `shared` or `install`

Examples:
- `feat(docx_basic): add replace_text with run-level preservation`
- `fix(shared): fix snapshot path collision on Windows`
- `test(xlsx_basic): add formula validation edge cases`
- `docs(readme): add LM Studio setup section`

---

## 20. What Claude must never do

These are hard prohibitions. If asked to do any of these, refuse and explain why.

1. **Never use `paragraph.text = value`** to edit a paragraph in a DOCX file. This
   destroys run-level formatting. Always use `docxedit.replace_string()` or run-level
   iteration.

2. **Never use `xlsxwriter` to open an existing `.xlsx` file**. `xlsxwriter` is
   write-only. It will truncate the file. Only use it for creating new files from
   scratch.

3. **Never write a tool that takes more than 10 parameters**. If an operation needs
   more than 10 parameters, split it into multiple tools or accept a `dict` as a
   single `config` parameter (documented in the docstring).

4. **Never add business logic to `server.py`**. Tool functions in `server.py` call
   `engine.py`. Any logic that manipulates document data belongs in `engine.py`.

5. **Never print to stdout in any engine or shared module**. The MCP stdio transport
   uses stdout for the JSON-RPC protocol. Any print statement corrupts the channel.
   Use `sys.stderr` for debug output.

6. **Never write to a file without calling `snapshot()` first**. No exceptions.

7. **Never return a plain string from a tool function**. Always return a dict.

8. **Never exceed 10 tools in a single server**. This is a hard limit for local model
   reliability.

9. **Never add a new dependency without updating both the server's `pyproject.toml`
   and the relevant section of this `CLAUDE.md`**. Hidden dependencies cause
   installation failures on user machines.

10. **Never modify `shared/` from within a server directory**. `shared/` is a
    read-only import target for all servers.

---

## 21. Adding a new tool — step-by-step checklist

Follow this checklist every time you add a tool to an existing server.

- [ ] Verify the server will not exceed 10 tools after adding this one
- [ ] Check that the tool name follows the verb-first snake_case convention
- [ ] Write the engine function in `engine.py` first (no MCP imports)
- [ ] Engine function returns a dict with `"success"` as first key
- [ ] Engine function calls `snapshot()` before any file write
- [ ] Engine function includes `"backup"` path in return dict on write operations
- [ ] Engine function returns error dict (not raise) for all failure cases
- [ ] Error dict includes `"hint"` field with actionable recovery instruction
- [ ] Add `@mcp.tool()` decorator in `server.py` calling the engine function
- [ ] Tool docstring is ≤ 80 characters
- [ ] All parameters have type annotations
- [ ] Optional parameters have primitive default values
- [ ] Add at least one success test in the corresponding `tests/test_{server}.py`
- [ ] Add at least one failure test (file not found)
- [ ] Run `uv run pytest tests/test_{server}.py` — all tests pass
- [ ] Run `uv run ruff check servers/{server_name}/`
- [ ] Run `uv run pyright servers/{server_name}/`
- [ ] Update the tool inventory table in this `CLAUDE.md` section 8

---

## 22. Adding a new server — step-by-step checklist

Follow this checklist when creating a new server from scratch.

- [ ] Confirm no existing server covers this tier of functionality
- [ ] Confirm tool count will be ≤ 10 at launch
- [ ] Create `servers/{app}_{tier}/` directory
- [ ] Create `servers/{app}_{tier}/__init__.py` (empty)
- [ ] Create `servers/{app}_{tier}/engine.py` following template in section 7
- [ ] Create `servers/{app}_{tier}/server.py` following template in section 7
- [ ] Create `servers/{app}_{tier}/pyproject.toml` with `shared` as dependency
- [ ] Add server to `[tool.uv.workspace] members` in root `pyproject.toml`
- [ ] Run `uv sync` — no errors
- [ ] Create `tests/test_{app}_{tier}.py` with at least 3 tests
- [ ] Add required fixtures to `tests/fixtures/` if not present
- [ ] Add mcp.json snippet to server README section
- [ ] Add server to install menu in `install/install.sh` and `install.bat`
- [ ] Add server to `install/mcp_config_writer.py` server registry
- [ ] Add server to recommended combinations in section 8 of this file
- [ ] Run full test suite `uv run pytest tests/` — all pass

---

## 23. Common failure modes and how to avoid them

### Failure: Tool call produces empty string output

Cause: Engine function printed to stdout. stdout is the MCP stdio transport channel.
Fix: Replace all `print()` calls with `logging.getLogger(__name__).debug()`.
Detection: Run server with `MCP_DEBUG=1` and inspect stderr vs stdout.

### Failure: LM Studio shows "tool not found" after registering server

Cause: The `command` in `mcp.json` is not on PATH, or the `--directory` path is wrong.
Fix: Use absolute paths in mcp.json. Verify `uv` is on PATH by running `uv --version`
in terminal. Re-run `mcp_config_writer.py`.

### Failure: replace_text strips bold/italic from replaced text

Cause: Used `paragraph.text = value` instead of `docxedit.replace_string()`.
Fix: Replace all direct `.text =` assignments on paragraph objects with docxedit calls.

### Failure: openpyxl produces corrupt .xlsx after chart modification

Cause: Chart data references were not updated when the data range changed. openpyxl
chart objects hold stale references after the underlying data moves.
Fix: Always delete and recreate charts rather than modifying them in place. The
`update_chart` tool should call the delete-then-add pattern internally.

### Failure: Version snapshot creates infinite loop of backups

Cause: Tool calls `snapshot()` then modifies `.mcp_versions/` directory which triggers
a file watcher that calls the tool again.
Fix: `file_utils.resolve_path()` must reject paths inside `.mcp_versions/` directories.

### Failure: 9B model hallucinates required parameter names

Cause: Tool has too many parameters or parameter names are ambiguous.
Fix: Rename parameters to be maximally self-documenting. Reduce parameter count by
combining related params into a single `config: str` JSON string if needed. Keep
tool count per server ≤ 8 for the most reliable results with 9B models.

### Failure: install.sh fails silently on macOS with SIP enabled

Cause: System Integrity Protection prevents writing to `/usr/local/` without sudo.
Fix: `uv` installs to `~/.local/bin/` by default — document that the user may need to
add `~/.local/bin` to PATH. Add a PATH check in `install.sh`.

### Failure: mcp_config_writer.py corrupts existing mcp.json

Cause: LM Studio's mcp.json sometimes contains trailing commas or inline comments
(it uses a relaxed JSON format). Standard `json.loads()` fails on these.
Fix: Use `json5` library for reading, standard `json.dumps()` for writing. The file
will be "upgraded" to strict JSON on first write — document this.

---

## 24. Dependency policy

### Approved dependencies

These libraries are approved for use. Do not add alternatives without discussion.

| Library | Used in | Version constraint |
|---|---|---|
| `mcp[cli]` | all servers | `>=1.2.0` |
| `python-docx` | docx servers | `>=1.1.0` |
| `docxedit` | docx servers | `>=1.2.0` |
| `openpyxl` | xlsx servers | `>=3.1.0` |
| `xlsxwriter` | xlsx_charts | `>=3.2.0` |
| `python-pptx` | pptx servers | `>=0.6.23` |
| `pdfplumber` | pdf tools | `>=0.11.0` |
| `docx2pdf` | docx_layout | `>=0.1.8` |
| `json5` | install only | `>=0.9.0` |
| `pytest` | tests | `>=8.0` |
| `ruff` | dev | `>=0.4.0` |
| `pyright` | dev | `>=1.1.0` |

### Adding a new dependency

Before adding any new library:

1. Check if an approved library can already do the job.
2. Verify the license is MIT, Apache 2.0, or BSD. No GPL libraries.
3. Check the library has been updated within the last 12 months.
4. Check it does not have known security vulnerabilities via `uv audit`.
5. Add it to the server's `pyproject.toml` with a minimum version constraint.
6. Add it to the approved table in this section.
7. Document why it was added and what alternative was rejected.

### Prohibited libraries

- `Spire.Doc` — commercial license, not open source
- `Aspose` — commercial license
- `win32com` / `pywin32` — Windows-only, defeats cross-platform goal
- `pandas` — too heavy for this use case; openpyxl is sufficient
- `LibreOffice UNO API` — requires LibreOffice installed; too complex a dependency

---

## 25. Git and PR rules

### Branch naming

`{type}/{description-in-kebab-case}`

Examples:
- `feat/docx-basic-replace-text`
- `fix/xlsx-formula-validation`
- `test/pptx-basic-fixtures`
- `docs/claude-md-update`

### PR requirements

Every PR must:

- Target `main` branch
- Have a description explaining what changed and why
- Pass all CI checks: `pytest`, `ruff check`, `pyright`
- Not decrease test coverage below 90% for modified files
- Not add a tool that exceeds 80 chars in its description
- Not add a server that exceeds 10 tools
- Update this `CLAUDE.md` if architectural decisions changed

### Commit hygiene

- One logical change per commit
- No "WIP" or "fix typo" commits on main — squash before merge
- Never commit `.mcp_versions/` directories
- Never commit `uv.lock` changes caused by platform-specific resolution;
  always regenerate on Linux if `uv.lock` shows platform-specific diffs

### CI checks (GitHub Actions)

```yaml
# .github/workflows/ci.yml runs on every PR:
- uv sync --frozen
- uv run ruff check .
- uv run ruff format --check .
- uv run pyright servers/ shared/
- uv run pytest tests/ --cov=servers --cov=shared --cov-fail-under=90
- python -c "
    import ast, pathlib
    for f in pathlib.Path('servers').rglob('server.py'):
        src = f.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.decorator_list:
                    docstring = ast.get_docstring(node) or ''
                    assert len(docstring) <= 80, f'{f}:{node.name} docstring > 80 chars'
  "
```

---

## 26. Source code editing protocol — line-level edits

This section governs how Claude Code edits source files in this repository. The goal
is to minimise token consumption, avoid full-file rewrites, and make every edit
reviewable at the line level — exactly the same philosophy applied to document editing
in sections 10-12, now applied to the codebase itself.

### The core rule: never rewrite a file that already exists

When editing an existing `.py`, `.toml`, `.sh`, `.json`, or `.md` file, Claude Code
must use targeted replacement, not full-file generation. A full-file rewrite:

- Consumes 3-10× more tokens than a targeted edit
- Destroys surrounding context the model did not intend to change
- Makes the diff unreadable in code review
- Risks introducing regressions in untouched sections

**The only time a full file write is acceptable:**
- Creating a brand new file that does not yet exist on disk
- The file is under 30 lines total and the change touches > 60% of it

For everything else, use the str_replace protocol below.

---

### str_replace protocol

Every source code edit follows this format. The model identifies the minimal unique
string to replace and provides the replacement. The engine finds the old string,
verifies it appears exactly once, and swaps it.

**Format the model must use:**

```
EDIT: servers/docx_basic/engine.py
<<<OLD>>>
def replace_text(
    file_path: str,
    match_text: str,
    new_text: str,
) -> dict:
<<<NEW>>>
def replace_text(
    file_path: str,
    match_text: str,
    new_text: str,
    preserve_style: bool = True,
) -> dict:
<<<END>>>
```

Rules for the OLD block:
- Must be a verbatim copy of the existing file content — no paraphrasing
- Must include enough surrounding lines to be unique in the file (minimum 3 lines
  of context if the changed line alone is not unique)
- Must not include line numbers — line numbers are display-only and not part of the
  file content
- Must match indentation exactly, including trailing whitespace
- Must appear exactly once in the file — if the string appears twice, add more
  context lines until it is unique

Rules for the NEW block:
- Contains only the replacement content — not the entire function or class
- Must maintain consistent indentation with surrounding code
- Must not introduce trailing whitespace
- Empty lines within the block are preserved exactly

Rules for the edit operation:
- One EDIT block per logical change
- Multiple EDIT blocks are allowed in one response for multi-location changes
- Each EDIT block is applied sequentially — later blocks must account for line
  shifts caused by earlier blocks in the same response
- If an OLD block cannot be found exactly, the edit fails — do not attempt fuzzy
  matching or approximate replacement

---

### Granularity rules — what counts as one edit

**One edit per:**
- Adding or removing a single parameter from a function signature
- Changing a return value in one branch
- Fixing one variable name across one function
- Adding one import line
- Changing one constant value
- Adding or removing one decorator

**Split into multiple edits when:**
- Changes span more than one function
- Changes span more than one class
- Changes are in different files (use separate EDIT blocks)
- The logical intent of two changes is independent (different bugs, different features)

**Forbidden in one edit:**
- Combining a refactor with a bug fix
- Combining a new feature with a style change
- Changing both the function signature and its call sites in one block

---

### Read before edit — always

Before editing any file, Claude Code must read the relevant section of the file to
verify the current state matches what is expected. The sequence is always:

1. `view` the file or relevant line range
2. Confirm the OLD string exists verbatim
3. Apply the `str_replace` edit
4. `view` the changed section to verify the edit applied correctly

Never assume the file content from a previous read. Files change between sessions.
Always re-read immediately before editing.

---

### What to do when a str_replace fails

If the OLD string is not found exactly:

1. Re-read the file at the suspected location
2. Check for whitespace differences (tabs vs spaces, trailing spaces, Windows line endings)
3. Check for Unicode differences (smart quotes vs straight quotes)
4. Narrow the OLD block to fewer lines and retry
5. If still failing, report the exact diff between expected and actual content —
   do not silently fall back to a full file rewrite

A failed str_replace is never a reason to rewrite the entire file.

---

### Engine.py edit size limits

Given that `engine.py` files contain document manipulation logic and can grow to
400-600 lines, these limits apply:

- **Adding a new function:** write only the new function block, inserted after the
  last function in the file using a str_replace that targets the final `\n` and the
  closing line before it
- **Fixing a bug in one function:** str_replace targeting only the changed lines
  within that function — maximum 20 lines in the OLD block for a bug fix
- **Refactoring a function signature:** one str_replace for the `def` line + docstring,
  one separate str_replace for each call site

---

### Token cost comparison (reference numbers)

These are approximate token counts to illustrate why surgical edits matter when
working with a local 9B model that has a 32K context window:

| Operation | Approach | ~Tokens consumed |
|---|---|---|
| Add one parameter to a function | str_replace (5 lines) | ~40 tokens |
| Add one parameter to a function | Full file rewrite (300 lines) | ~900 tokens |
| Fix one bug in engine.py | str_replace (8 lines) | ~65 tokens |
| Fix one bug in engine.py | Full file rewrite (400 lines) | ~1,200 tokens |
| Add a new tool to server.py | str_replace (12 lines) | ~95 tokens |
| Add a new tool to server.py | Full file rewrite (150 lines) | ~450 tokens |

At 9B model scale with a 32K context window, every 1,000 tokens saved is 3% more
context available for document content, conversation history, and tool results.
Over a full coding session of 20 edits, str_replace saves approximately 15,000-20,000
tokens compared to full rewrites — the equivalent of freeing up half the context window.

---

### CLAUDE.md is exempt from str_replace line limits

This file (`CLAUDE.md`) is documentation and grows deliberately. When updating
`CLAUDE.md`, full section replacements are acceptable since sections are large and
self-contained. Use str_replace targeting the full section being updated, identified
by its `## N. Section title` header line and the following `---` separator.

---

## 27. Git integration for document edits

This section covers optional Git integration that runs alongside the `.mcp_versions/`
snapshot system. When enabled, document edits are committed to Git automatically,
giving users a proper Git history on their working documents — not just binary backups.

### When Git integration applies

Git integration is opt-in. It activates only when:

1. The file being edited is inside a Git repository (`git -C <dir> rev-parse` succeeds)
2. The user has not disabled it via the `GIT_INTEGRATION=false` environment variable

When Git is not available or the file is not in a Git repo, the server falls back
silently to snapshot-only behaviour. Never fail a document edit because Git is absent.

---

### The gitops module — shared/gitops.py

A new shared module handles all Git operations. No server imports `subprocess` directly.

```python
# shared/gitops.py

def is_git_repo(path: str) -> bool:
    """Return True if path is inside a Git repository."""

def stage_file(file_path: str) -> bool:
    """Run git add on file_path. Return True on success."""

def commit(repo_path: str, message: str, author: str = "office-mcp") -> str | None:
    """
    Run git commit with message. Return commit SHA on success, None on failure.
    Never raises — Git failures are non-fatal for document editing.
    """

def get_log(repo_path: str, file_path: str, max_entries: int = 20) -> list[dict]:
    """
    Return Git log for file_path as list of dicts.
    Each dict: {"sha": str, "message": str, "timestamp": str, "author": str}
    """

def create_branch(repo_path: str, branch_name: str) -> bool:
    """Create and checkout a new branch. Return True on success."""

def current_branch(repo_path: str) -> str:
    """Return current branch name, or "HEAD" if detached."""

def diff_staged(repo_path: str) -> str:
    """Return git diff --staged output as string."""
```

All functions catch exceptions and return safe defaults. A broken Git environment
never propagates an exception to the MCP tool.

---

### Commit message format for document edits

Every auto-commit from an office-mcp tool uses this message format:

```
[office-mcp] {op}: {summary}

Server: {server_name}
File: {relative_file_path}
Ops applied: {op_count}
Snapshot: {backup_filename}
```

Examples:

```
[office-mcp] replace_text: replaced 3 placeholders in contract_q1.docx

Server: docx-basic
File: contracts/contract_q1.docx
Ops applied: 3
Snapshot: contract_q1_2026-03-25T14-30-00Z.bak
```

```
[office-mcp] set_cell: updated 5 cells in budget_q3.xlsx

Server: xlsx-basic
File: finance/budget_q3.xlsx
Ops applied: 5
Snapshot: budget_q3_2026-03-25T09-15-00Z.bak
```

The `[office-mcp]` prefix makes auto-commits easily filterable in `git log`.

---

### Where Git commit happens in the write flow

The commit is the last step after a successful write, not before. The sequence is:

```
1. validate_ops(ops, allowed_ops)          # patch_validator
2. snapshot(file_path)                     # version_control — always
3. apply document changes                  # engine logic
4. update .mcp_state.json if xlsx          # xlsx only
5. git add <file_path>                     # gitops — if in git repo
6. git commit -m "[office-mcp] ..."        # gitops — if staged
7. return success dict with git_sha        # include SHA if committed
```

If step 6 fails (e.g. nothing to commit, Git not installed), the function still
returns `{"success": true}` — the document was edited successfully. The return dict
includes `"git_committed": false` and `"git_error": "..."` for transparency.

---

### Branch-per-task pattern (optional, advanced)

For users who want to isolate document edits in feature branches, the `docx_basic`
`restore_version` tool supports an optional `create_branch` parameter:

```python
restore_version(
    file_path="contracts/contract_q1.docx",
    timestamp="2026-03-25T14-30-00Z",
    create_branch="contract-revision-april",   # optional
)
```

When `create_branch` is provided:
1. Creates and checks out the branch
2. Restores the snapshot
3. Commits the restored state to the new branch

This lets users maintain parallel document versions without merge conflicts.

---

### Git log as version history — the `get_doc_history` tool

Each `_basic` server gains one additional tool when Git integration is active:
`get_doc_history`. This returns the merged history from both sources:

```python
@mcp.tool()
def get_doc_history(file_path: str, max_entries: int = 20) -> dict:
    """Return combined Git + snapshot history for a document."""
```

Return format:

```json
{
  "success": true,
  "file": "contracts/contract_q1.docx",
  "history": [
    {
      "source": "git",
      "timestamp": "2026-03-25T14:30:00Z",
      "message": "[office-mcp] replace_text: replaced 3 placeholders",
      "sha": "a3f9c2b",
      "revertible": true,
      "revert_ref": "a3f9c2b"
    },
    {
      "source": "snapshot",
      "timestamp": "2026-03-25T14:30:00Z",
      "backup_path": ".mcp_versions/contract_q1_2026-03-25T14-30-00Z.bak",
      "revertible": true,
      "revert_ref": "2026-03-25T14-30-00Z"
    }
  ]
}
```

Git entries and snapshot entries are merged and sorted newest-first. Every entry has
a `"revertible": true` flag and a `"revert_ref"` the model can pass to `restore_version`.

---

### Git integration in the progress tracker

Git integration is Phase 10b in the progress tracker (section 29). It is built after
the installer (Phase 10) and is gated on the base servers being complete and tested.

---

### What Git integration does NOT do

- It does not push to remote. All operations are local.
- It does not manage `.gitignore` for `.mcp_versions/`. The installer handles that.
- It does not create the initial Git repository. The user's document folder must
  already be a Git repo. If it is not, Git integration is silently skipped.
- It does not handle merge conflicts. If a file has unstaged changes from another
  process, `git add` will stage all changes. Document this in the README.

---

## 28. Document diff engine

This section specifies how the project computes and presents human-readable diffs
between two versions of a `.docx`, `.xlsx`, or `.pptx` file. This is distinct from
Git's binary file diff — it operates on extracted content, not bytes.

The document diff engine powers three things:
1. The `diff_versions` tool available in each `_basic` server
2. The display shown after `restore_version` ("here is what you reverted")
3. The review step in the contract workflow (before exporting to PDF)

---

### shared/doc_diff.py

```python
# shared/doc_diff.py

def diff_docx(path_a: str, path_b: str) -> dict:
    """
    Compare two .docx files at paragraph level.
    Returns structured diff with added, removed, changed paragraphs.
    """

def diff_xlsx(path_a: str, path_b: str, sheet_name: str | None = None) -> dict:
    """
    Compare two .xlsx files at cell level.
    Returns structured diff with changed cells by sheet.
    If sheet_name provided, only diff that sheet.
    """

def diff_pptx(path_a: str, path_b: str) -> dict:
    """
    Compare two .pptx files at shape-text level.
    Returns structured diff with changed text per slide per shape.
    """

def format_diff_as_text(diff: dict) -> str:
    """
    Format a diff dict as a human-readable unified-diff-style string.
    Suitable for returning in a tool response for the model to narrate.
    """
```

---

### DOCX diff — paragraph-level algorithm

The DOCX diff operates on paragraph text, not raw XML. This avoids XML noise (run
splits, revision marks, internal IDs) that would produce false positives.

**Algorithm:**

```python
def diff_docx(path_a: str, path_b: str) -> dict:
    doc_a = Document(path_a)
    doc_b = Document(path_b)

    # Extract text per paragraph, preserving index
    paras_a = [{"index": i, "text": p.text, "style": p.style.name}
               for i, p in enumerate(doc_a.paragraphs)]
    paras_b = [{"index": i, "text": p.text, "style": p.style.name}
               for i, p in enumerate(doc_b.paragraphs)]

    texts_a = [p["text"] for p in paras_a]
    texts_b = [p["text"] for p in paras_b]

    # Use difflib SequenceMatcher on paragraph text lists
    matcher = difflib.SequenceMatcher(None, texts_a, texts_b)

    changes = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changes.append({
            "type": tag,           # "replace", "insert", "delete"
            "a_range": [i1, i2],
            "b_range": [j1, j2],
            "a_text": texts_a[i1:i2],
            "b_text": texts_b[j1:j2],
        })

    return {
        "success": True,
        "file_a": path_a,
        "file_b": path_b,
        "paragraph_count_a": len(paras_a),
        "paragraph_count_b": len(paras_b),
        "changes": changes,
        "change_count": len(changes),
    }
```

**Key rules:**
- Diff on `.text` (full paragraph text), not on run-level content
- Use `difflib.SequenceMatcher` — same algorithm as Git's patience diff
- Never diff on XML directly — too noisy
- Ignore style changes unless the paragraph text also changed (style-only changes
  are tracked separately in a `"style_changes"` list if needed)
- Empty paragraphs (`""`) are included in the diff — they represent whitespace
  structure and matter for document layout

---

### XLSX diff — cell-level algorithm

```python
def diff_xlsx(path_a: str, path_b: str, sheet_name: str | None = None) -> dict:
    wb_a = openpyxl.load_workbook(path_a, data_only=True)
    wb_b = openpyxl.load_workbook(path_b, data_only=True)

    # Determine sheets to compare
    sheets_a = set(wb_a.sheetnames)
    sheets_b = set(wb_b.sheetnames)

    result = {
        "success": True,
        "added_sheets": list(sheets_b - sheets_a),
        "removed_sheets": list(sheets_a - sheets_b),
        "sheet_diffs": {},
    }

    common = sheets_a & sheets_b
    if sheet_name:
        common = {sheet_name} if sheet_name in common else set()

    for name in common:
        ws_a = wb_a[name]
        ws_b = wb_b[name]
        changed_cells = []

        # Iterate over union of used ranges
        all_cells = set()
        for row in ws_a.iter_rows():
            for cell in row:
                all_cells.add(cell.coordinate)
        for row in ws_b.iter_rows():
            for cell in row:
                all_cells.add(cell.coordinate)

        for coord in all_cells:
            val_a = ws_a[coord].value if coord in ws_a else None
            val_b = ws_b[coord].value if coord in ws_b else None
            if val_a != val_b:
                changed_cells.append({
                    "cell": coord,
                    "old": val_a,
                    "new": val_b,
                })

        if changed_cells:
            result["sheet_diffs"][name] = {
                "changed_cells": changed_cells,
                "change_count": len(changed_cells),
            }

    return result
```

**Key rules:**
- Use `data_only=True` when loading — compares evaluated values, not formula strings
- When you want to diff formulas, use a separate `diff_xlsx_formulas()` call with
  `data_only=False`
- Cap changed cells at 500 per sheet in the return dict — beyond this, truncate with
  `"truncated": true` and `"total_changes": N`
- Sort changed cells by coordinate for stable, readable output

---

### PPTX diff — shape-text-level algorithm

```python
def diff_pptx(path_a: str, path_b: str) -> dict:
    prs_a = Presentation(path_a)
    prs_b = Presentation(path_b)

    slide_count_a = len(prs_a.slides)
    slide_count_b = len(prs_b.slides)

    changes = []
    for i, (slide_a, slide_b) in enumerate(
        zip(prs_a.slides, prs_b.slides)
    ):
        # Map shape name → text for each slide
        shapes_a = {s.name: s.text_frame.text
                    for s in slide_a.shapes if s.has_text_frame}
        shapes_b = {s.name: s.text_frame.text
                    for s in slide_b.shapes if s.has_text_frame}

        all_names = set(shapes_a) | set(shapes_b)
        for name in all_names:
            t_a = shapes_a.get(name, None)
            t_b = shapes_b.get(name, None)
            if t_a != t_b:
                changes.append({
                    "slide_index": i,
                    "shape_name": name,
                    "old_text": t_a,
                    "new_text": t_b,
                })

    return {
        "success": True,
        "slide_count_a": slide_count_a,
        "slide_count_b": slide_count_b,
        "slide_count_changed": slide_count_a != slide_count_b,
        "text_changes": changes,
        "change_count": len(changes),
    }
```

---

### The diff_versions MCP tool

Each `_basic` server exposes one diff tool:

```python
@mcp.tool()
def diff_versions(
    file_path: str,
    timestamp_a: str,
    timestamp_b: str = "current",
) -> dict:
    """Compare two versions of a document. timestamp_b defaults to current file."""
```

When `timestamp_b = "current"`, the diff is between the snapshot at `timestamp_a`
and the current working file. This is the most common use case — "show me what changed
since version X."

When both timestamps are provided, the diff is between two snapshots.

The tool resolves timestamps to backup paths via `shared.version_control.get_history()`
and calls the appropriate `diff_*` function from `shared/doc_diff.py`.

Return includes the full structured diff plus `"summary"` — a 2-3 sentence plain
English description of what changed, suitable for the model to narrate to the user:

```json
{
  "success": true,
  "summary": "3 paragraphs changed, 1 paragraph added. The main changes are in Section 2 where PARTY_A_NAME was replaced with Acme Corporation, and a new termination clause was added after paragraph 14.",
  "changes": [...],
  "change_count": 4
}
```

The `"summary"` is generated by the engine using simple string formatting — not by
calling an LLM. Count changes, find the paragraphs/cells/shapes with the largest
text delta, describe them concisely.

---

### diff_versions and token budget

A full DOCX diff on a 50-paragraph document produces a `"changes"` array that may
contain 5-20 entries, each with `"a_text"` and `"b_text"` strings. This is typically
300-800 tokens — acceptable. However, a diff on a large spreadsheet (500 changed cells)
can produce 5,000+ tokens.

Rules to stay within token budget:
- DOCX: return full paragraph text in diff, no truncation (paragraphs are short)
- XLSX: cap at 500 changed cells, truncate beyond that with `"truncated": true`
- PPTX: return full shape text in diff (shapes are short by nature)
- All formats: `"summary"` is always returned regardless of truncation — the model
  can narrate from the summary even when the full diff is too large

---

### Adding doc_diff to the progress tracker

Doc diff is Phase 1b in the progress tracker — it is built alongside the shared module
(Phase 1) since it lives in `shared/doc_diff.py`. The `diff_versions` tool is added
to each server in its respective phase (Phase 2 for DOCX, Phase 5 for XLSX, Phase 8
for PPTX) as the final tool of that server.

---

## 29. Project build progress tracker

This section tracks the implementation status of the entire project. Update checkboxes
as work is completed. Claude Code should read this section at the start of every session
to understand what is done, what is in progress, and what to build next.

Legend:
- `[ ]` not started
- `[~]` in progress
- `[x]` complete and tested
- `[!]` blocked — see note

---

### Phase 0 — Repository bootstrap

- [ ] Create GitHub repository `office-mcp` with MIT license
- [ ] Add `.gitignore` (Python, uv, `.mcp_versions/`, `__pycache__`, `.pyc`, `.env`)
- [ ] Add `.python-version` pinned to `3.11`
- [ ] Create root `pyproject.toml` with uv workspace config
- [ ] Create `shared/pyproject.toml`
- [ ] Create `shared/__init__.py`
- [ ] Create `servers/` directory with `.gitkeep`
- [ ] Create `tests/` directory with `conftest.py`
- [ ] Create `tests/fixtures/` directory
- [ ] Create `install/` directory
- [ ] Add `README.md` with project description and install instructions stub
- [ ] Add `CLAUDE.md` (this file)
- [ ] Run `uv sync` successfully from repo root
- [ ] Verify `uv run python --version` returns 3.11.x

---

### Phase 1 — Shared module

- [ ] Implement `shared/file_utils.py`
  - [ ] `resolve_path()` — expand `~`, env vars, return absolute `Path`
  - [ ] `resolve_path()` — reject paths inside `.mcp_versions/`
  - [ ] `safe_copy()` — copy with parent dir creation
  - [ ] `read_mcp_json()` — json5 parse, return `{}` if missing
  - [ ] `write_mcp_json()` — atomic write via temp file + rename
- [ ] Implement `shared/version_control.py`
  - [ ] `snapshot()` — copy to `.mcp_versions/{name}_{timestamp}.bak`
  - [ ] `snapshot()` — create `.mcp_versions/` if not exists
  - [ ] `snapshot()` — return backup path as string
  - [ ] `snapshot()` — raise `FileNotFoundError` if source missing
  - [ ] `restore()` — copy `.bak` back over working file
  - [ ] `restore()` — return `False` if backup not found
  - [ ] `get_history()` — return list of dicts, newest first
  - [ ] `get_history()` — each dict has `timestamp`, `backup_path`, `size_bytes`
- [ ] Implement `shared/patch_validator.py`
  - [ ] `validate_ops()` — reject non-list input
  - [ ] `validate_ops()` — reject ops missing `"op"` key
  - [ ] `validate_ops()` — reject op values not in `allowed_ops`
  - [ ] `validate_ops()` — enforce max 50 ops per batch
  - [ ] `validate_ops()` — validate surgical address format (regex check)
  - [ ] `validate_ops()` — return `(True, "")` on valid
  - [ ] `validate_ops()` — return `(False, error_message)` on invalid
- [ ] Implement `shared/address_resolver.py`
  - [ ] `resolve_docx_address()` — parse `§N.pN` / `§N.tN.rN.cN` / `pN` notation
  - [ ] `resolve_docx_address()` — raise `AddressError` if node does not exist
  - [ ] `resolve_xlsx_address()` — parse Excel cell notation and range notation
  - [ ] `resolve_pptx_address()` — parse `slide[N]/shape[name]/pN` notation
  - [ ] `build_docx_index()` — scan headings, build section tree with para_range
  - [ ] `build_docx_index()` — fall back to flat `pN` scheme if no headings found
  - [ ] `build_xlsx_index()` — scan used_range, headers, named_ranges, chart_count
  - [ ] `build_pptx_index()` — scan slides for titles, shape counts, has_table/chart
- [ ] Implement `shared/gitops.py` (section 27)
  - [ ] `is_git_repo()` — checks via `git rev-parse`, returns bool
  - [ ] `stage_file()` — runs `git add`, returns bool, never raises
  - [ ] `commit()` — runs `git commit -m`, returns SHA or None, never raises
  - [ ] `get_log()` — returns list of dicts newest first
  - [ ] `create_branch()` — creates and checks out branch, returns bool
  - [ ] `current_branch()` — returns branch name or `"HEAD"`
  - [ ] `diff_staged()` — returns `git diff --staged` as string
  - [ ] All functions return safe defaults on exception — never propagate
  - [ ] GIT_INTEGRATION=false env var disables all git operations
- [ ] Implement `shared/doc_diff.py` (section 28)
  - [ ] `diff_docx()` — paragraph-level SequenceMatcher diff
  - [ ] `diff_docx()` — ignores style-only changes in main `"changes"` list
  - [ ] `diff_docx()` — empty paragraphs included in diff
  - [ ] `diff_xlsx()` — cell-level diff using data_only=True
  - [ ] `diff_xlsx()` — caps at 500 changed cells, sets `"truncated": true`
  - [ ] `diff_xlsx()` — tracks added/removed sheets
  - [ ] `diff_xlsx()` — optional `sheet_name` filter
  - [ ] `diff_pptx()` — shape-text-level diff per slide
  - [ ] `diff_pptx()` — reports slide count change
  - [ ] `format_diff_as_text()` — unified-diff-style string output
  - [ ] All diff functions include `"summary"` field (rule-based, no LLM)
- [ ] Write `tests/test_shared.py`
  - [ ] Test `snapshot()` creates file in `.mcp_versions/`
  - [ ] Test `restore()` reverts file content correctly
  - [ ] Test `get_history()` returns newest first
  - [ ] Test `validate_ops()` accepts valid op array
  - [ ] Test `validate_ops()` rejects non-list input
  - [ ] Test `validate_ops()` rejects unknown op names
  - [ ] Test `validate_ops()` rejects arrays > 50 ops
  - [ ] Test `read_mcp_json()` handles trailing commas
  - [ ] Test `read_mcp_json()` handles inline comments
  - [ ] Test `write_mcp_json()` is atomic (temp file used)
  - [ ] Test `resolve_path()` rejects `.mcp_versions/` paths
  - [ ] Test `is_git_repo()` returns True inside git repo
  - [ ] Test `is_git_repo()` returns False outside git repo
  - [ ] Test `commit()` returns None when git not available
  - [ ] Test `diff_docx()` detects replaced paragraph
  - [ ] Test `diff_docx()` detects inserted paragraph
  - [ ] Test `diff_docx()` detects deleted paragraph
  - [ ] Test `diff_docx()` returns empty changes for identical files
  - [ ] Test `diff_xlsx()` detects changed cell value
  - [ ] Test `diff_xlsx()` detects added sheet
  - [ ] Test `diff_xlsx()` caps at 500 changed cells
  - [ ] Test `diff_pptx()` detects changed shape text
  - [ ] Test `format_diff_as_text()` produces non-empty string
- [ ] `uv run pytest tests/test_shared.py` — all pass
- [ ] `uv run pyright shared/` — no errors
- [ ] `uv run ruff check shared/` — no errors

---

### Phase 2 — DOCX Basic server

- [ ] Create `servers/docx_basic/` directory structure
  - [ ] `__init__.py`
  - [ ] `engine.py`
  - [ ] `server.py`
  - [ ] `pyproject.toml`
- [ ] Add `docx_basic` to root workspace `pyproject.toml`
- [ ] Add test fixtures
  - [ ] `tests/fixtures/contract_simple.docx` — plain paragraphs, no tables
  - [ ] `tests/fixtures/contract_complex.docx` — multi-run bold/italic, tables, header
- [ ] Implement `engine.py` functions
  - [ ] `get_document_index()` — section tree, zero paragraph content returned
  - [ ] `get_document_index()` — reports `address_scheme`: `"sectioned"` or `"flat"`
  - [ ] `fetch_section()` — returns only paragraphs/tables in addressed section
  - [ ] `fetch_section()` — validates address exists, returns `AddressError` on miss
  - [ ] `replace_at()` — navigate by address, run-level edit, zero surrounding read
  - [ ] `replace_at()` — calls `snapshot()` before write
  - [ ] `replace_at()` — returns `old_text`, `new_text`, `tokens_read: 0`
  - [ ] `insert_at()` — insert paragraph after address, calls `snapshot()`
  - [ ] `delete_at()` — delete paragraph at address, calls `snapshot()`
  - [ ] `read_document()` — legacy full read, warns if paragraph_count > 50
  - [ ] `read_document()` — truncates at 150 paragraphs, sets `"truncated": true`
  - [ ] `read_paragraph()` — returns single paragraph with run details
  - [ ] `replace_text()` — uses `docxedit.replace_string()`, never `.text =`
  - [ ] `replace_text()` — calls `snapshot()` before write
  - [ ] `replace_text()` — includes `"backup"` in return dict
  - [ ] `replace_text()` — reports which paragraphs were changed
  - [ ] `insert_paragraph()` — inserts after paragraph N with style
  - [ ] `insert_paragraph()` — calls `snapshot()` before write
  - [ ] `delete_paragraph()` — by index or match text
  - [ ] `delete_paragraph()` — calls `snapshot()` before write
  - [ ] `append_text()` — adds paragraph at document end
  - [ ] `append_text()` — calls `snapshot()` before write
  - [ ] `get_history()` — delegates to `shared.version_control.get_history()`
  - [ ] `restore_version()` — delegates to `shared.version_control.restore()`
  - [ ] `diff_versions()` — calls `shared.doc_diff.diff_docx()` between two snapshots
  - [ ] `diff_versions()` — `timestamp_b="current"` diffs against working file
  - [ ] `diff_versions()` — returns `"summary"` field always
  - [ ] All functions return `{"success": false, "error": ..., "hint": ...}` on failure
  - [ ] No `print()` statements anywhere in engine.py
- [ ] Implement `server.py`
  - [ ] `mcp = FastMCP("docx-basic")`
  - [ ] `get_document_index` — docstring ≤ 80 chars
  - [ ] `fetch_section` — docstring ≤ 80 chars
  - [ ] `replace_at` — docstring ≤ 80 chars
  - [ ] `insert_at` — docstring ≤ 80 chars
  - [ ] `delete_at` — docstring ≤ 80 chars
  - [ ] `read_document` (legacy, warns on large) — docstring ≤ 80 chars
  - [ ] `get_history`, `restore_version`, `diff_versions` tools
  - [ ] Total tools ≤ 10 — verify count before finishing
  - [ ] All parameters typed
  - [ ] `main()` function calls `mcp.run()`
  - [ ] `project.scripts` entry in `pyproject.toml`
- [ ] Write `tests/test_docx_basic.py`
  - [ ] `test_get_document_index_returns_section_tree`
  - [ ] `test_get_document_index_flat_scheme_on_no_headings`
  - [ ] `test_fetch_section_returns_only_addressed_paragraphs`
  - [ ] `test_fetch_section_invalid_address_error`
  - [ ] `test_replace_at_by_section_address`
  - [ ] `test_replace_at_preserves_run_formatting`
  - [ ] `test_replace_at_tokens_read_is_zero`
  - [ ] `test_replace_at_creates_snapshot`
  - [ ] `test_insert_at_after_address`
  - [ ] `test_delete_at_address`
  - [ ] `test_read_document_warns_on_large_file`
  - [ ] `test_read_document_truncates_at_150`
  - [ ] `test_read_paragraph_returns_run_details`
  - [ ] `test_replace_text_preserves_bold_formatting`
  - [ ] `test_replace_text_preserves_italic_formatting`
  - [ ] `test_replace_text_creates_snapshot`
  - [ ] `test_replace_text_file_not_found`
  - [ ] `test_replace_text_match_not_found`
  - [ ] `test_get_history_returns_newest_first`
  - [ ] `test_restore_version_reverts_content`
  - [ ] `test_diff_versions_detects_replaced_paragraph`
  - [ ] `test_diff_versions_current_vs_snapshot`
  - [ ] `test_diff_versions_returns_summary`
- [ ] `uv run pytest tests/test_docx_basic.py` — all pass
- [ ] `uv run pyright servers/docx_basic/` — no errors
- [ ] `uv run ruff check servers/docx_basic/` — no errors
- [ ] Manual test: register in LM Studio, send "read this document" prompt, verify loop

---

### Phase 3 — DOCX Tables server

- [ ] Create `servers/docx_tables/` directory structure
- [ ] Add to root workspace `pyproject.toml`
- [ ] Add test fixture
  - [ ] `tests/fixtures/report_tables.docx` — multiple tables, merged cells
- [ ] Implement `engine.py` functions
  - [ ] `list_tables()` — count + row/col dimensions per table
  - [ ] `read_table()` — returns 2D JSON array for table N
  - [ ] `read_table()` — handles merged cells (marks as `"merged"`)
  - [ ] `set_cell()` — writes text to table[n] row[r] col[c]
  - [ ] `set_cell()` — calls `snapshot()` before write
  - [ ] `add_row()` — appends row with data array to table N
  - [ ] `add_row()` — calls `snapshot()` before write
  - [ ] `delete_row()` — removes row R from table N
  - [ ] `delete_row()` — calls `snapshot()` before write
  - [ ] `add_table()` — inserts new table at paragraph N
  - [ ] `add_table()` — calls `snapshot()` before write
  - [ ] `delete_table()` — removes table N
  - [ ] `delete_table()` — calls `snapshot()` before write
  - [ ] All out-of-range index errors return actionable hint
- [ ] Implement `server.py` — 7 tools, all docstrings ≤ 80 chars
- [ ] Write `tests/test_docx_tables.py`
  - [ ] `test_list_tables_returns_dimensions`
  - [ ] `test_read_table_returns_2d_array`
  - [ ] `test_read_table_handles_merged_cells`
  - [ ] `test_set_cell_writes_value`
  - [ ] `test_set_cell_creates_snapshot`
  - [ ] `test_set_cell_out_of_range_error`
  - [ ] `test_add_row_appends_data`
  - [ ] `test_delete_row_shifts_up`
  - [ ] `test_add_table_at_position`
  - [ ] `test_delete_table_removes_correctly`
- [ ] All tests pass, pyright clean, ruff clean

---

### Phase 4 — DOCX Layout server

- [ ] Create `servers/docx_layout/` directory structure
- [ ] Add to root workspace `pyproject.toml`
- [ ] Implement `engine.py` functions
  - [ ] `set_heading()` — apply Heading 1-6 style to paragraph N
  - [ ] `set_font()` — set name/size/bold/italic on paragraph or specific run
  - [ ] `set_paragraph_style()` — apply named style from document gallery
  - [ ] `set_paragraph_style()` — return error if style not in document
  - [ ] `add_image()` — insert image file at paragraph N with width setting
  - [ ] `add_image()` — validate image file exists and format is supported
  - [ ] `set_page_margins()` — top/bottom/left/right in cm
  - [ ] `add_header_footer()` — set header or footer text for all pages
  - [ ] `export_pdf()` — detect platform, call docx2pdf or LibreOffice
  - [ ] `export_pdf()` — return clear error if neither Word nor LibreOffice found
  - [ ] All functions call `snapshot()` before write
- [ ] Implement `server.py` — 7 tools, all docstrings ≤ 80 chars
- [ ] Write `tests/test_docx_layout.py`
  - [ ] `test_set_heading_applies_style`
  - [ ] `test_set_font_name_and_size`
  - [ ] `test_set_font_bold_preserves_other_runs`
  - [ ] `test_set_paragraph_style_valid`
  - [ ] `test_set_paragraph_style_invalid_name`
  - [ ] `test_add_image_inserts_at_position`
  - [ ] `test_add_image_invalid_path_error`
  - [ ] `test_set_page_margins`
  - [ ] `test_add_header_text`
  - [ ] `test_add_footer_text`
  - [ ] `test_export_pdf_produces_file` (skip if no Word/LibreOffice)
- [ ] All tests pass, pyright clean, ruff clean

---

### Phase 5 — XLSX Basic server

- [ ] Create `servers/xlsx_basic/` directory structure
- [ ] Add to root workspace `pyproject.toml`
- [ ] Add test fixtures
  - [ ] `tests/fixtures/budget_simple.xlsx` — flat data, no formulas
- [ ] Implement `engine.py` functions
  - [ ] `get_sheet_index()` — used_range, headers, named_ranges, chart_count per sheet
  - [ ] `get_sheet_index()` — zero cell values returned
  - [ ] `fetch_range()` — return 2D value array for addressed range only
  - [ ] `fetch_range()` — validate range format, return error on invalid
  - [ ] `read_sheet()` — legacy full read, warns if row_count > 30
  - [ ] `read_sheet()` — returns companion `.mcp_state.json` if exists
  - [ ] `list_sheets()` — sheet names + row/col dimensions
  - [ ] `read_cell()` — value + formula string + data type for one cell
  - [ ] `set_cell()` — write value to cell by address (e.g. `"B5"`)
  - [ ] `set_cell()` — calls `snapshot()` before write
  - [ ] `set_cell()` — updates `.mcp_state.json` after write
  - [ ] `set_range()` — write 2D array to range
  - [ ] `set_range()` — calls `snapshot()` before write
  - [ ] `insert_row()` — insert at row N, shift down
  - [ ] `insert_row()` — calls `snapshot()` before write
  - [ ] `delete_row()` — remove row N, shift up
  - [ ] `delete_row()` — calls `snapshot()` before write
  - [ ] `add_sheet()` — create new sheet, optional name
  - [ ] `delete_sheet()` — remove by name, error if not found
  - [ ] `diff_versions()` — calls `shared.doc_diff.diff_xlsx()` between two snapshots
  - [ ] `diff_versions()` — `timestamp_b="current"` diffs against working file
  - [ ] `diff_versions()` — returns `"summary"` and respects 500-cell cap
  - [ ] All functions use Excel address notation (`"B5"` not row/col ints)
  - [ ] Cell address validated in `patch_validator`
- [ ] Implement `server.py` — 10 tools (9 original + `diff_versions`), all docstrings ≤ 80 chars
- [ ] Write `tests/test_xlsx_basic.py`
  - [ ] `test_get_sheet_index_returns_used_range`
  - [ ] `test_get_sheet_index_returns_headers`
  - [ ] `test_get_sheet_index_zero_cell_values`
  - [ ] `test_fetch_range_returns_addressed_cells_only`
  - [ ] `test_fetch_range_invalid_notation_error`
  - [ ] `test_read_sheet_warns_on_large_sheet`
  - [ ] `test_read_sheet_returns_2d_array`
  - [ ] `test_read_sheet_returns_correct_types`
  - [ ] `test_list_sheets_returns_names_and_dimensions`
  - [ ] `test_read_cell_value_and_type`
  - [ ] `test_set_cell_writes_value`
  - [ ] `test_set_cell_creates_snapshot`
  - [ ] `test_set_cell_updates_state_json`
  - [ ] `test_set_cell_invalid_address_error`
  - [ ] `test_set_range_writes_2d_array`
  - [ ] `test_insert_row_shifts_down`
  - [ ] `test_delete_row_shifts_up`
  - [ ] `test_add_sheet_creates_new`
  - [ ] `test_delete_sheet_removes`
  - [ ] `test_delete_sheet_not_found_error`
  - [ ] `test_diff_versions_detects_changed_cell`
  - [ ] `test_diff_versions_returns_summary`
- [ ] All tests pass, pyright clean, ruff clean
- [ ] Manual test: LM Studio end-to-end — "set cell B5 to 142500"

---

### Phase 6 — XLSX Formulas server

- [ ] Create `servers/xlsx_formulas/` directory structure
- [ ] Add to root workspace `pyproject.toml`
- [ ] Add test fixture
  - [ ] `tests/fixtures/budget_formulas.xlsx` — SUM, IF, VLOOKUP formulas
- [ ] Implement `engine.py` functions
  - [ ] `set_formula()` — write formula string starting with `=`
  - [ ] `set_formula()` — validate leading `=` in patch_validator
  - [ ] `set_formula()` — calls `snapshot()` before write
  - [ ] `set_named_range()` — define named range for formula use
  - [ ] `set_conditional_format()` — color rule: greater/less/between/equal
  - [ ] `set_conditional_format()` — supports colors: `"green"`, `"red"`, `"yellow"`, `"blue"`
  - [ ] `set_data_validation()` — dropdown list from values array
  - [ ] `set_data_validation()` — number constraint (min, max)
  - [ ] `freeze_panes()` — freeze rows and/or columns
  - [ ] `set_autofilter()` — enable filter on header row range
  - [ ] All functions call `snapshot()` before write
- [ ] Implement `server.py` — 6 tools, all docstrings ≤ 80 chars
- [ ] Write `tests/test_xlsx_formulas.py`
  - [ ] `test_set_formula_writes_formula_string`
  - [ ] `test_set_formula_rejects_missing_equals`
  - [ ] `test_set_formula_creates_snapshot`
  - [ ] `test_set_named_range_creates_range`
  - [ ] `test_set_conditional_format_greater_than`
  - [ ] `test_set_conditional_format_between`
  - [ ] `test_set_data_validation_dropdown`
  - [ ] `test_set_data_validation_number_constraint`
  - [ ] `test_freeze_panes_rows_only`
  - [ ] `test_freeze_panes_rows_and_cols`
  - [ ] `test_set_autofilter_adds_filter`
- [ ] All tests pass, pyright clean, ruff clean

---

### Phase 7 — XLSX Charts server

- [ ] Create `servers/xlsx_charts/` directory structure
- [ ] Add to root workspace `pyproject.toml`
- [ ] Add test fixture
  - [ ] `tests/fixtures/dashboard.xlsx` — existing charts, conditional formatting
- [ ] Implement `engine.py` functions
  - [ ] `add_chart()` — bar/line/pie/area/scatter from data range
  - [ ] `add_chart()` — uses openpyxl chart objects (not xlsxwriter)
  - [ ] `add_chart()` — anchor_cell positions chart top-left
  - [ ] `add_chart()` — width and height in cm
  - [ ] `add_chart()` — calls `snapshot()` before write
  - [ ] `update_chart()` — delete-then-add pattern internally
  - [ ] `update_chart()` — calls `snapshot()` before write
  - [ ] `delete_chart()` — remove by name or index
  - [ ] `delete_chart()` — calls `snapshot()` before write
  - [ ] `add_pivot_table()` — create pivot from range, rows/cols/values params
  - [ ] `add_pivot_table()` — calls `snapshot()` before write
  - [ ] `set_cell_style()` — font, fill color (hex), border, number format
  - [ ] `set_cell_style()` — calls `snapshot()` before write
  - [ ] Unsupported chart type returns error dict, never silent fallback
- [ ] Implement `server.py` — 5 tools, all docstrings ≤ 80 chars
- [ ] Write `tests/test_xlsx_charts.py`
  - [ ] `test_add_chart_bar`
  - [ ] `test_add_chart_line`
  - [ ] `test_add_chart_pie`
  - [ ] `test_add_chart_unsupported_type_error`
  - [ ] `test_add_chart_creates_snapshot`
  - [ ] `test_update_chart_changes_title`
  - [ ] `test_delete_chart_removes`
  - [ ] `test_add_pivot_table`
  - [ ] `test_set_cell_style_font`
  - [ ] `test_set_cell_style_fill_color`
- [ ] All tests pass, pyright clean, ruff clean

---

### Phase 8 — PPTX Basic server

- [ ] Create `servers/pptx_basic/` directory structure
- [ ] Add to root workspace `pyproject.toml`
- [ ] Add test fixtures
  - [ ] `tests/fixtures/deck_simple.pptx` — title + content slides
  - [ ] `tests/fixtures/deck_images.pptx` — slides with embedded images
- [ ] Implement `engine.py` functions
  - [ ] `get_presentation_index()` — slide count, titles, shape_count, has_table/chart per slide
  - [ ] `get_presentation_index()` — returns available_layouts list
  - [ ] `get_presentation_index()` — zero shape text content returned
  - [ ] `fetch_slide()` — returns all shapes with text for one slide only
  - [ ] `fetch_shape()` — returns paragraph text for one shape only
  - [ ] `set_text_at()` — write to `slide[N]/shape[name]/pN` address, run-level
  - [ ] `set_text_at()` — calls `snapshot()` before write
  - [ ] `set_text_at()` — returns `old_text` and `new_text` in response
  - [ ] `read_presentation()` — legacy full index, still useful for small decks
  - [ ] `read_slide()` — all shapes with name, type, text content
  - [ ] `read_slide()` — returns shape index alongside name
  - [ ] `set_text()` — replace text in shape by slide index + shape name
  - [ ] `set_text()` — uses run-level editing, never `shape.text_frame.text =`
  - [ ] `set_text()` — calls `snapshot()` before write
  - [ ] `add_slide()` — append with layout name + title + body text
  - [ ] `add_slide()` — validate layout name against available layouts
  - [ ] `add_slide()` — calls `snapshot()` before write
  - [ ] `delete_slide()` — remove by index
  - [ ] `delete_slide()` — calls `snapshot()` before write
  - [ ] `reorder_slide()` — move from index A to index B
  - [ ] `reorder_slide()` — calls `snapshot()` before write
  - [ ] `add_text_box()` — text box at x/y (inches) with width on slide N
  - [ ] `add_text_box()` — calls `snapshot()` before write
  - [ ] `add_image()` — insert image at x/y/width/height on slide N
  - [ ] `add_image()` — validate file exists + supported format
  - [ ] `add_image()` — calls `snapshot()` before write
  - [ ] `diff_versions()` — calls `shared.doc_diff.diff_pptx()` between two snapshots
  - [ ] `diff_versions()` — `timestamp_b="current"` diffs against working file
  - [ ] `diff_versions()` — returns `"summary"` field always
- [ ] Implement `server.py` — 9 tools (8 original + `diff_versions`), all docstrings ≤ 80 chars
- [ ] Write `tests/test_pptx_basic.py`
  - [ ] `test_read_presentation_returns_slide_count`
  - [ ] `test_read_presentation_returns_layouts`
  - [ ] `test_read_slide_returns_shapes`
  - [ ] `test_read_slide_returns_shape_names`
  - [ ] `test_set_text_replaces_title`
  - [ ] `test_set_text_preserves_formatting`
  - [ ] `test_set_text_creates_snapshot`
  - [ ] `test_set_text_shape_not_found_error`
  - [ ] `test_add_slide_with_layout`
  - [ ] `test_add_slide_invalid_layout_error`
  - [ ] `test_delete_slide_removes`
  - [ ] `test_reorder_slide_moves_correctly`
  - [ ] `test_add_text_box_at_position`
  - [ ] `test_add_image_inserts`
  - [ ] `test_add_image_invalid_path_error`
  - [ ] `test_diff_versions_detects_changed_shape_text`
  - [ ] `test_diff_versions_returns_summary`
- [ ] All tests pass, pyright clean, ruff clean
- [ ] Manual test: LM Studio end-to-end — "add a slide with title Q3 Results"

---

### Phase 9 — PPTX Design server

- [ ] Create `servers/pptx_design/` directory structure
- [ ] Add to root workspace `pyproject.toml`
- [ ] Implement `engine.py` functions
  - [ ] `set_background()` — solid hex color or image file
  - [ ] `set_background()` — calls `snapshot()` before write
  - [ ] `set_font_style()` — font name/size/bold/color (hex) on shape
  - [ ] `set_font_style()` — calls `snapshot()` before write
  - [ ] `add_table()` — insert table with rows/cols + data on slide
  - [ ] `add_table()` — calls `snapshot()` before write
  - [ ] `add_chart()` — bar/line/pie from data dict on slide
  - [ ] `add_chart()` — calls `snapshot()` before write
  - [ ] `duplicate_slide()` — copy slide N to position M
  - [ ] `duplicate_slide()` — calls `snapshot()` before write
  - [ ] `export_pdf()` — detect platform, error if unavailable
- [ ] Implement `server.py` — 6 tools, all docstrings ≤ 80 chars
- [ ] Write `tests/test_pptx_design.py`
  - [ ] `test_set_background_solid_color`
  - [ ] `test_set_background_image`
  - [ ] `test_set_font_style_name_size`
  - [ ] `test_set_font_style_bold`
  - [ ] `test_add_table_on_slide`
  - [ ] `test_add_chart_bar`
  - [ ] `test_duplicate_slide_creates_copy`
  - [ ] `test_export_pdf_produces_file` (skip if unavailable)
- [ ] All tests pass, pyright clean, ruff clean

---

### Phase 10 — Installer and distribution

- [ ] Create `install/mcp_config_writer.py`
  - [ ] Detect LM Studio mcp.json path by OS (macOS / Windows / Linux)
  - [ ] Read existing config via `shared.file_utils.read_mcp_json()`
  - [ ] Accept `--servers` CLI arg (comma-separated server names)
  - [ ] Skip server if already registered (idempotent)
  - [ ] Generate correct `uv run --directory` mcp.json entry per server
  - [ ] Write updated config via `shared.file_utils.write_mcp_json()`
  - [ ] Print confirmation of each server registered
  - [ ] Print "Restart LM Studio" reminder
- [ ] Create `install/install.sh`
  - [ ] Check Python ≥ 3.11, print install URL and exit 1 if not found
  - [ ] Check `uv` on PATH, install via curl if missing
  - [ ] Run `uv sync` from repo root
  - [ ] Show numbered menu of available servers
  - [ ] Accept user selection (individual numbers or `all`)
  - [ ] Run `mcp_config_writer.py` with selection
  - [ ] Idempotent — safe to run twice
  - [ ] Test on macOS
  - [ ] Test on Ubuntu 22.04
- [ ] Create `install/install.bat`
  - [ ] Check Python via `py --version` then `python --version`
  - [ ] Install `uv` via PowerShell if missing
  - [ ] Same menu + mcp_config_writer flow as install.sh
  - [ ] Test on Windows 10
  - [ ] Test on Windows 11
- [ ] Write `tests/test_mcp_config_writer.py`
  - [ ] `test_adds_server_entry_to_empty_config`
  - [ ] `test_skips_already_registered_server`
  - [ ] `test_handles_trailing_comma_in_existing_config`
  - [ ] `test_handles_comment_in_existing_config`
  - [ ] `test_does_not_remove_existing_entries`
  - [ ] `test_writes_atomically` (checks temp file renamed)
- [ ] All tests pass

---

### Phase 10b — Git integration for document edits (optional)

Built after Phase 10 (installer). Requires base servers complete and tested.
Can be skipped if git integration is not needed for initial release.

- [ ] `shared/gitops.py` is complete (checked off in Phase 1)
- [ ] Add `git_integration` flag to `shared/version_control.py`
  - [ ] `snapshot()` accepts optional `commit: bool = False` param
  - [ ] When `commit=True` and file is in a git repo, stages and commits after snapshot
  - [ ] Commit message follows `[office-mcp] {op}: {summary}` format from section 27
  - [ ] Git failure does not affect return value of `snapshot()`
- [ ] Add `git_committed` and `git_sha` fields to write tool return dicts
  - [ ] `"git_committed": true` when commit succeeded
  - [ ] `"git_committed": false` when git unavailable or not in repo
  - [ ] `"git_sha": "a3f9c2b"` when committed, omitted otherwise
- [ ] Add `get_doc_history` tool to each `_basic` server
  - [ ] Returns merged Git + snapshot history, newest first
  - [ ] Each entry has `"source"`, `"timestamp"`, `"revertible"`, `"revert_ref"`
  - [ ] Git entries include `"sha"` and `"message"`
  - [ ] Snapshot entries include `"backup_path"`
- [ ] `restore_version` in each `_basic` server gains `create_branch` parameter
  - [ ] When provided, creates branch and commits restored state
  - [ ] Branch creation failure returns error dict, does not affect file restore
- [ ] Add `GIT_INTEGRATION` env var check to installer
  - [ ] installer.sh prompts user: "Enable Git integration? (y/n)"
  - [ ] Sets `GIT_INTEGRATION=true` in the mcp.json `env` block if yes
- [ ] Write `tests/test_gitops.py`
  - [ ] `test_is_git_repo_true_inside_repo`
  - [ ] `test_is_git_repo_false_outside_repo`
  - [ ] `test_commit_returns_sha`
  - [ ] `test_commit_returns_none_when_git_missing`
  - [ ] `test_snapshot_with_commit_creates_git_commit`
  - [ ] `test_snapshot_git_failure_does_not_break_snapshot`
  - [ ] `test_get_doc_history_merges_sources`
  - [ ] `test_restore_with_create_branch`
- [ ] All tests pass

---

### Phase 11 — CI/CD pipeline

- [ ] Create `.github/workflows/ci.yml`
  - [ ] Trigger on: push to `main`, pull_request to `main`
  - [ ] Steps: `uv sync --frozen`, `ruff check .`, `ruff format --check .`
  - [ ] Steps: `pyright servers/ shared/`
  - [ ] Steps: `pytest tests/ --cov=servers --cov=shared --cov-fail-under=90`
  - [ ] Step: docstring length check (≤ 80 chars per tool)
  - [ ] Step: str_replace compliance check — flag any full-file writes to existing files
  - [ ] Matrix: Ubuntu 22.04, Windows latest, macOS latest
- [ ] Create `.github/workflows/release.yml`
  - [ ] Trigger on: tag push `v*`
  - [ ] Build release archives for Linux, Windows, macOS
  - [ ] Upload as GitHub Release assets
- [ ] CI passes on all 3 platforms

---

### Phase 12 — Documentation and README

- [ ] `README.md` — project description and goals
- [ ] `README.md` — prerequisites (Python 3.11, uv)
- [ ] `README.md` — quick install section (clone + install.sh / install.bat)
- [ ] `README.md` — LM Studio setup with screenshots
- [ ] `README.md` — recommended server combinations table
- [ ] `README.md` — example prompts for each server tier
- [ ] `README.md` — contributing guide
- [ ] `README.md` — license section (MIT)
- [ ] Each server directory has inline mcp.json snippet in its docstring
- [ ] `CLAUDE.md` progress tracker updated to reflect final state

---

### Phase 13 — End-to-end validation

These are manual acceptance tests. Each must be performed in LM Studio 0.4.x with
Qwen 3.5 9B before the release tag is created.

#### DOCX end-to-end tests

- [ ] Load `docx_basic` only. Ask: "Read contract_complex.docx and tell me how many
      paragraphs it has." — model calls `read_document`, returns count correctly.
- [ ] Ask: "Replace PARTY_A_NAME with Acme Corporation in the contract." — model calls
      `replace_text`, formatting preserved, snapshot created.
- [ ] Ask: "Undo the last change." — model calls `restore_version`, file reverted.
- [ ] Load `docx_basic` + `docx_tables`. Ask: "Add a row to the first table with values
      Item D, 500, 3." — model calls `add_row`, table updated correctly.
- [ ] Load `docx_layout` only. Ask: "Make the first paragraph a Heading 1." — model
      calls `set_heading`, style applied.

#### XLSX end-to-end tests

- [ ] Load `xlsx_basic` only. Ask: "Set cell B5 in the Q3 sheet to 142500." — model
      calls `set_cell`, value written correctly.
- [ ] Load `xlsx_basic` + `xlsx_formulas`. Ask: "Add a SUM formula in D10 that totals
      D2 through D9." — model calls `set_formula` with `=SUM(D2:D9)`.
- [ ] Ask: "Highlight cells B2 to B20 in green where the value is over 100000." —
      model calls `set_conditional_format` correctly.
- [ ] Load `xlsx_charts` only. Ask: "Create a bar chart from the data in A1:D10 on the
      Q3 sheet." — model calls `add_chart`, chart appears in workbook.

#### PPTX end-to-end tests

- [ ] Load `pptx_basic` only. Ask: "Read deck_simple.pptx and list all the slide
      titles." — model calls `read_presentation`, returns titles.
- [ ] Ask: "Add a new slide at the end with title Q4 Forecast and the body text
      Revenue target: $2M." — model calls `add_slide`, slide appears.
- [ ] Ask: "Move slide 3 to position 1." — model calls `reorder_slide`.

#### Contract workflow test (full pipeline)

- [ ] Start with `contract_complex.docx` (has placeholder text like PARTY_A_NAME,
      PARTY_B_NAME, EFFECTIVE_DATE, CONTRACT_VALUE).
- [ ] Load `docx_basic` + `docx_tables`.
- [ ] Send one prompt: "Fill in this contract: Party A is Acme Corp, Party B is Widget
      Ltd, effective date is April 1 2026, contract value is $50,000 USD."
- [ ] Model should call `replace_text` 4 times in sequence using the agentic loop.
- [ ] Verify all 4 replacements applied, all formatting preserved.
- [ ] Verify 4 snapshots created in `.mcp_versions/`.
- [ ] Ask: "Export to PDF." — model calls `export_pdf`, PDF file created.

---

### Overall completion summary

Update this table as phases complete.

| Phase | Description | Status | Notes |
|---|---|---|---|
| 0 | Repository bootstrap | `[ ]` | |
| 1 | Shared module (file_utils, version_control, patch_validator, gitops, doc_diff) | `[ ]` | |
| 2 | DOCX Basic (8 tools + diff_versions) | `[ ]` | |
| 3 | DOCX Tables | `[ ]` | |
| 4 | DOCX Layout | `[ ]` | |
| 5 | XLSX Basic (9 tools + diff_versions) | `[ ]` | |
| 6 | XLSX Formulas | `[ ]` | |
| 7 | XLSX Charts | `[ ]` | |
| 8 | PPTX Basic (8 tools + diff_versions) | `[ ]` | |
| 9 | PPTX Design | `[ ]` | |
| 10 | Installer and distribution | `[ ]` | |
| 10b | Git integration for document edits | `[ ]` | Optional — skip for v0.1 |
| 11 | CI/CD pipeline | `[ ]` | |
| 12 | Documentation and README | `[ ]` | |
| 13 | End-to-end validation | `[ ]` | |

**Current focus:** Phase 0 — start here.

---

### Source code edit protocol compliance tracker

Track whether Claude Code is following the str_replace rules from section 26.
Update after each coding session.

| Session | Files edited | str_replace used | Full rewrites | Notes |
|---|---|---|---|---|
| — | — | — | — | Not started |

**Rule:** full rewrites must be 0 for all sessions after Phase 0 bootstrap.
If a full rewrite was necessary, add a note explaining why the str_replace
protocol could not apply.

---

*Last updated: 2026-03-25*
*Covers: office-mcp v0.1.x architecture*
*For questions about this file, open a GitHub Discussion — do not edit CLAUDE.md
without reviewing the full architecture context in this file first.*
