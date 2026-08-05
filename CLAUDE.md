# CLAUDE.md — office-mcp

> Standards reference: https://github.com/azzindani/Standards/blob/main/local_mcp/STANDARDS.md
> When this file conflicts with the general STANDARDS.md, this file takes precedence.

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
8. [Tool inventory](#8-tool-inventory)
9. [Patch protocol — the JSON op format](#9-patch-protocol--the-json-op-format)
10. [Surgical addressing protocol](#10-surgical-addressing-protocol)
11. [DOCX engine rules](#11-docx-engine-rules)
12. [XLSX engine rules](#12-xlsx-engine-rules)
13. [PPTX engine rules](#13-pptx-engine-rules)
14. [Error handling contract](#14-error-handling-contract)
15. [Testing rules](#15-testing-rules)
16. [MCP tool schema rules](#16-mcp-tool-schema-rules)
17. [Local model constraints](#17-local-model-constraints)
18. [Naming conventions](#18-naming-conventions)
19. [What Claude must never do](#19-what-claude-must-never-do)
20. [Adding a new tool — checklist](#20-adding-a-new-tool--checklist)
21. [Common failure modes](#21-common-failure-modes)
22. [Dependency policy](#22-dependency-policy)
23. [Git and PR rules](#23-git-and-pr-rules)
24. [Source code editing protocol](#24-source-code-editing-protocol)
25. [Cross-platform compatibility](#25-cross-platform-compatibility)
26. [Progress output system](#26-progress-output-system)
27. [File path handling](#27-file-path-handling)
28. [Operation receipt log](#28-operation-receipt-log)

---

## 1. Project overview

`office-mcp` is an open-source monorepo of MCP (Model Context Protocol) servers that
give local LLMs full programmatic control over Microsoft Office file formats — Word
(.docx), Excel (.xlsx), and PowerPoint (.pptx).

The primary target runtime is LM Studio 0.4.x running any model that supports tool
calling (Gemma 4, Qwen 3.5, etc.). The design is deliberately constrained to work
within the tool-count and context-length limits of local models. Servers are split by
tier so the user loads only the tools their task requires.

### Goals

- Every tool executes a deterministic, structured operation. No AI inference happens
  inside the tool itself.
- Documents are never fully rewritten. Every edit is a targeted patch at the paragraph,
  run, cell, or shape level.
- Files on disk are safe. Every write operation is preceded by a version snapshot.
  Rollback is always possible.
- Zero cloud dependency. All servers run locally. No API keys required.
- Non-developer installable. A user who can paste JSON into LM Studio should be able
  to get this running.

### Non-goals

- This is not a general-purpose document library. Tools are intentionally narrow and
  opinionated for LLM consumption.
- This project does not render documents visually or provide a document viewer UI.
- This project does not integrate with cloud storage in the core servers.

---

## 2. Repository layout

```
MCP_Microsoft_Office/
│
├── shared/                         # imported by ALL servers — never duplicate this
│   ├── __init__.py
│   ├── address_resolver.py         # §N.pM / A1:B5 / slide[N]/shape[name] parsing
│   ├── doc_diff.py                 # paragraph/cell/shape-level diff engine
│   ├── file_utils.py               # path resolution, atomic writes, JSON helpers
│   ├── gitops.py                   # optional auto-commit on every write
│   ├── live_edit.py                # auto-reload in Word/Excel/LibreOffice after save
│   ├── patch_validator.py          # validate op arrays before apply
│   ├── platform_utils.py           # constrained mode, limits, open_file()
│   ├── progress.py                 # ok/fail/info/warn step helpers
│   ├── receipt.py                  # per-file operation audit log
│   └── version_control.py          # snapshot, restore, get_history
│
├── servers/
│   ├── docx_basic/                 # 15 tools — read, search, edit, history, diff
│   │   ├── __init__.py
│   │   ├── server.py               # FastMCP setup + tool definitions (thin)
│   │   ├── engine.py               # pure python-docx logic (no MCP imports)
│   │   ├── helpers.py              # internal helpers for engine.py
│   │   └── pyproject.toml
│   │
│   ├── docx_tables/                # 9 tools — table CRUD
│   ├── docx_layout/                # 7 tools — styles, fonts, margins, PDF export
│   ├── docx_new/                   # 7 tools — create, template, batch, merge
│   ├── xlsx_basic/                 # 14 tools — read, cell CRUD, sheets, sort, dedup
│   │   └── helpers.py              # (has helpers.py alongside engine.py)
│   ├── xlsx_formulas/              # 9 tools — formulas, fill-down, auto-sum
│   ├── xlsx_charts/                # 5 tools — charts, pivot tables, cell styles
│   ├── xlsx_new/                   # 6 tools — create, CSV import, invoice
│   ├── pptx_basic/                 # 10 tools — read, edit, slides, diff
│   ├── pptx_design/                # 8 tools — background, fonts, global changes
│   └── pptx_new/                   # 6 tools — create, agenda, doc→deck
│
├── tests/
│   ├── fixtures/                   # real .docx .xlsx .pptx files for testing
│   ├── conftest.py
│   └── test_*.py                   # one test file per server
│
├── install/
│   ├── install.sh                  # Linux / macOS interactive installer
│   ├── install.bat                 # Windows interactive installer
│   └── mcp_config_writer.py        # writes LM Studio / Claude Desktop / Cursor config
│
├── pyproject.toml                  # root workspace — uv workspaces config
├── uv.lock
├── .python-version                 # 3.12
└── CLAUDE.md                       # this file
```

Every server directory has `__init__.py`, `server.py`, `engine.py`, `pyproject.toml`.
`docx_basic` and `xlsx_basic` also have `helpers.py` for internal engine helpers.
Do not create subdirectories inside a server.

---

## 3. Architecture principles

### P1 — engine.py has zero MCP imports

`engine.py` is pure Python. It imports `python-docx`, `openpyxl`, `python-pptx`, and
`shared/`. It never imports `mcp`, `fastmcp`, or anything from the MCP protocol layer.
This makes the engine directly testable with pytest without spinning up a server.

### P2 — server.py is a thin wrapper only

`server.py` does three things: initialises the `FastMCP` instance, defines tool
functions with `@mcp.tool()` decorators, and calls into `engine.py`. Tool functions
in `server.py` must not contain business logic.

### P3 — tools never rewrite entire files

Every write operation targets a specific node: a paragraph by index, a cell by
address, a shape by name, a slide by index. If an operation requires reading the whole
document first, that is two separate tool calls — one `read_*` and one targeted write.

### P4 — snapshot before every write

Every tool that modifies a file calls `shared.version_control.snapshot(path)` before
applying any change. If a tool skips the snapshot, it is a bug.

### P5 — return structured JSON, never prose

Every tool returns a Python dict that becomes JSON. Never return a plain string.
Return `{"success": true, "op": "replace_text", "paragraph_index": 4, "new_text": "..."}`.

### P6 — fail loudly with actionable messages

When a tool fails: `{"success": false, "error": "<specific reason>", "hint": "<what to try instead>"}`.
Never swallow exceptions silently.

### P7 — shared/ is read-only from server perspective

Servers import from `shared/` but never modify it. Fix bugs in `shared/` directly —
do not work around them by duplicating logic in `engine.py`.

### P8 — tool descriptions must be ≤ 80 characters

Tool descriptions consume context on every turn. Every `@mcp.tool()` description must
be 80 characters or fewer. This is a CI check.

### P9 — tool parameter names are lowercase snake_case nouns

`file_path`, `paragraph_index`, `sheet_name`, `cell_address`. Never verb-first names
like `get_file_path` or camelCase like `filePath`.

### P10 — no optional parameters with complex defaults

If a parameter is optional, its default must be `None` or a primitive scalar.
Never use a mutable default like `[]` or `{}`.

---

## 4. Technology stack

| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.12+ | Document libraries live here |
| MCP framework | FastMCP ≥ 1.2.0 | Official SDK, decorator-based tools |
| Package manager | uv | Workspace support, fast, single lockfile |
| DOCX manipulation | python-docx ≥ 1.1.0 | Mature, MIT, run-level access |
| DOCX run-safe edit | docxedit ≥ 1.2.0 | Preserves formatting on replace |
| XLSX read+write | openpyxl ≥ 3.1.0 | Read+write on existing files |
| XLSX create+charts | xlsxwriter ≥ 3.2.0 | Write-only, best chart support |
| PPTX | python-pptx ≥ 0.6.23 | Only mature open-source pptx lib |
| PDF generate | reportlab ≥ 4.2.0 | Only for net-new PDF creation |
| Testing | pytest ≥ 8.0 | Standard |
| Type checking | pyright (strict) | Enforced in CI |
| Linting | ruff | Fast, replaces flake8+isort+black |

---

## 5. Monorepo and workspace setup

The root `pyproject.toml` declares a uv workspace with all 11 servers plus `shared`.

```bash
# Install everything (run once after clone)
uv sync --all-packages

# Run a specific server (for development)
uv run --directory servers/docx_basic docx-basic

# Run all tests
uv run pytest tests/

# Type check one server
uv run pyright servers/docx_basic/

# Lint everything
uv run ruff check .

# Format everything
uv run ruff format .
```

---

## 6. Shared module — shared/

### version_control.py

```python
def snapshot(file_path: str) -> str:
    """Copy to .mcp_versions/{filename}_{iso_timestamp}.bak. Returns backup path."""

def restore(file_path: str, timestamp: str) -> bool:
    """Copy backup back over working file. Returns True on success."""

def get_history(file_path: str) -> list[dict]:
    """Return snapshots newest first. Each dict: {timestamp, backup_path, size_bytes}"""
```

Snapshots live in `.mcp_versions/` in the same folder as the file. Created automatically.
`.mcp_versions/` is in `.gitignore`.

### patch_validator.py

```python
def validate_ops(ops: list[dict], allowed_ops: list[str]) -> tuple[bool, str]:
    """Validate patch op array. Returns (True, "") or (False, error_message)."""
```

Called by every engine function that accepts a patch array. Maximum 50 ops per batch.

### file_utils.py

Exports `resolve_path()`, `safe_copy()`, `read_mcp_json()`, `write_mcp_json()`.
`resolve_path()` expands `~`, env vars, resolves to absolute path, and rejects paths
inside `.mcp_versions/`.

### platform_utils.py

```python
def is_8gb_mode() -> bool: ...       # reads OFFICE_MCP_8GB_MODE env var
def get_max_paragraphs() -> int: ... # 50 normal, 20 constrained
def get_max_cells() -> int: ...      # 200 normal, 100 constrained
def get_max_search_results() -> int: # 50 normal, 10 constrained
```

Every engine function that returns bounded content calls these helpers.
Never hardcode limits directly in engine logic.

### progress.py

```python
def ok(msg: str, detail: str = "") -> dict: ...
def fail(msg: str, detail: str = "") -> dict: ...
def info(msg: str, detail: str = "") -> dict: ...
def warn(msg: str, detail: str = "") -> dict: ...
```

Every tool response includes a `"progress"` array built with these helpers.

### receipt.py

`append_receipt()` — called after every write operation (success or failure) to
maintain the `.mcp_receipt.json` audit log alongside the document.

### address_resolver.py

Parses and resolves surgical address strings:
- DOCX: `§N`, `§N.pM`, `§N.tM.rR.cC`, `pN`
- XLSX: Excel cell notation `A1`, `B5:D10`
- PPTX: `slide[N]/shape[name]/pM`

### doc_diff.py

`diff_docx()`, `diff_xlsx()`, `diff_pptx()` — paragraph/cell/shape-level diff between
two file versions. Used by `diff_versions` tools in each `_basic` server.

### gitops.py

Optional auto-commit after every write. Activated when the file is inside a Git repo
and `GIT_INTEGRATION` env var is not `false`. All functions are non-raising —
Git failures never abort document edits.

### live_edit.py

`notify_reload()` — attempts to trigger auto-reload in the native app (Word/Excel on
macOS via AppleScript, LibreOffice on Linux via lock-file detection). Falls back to
an informational progress step on Windows.

---

## 7. Server structure — every server follows the same pattern

### server.py template

```python
from mcp.server.fastmcp import FastMCP
from . import engine

mcp = FastMCP("docx-basic")


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

Rules:
- One `@mcp.tool()` per exported tool. No helper functions in this file.
- Tool function body is always a single `return engine.function_name(...)` call.
- Type annotations on all parameters. Return type is always `dict`.
- Docstring ≤ 80 chars.
- `main()` function required for the `project.scripts` entry point.

### engine.py template

```python
from pathlib import Path
from docx import Document
from shared.version_control import snapshot
from shared.patch_validator import validate_ops
from shared.file_utils import resolve_path
from shared.progress import ok, fail, info
from shared.receipt import append_receipt


def replace_text(file_path: str, match_text: str, new_text: str, ...) -> dict:
    progress = []
    backup = None
    try:
        path = resolve_path(file_path)
        # ... do work ...
        backup = snapshot(str(path))
        progress.append(ok("Snapshot saved", Path(backup).name))
        # ... apply change ...
        progress.append(ok(f"Replaced '{match_text}'", f"{n} occurrences"))
        append_receipt(str(path), "replace_text", "docx_basic", {...}, "✔ ...", backup, True)
        return {
            "success": True,
            "op": "replace_text",
            "backup": backup,
            "progress": progress,
            "token_estimate": len(str(progress)) // 4,
        }
    except Exception as e:
        progress.append(fail(str(e)))
        append_receipt(str(path) if path else file_path, "replace_text", "docx_basic", {...}, "✘ ...", backup, False)
        return {
            "success": False,
            "error": str(e),
            "hint": "Use restore_version to undo if a snapshot was taken.",
            "backup": backup,
            "progress": progress,
            "token_estimate": len(str(progress)) // 4,
        }
```

Rules:
- Every function returns a dict with `"success"` as first key.
- Every response includes `"progress"` array and `"token_estimate"`.
- Snapshot before every write. Include `"backup"` path in return dict.
- Never raise exceptions to the caller. Catch and return error dict.
- No `print()` statements. Log to stderr via `logging` if needed.
- Call `append_receipt()` after every write (success or failure).

---

## 8. Tool inventory

### Current tool counts

| Server | Tools | Description |
|---|---|---|
| `docx_basic` | 15 | read, search, edit paragraphs, history, diff, receipt |
| `docx_tables` | 9 | table CRUD |
| `docx_layout` | 7 | styles, fonts, margins, PDF export |
| `docx_new` | 7 | create, template, batch, merge |
| `xlsx_basic` | 14 | read, cell CRUD, sheets, sort, dedup |
| `xlsx_formulas` | 9 | formulas, fill-down, auto-sum, validation |
| `xlsx_charts` | 5 | charts, pivot tables, cell styles |
| `xlsx_new` | 6 | create, CSV import, invoice |
| `pptx_basic` | 10 | read, edit, slides, diff |
| `pptx_design` | 8 | background, fonts, global changes, PDF export |
| `pptx_new` | 6 | create, agenda, doc→deck |
| **Total** | **96** | across 11 servers |

### Tool count constraint

Maximum **10 tools** per server. Hard limit, not a guideline. If a natural grouping
exceeds 10 tools, split into two servers. Recommended 6–9 tools per server.

### Recommended server combinations

| Task | Servers |
|---|---|
| Edit a contract | `docx_basic` |
| Contract + tables | `docx_basic` + `docx_tables` |
| Format a document | `docx_layout` |
| Write a new document | `docx_new` |
| Data entry + formulas | `xlsx_basic` + `xlsx_formulas` |
| Build an invoice | `xlsx_new` + `xlsx_formulas` |
| Charts only | `xlsx_charts` |
| Edit a presentation | `pptx_basic` |
| Style a deck | `pptx_basic` + `pptx_design` |
| Create a presentation | `pptx_new` |

---

## 9. Patch protocol — the JSON op format

When a tool accepts a list of operations, the format is always an array of op objects.
Every op has an `"op"` field first. Maximum 50 ops per batch.

### DOCX ops

```json
[
  {"op": "replace_text", "match": "PARTY_A", "new_text": "Acme Corp", "preserve_style": true},
  {"op": "insert_after", "match": "Section 3.", "new_text": "...", "style": "Body Text"},
  {"op": "delete_paragraph", "match": "INTENTIONALLY LEFT BLANK"},
  {"op": "replace_table_cell", "table_index": 0, "row": 2, "col": 1, "new_text": "$5,000"}
]
```

### XLSX ops

```json
[
  {"op": "set_cell", "sheet": "Q3", "cell": "B5", "value": 142500},
  {"op": "set_formula", "sheet": "Q3", "cell": "D5", "formula": "=SUM(B5:C5)*1.1"}
]
```

### PPTX ops

```json
[
  {"op": "set_text", "slide_index": 0, "shape_name": "Title 1", "new_text": "Q3 Results"},
  {"op": "add_slide", "after_index": 2, "layout": "Title and Content", "title": "Key Metrics"}
]
```

---

## 10. Surgical addressing protocol

### The four-tool pattern

Every document editing task follows this sequence:

```
Step 1: LOCATE   — search_paragraphs / search_cells / search_slides
Step 2: INSPECT  — read_paragraph / read_cell / read_slide
Step 3: PATCH    — replace_text / set_cell / set_text
Step 4: VERIFY   — read_paragraph / read_cell / read_slide
```

### Address formats

**DOCX** — section notation built from heading hierarchy:

| Address | Meaning |
|---|---|
| `§2` | All content of section 2 |
| `§2.1` | Subsection 1 within section 2 |
| `§2.p4` | Paragraph 4 within section 2 |
| `§2.t0` | First table in section 2 |
| `p47` | Absolute paragraph 47 (flat fallback) |

**XLSX** — standard Excel notation: `B5`, `A1:D10`

**PPTX** — `slide[N]/shape[name]/pM`

### Token budget — hard ceilings

| Tool category | Max output |
|---|---|
| Full document read | 150 paragraphs (truncate with warning) |
| Paragraph range | `get_max_paragraphs()` — 50 normal / 20 constrained |
| Cell range | `get_max_cells()` — 200 normal / 100 constrained |
| Search results | `get_max_search_results()` — 50 normal / 10 constrained |
| Single slide | 1 slide only |

Every tool response includes `"token_estimate": len(str(response)) // 4`.

### Prohibited patterns

- Never return the full document from a write tool.
- Never implement read-then-write in a single tool.
- Never return all paragraphs when zero matches found — return empty matches array.
- Never load an entire workbook into memory for a search — use `read_only=True`.
- Never return raw XML from any tool.

---

## 11. DOCX engine rules

### The run-level editing rule — most important rule in this file

A Word paragraph contains runs. Each run is a sequence of characters with identical
formatting. A single word can be split across multiple runs.

**NEVER do this:**
```python
paragraph.text = "new content"  # destroys all formatting
```

**Always do this:**
```python
import docxedit
docxedit.replace_string(doc, old_string=match_text, new_string=new_text)
```

For cases docxedit cannot handle, edit runs directly:
```python
for run in paragraph.runs:
    if match_text in run.text:
        run.text = run.text.replace(match_text, new_text)
        # run.bold, run.italic, run.font.* are preserved automatically
```

### Paragraph index stability

Paragraph indices shift when paragraphs are inserted or deleted. Always re-read after
any insert or delete. Prefer `match_text` (content-based) over `paragraph_index`
(position-based) in tool parameters.

### Table indexing

Tables are zero-indexed. Return table dimensions in every `list_tables` response so
the model can validate indices before writing.

### Export to PDF

`export_pdf` in `docx_layout` uses `docx2pdf`. Requires Word on Windows/macOS, or
LibreOffice on Linux. The tool detects the platform and returns a clear error if
neither is available. Never silently fail a PDF export.

---

## 12. XLSX engine rules

### openpyxl vs xlsxwriter

Use `openpyxl` for all tools that read or modify **existing** `.xlsx` files.
Use `xlsxwriter` only for tools that **create a new file from scratch**. `xlsxwriter`
cannot read existing files — it will overwrite them.

### Cell address format

All cell addresses use Excel notation: `"A1"`, `"B5"`. Never use row/column integer
tuples in the tool interface.

```python
from openpyxl.utils import get_column_letter
cell_address = f"{get_column_letter(col)}{row}"
```

### Formula strings

Formula values must include the leading `=` sign: `"=SUM(B2:B10)"`. Validate this in
`patch_validator`. openpyxl does not evaluate formulas — they are stored verbatim.

### Chart creation

Use `openpyxl` chart objects for editing existing files. Supported types: `"bar"`,
`"line"`, `"pie"`, `"area"`, `"scatter"`. Return an error dict for unsupported types —
never silently fall back to a default. `update_chart` uses delete-then-recreate
internally.

---

## 13. PPTX engine rules

### Shape name vs shape index

Always prefer `shape_name` over `shape_index` in tool parameters. Shape names are
stable across slide editing. Shape indices can shift.

### Text frames and paragraphs

Never overwrite `shape.text_frame.text` directly — it destroys paragraph-level
formatting. Edit at the paragraph or run level. The same run-level editing rules from
section 11 apply here.

### Image insertion

```python
slide.shapes.add_picture(image_file, left=Inches(x), top=Inches(y),
                         width=Inches(width), height=Inches(height))
```

Validate that the image file exists before inserting. Return an error dict if not
found or format is unsupported (PNG, JPG, GIF, BMP, TIFF).

### Export to PDF

Same constraint as DOCX — requires Word/PowerPoint or LibreOffice. Detect platform,
return clear error if unavailable.

---

## 14. Error handling contract

Every engine function returns a dict. Never raise. The dict must include `"success"`.

**On success:**
```python
{"success": True, "op": "name", "progress": [...], "token_estimate": N, ...}
```

**On failure:**
```python
{"success": False, "error": "Human-readable description.", "hint": "What to try instead.",
 "backup": backup_path_or_none, "progress": [...], "token_estimate": N}
```

### Standard error messages

| Situation | Error | Hint |
|---|---|---|
| File not found | `"File not found: {path}"` | `"Check that file_path is absolute and the file exists."` |
| Wrong file type | `"Expected .docx file, got .{ext}"` | `"Use the correct server for this file type."` |
| Match not found | `"match_text not found in document"` | `"Use search_paragraphs to verify the exact text."` |
| Invalid op | `"Unknown op: {op_name}"` | `"Allowed ops: {allowed_ops}"` |
| Index out of range | `"paragraph_index {n} out of range (0-{max})"` | `"Use read_document to get current paragraph count."` |
| Sheet not found | `"Sheet '{name}' not found"` | `"Use list_sheets to get available sheet names."` |
| Cell address invalid | `"Invalid cell address: {addr}"` | `"Use Excel notation like B5 or C12."` |

---

## 15. Testing rules

### Test structure

Tests import directly from `engine.py` — not from `server.py`. This keeps tests
independent of the MCP protocol layer.

```python
# tests/test_docx_basic.py
from servers.docx_basic.engine import read_document, replace_text
```

### Fixture rules

Test fixtures in `tests/fixtures/` are committed to the repo as real office files.
Never regenerate fixtures in tests — use `tmp_path` to copy and modify within a test.

### Coverage requirements

- `shared/` modules: 100% line coverage
- `engine.py` for all servers: ≥ 90% line coverage
- Error paths must be explicitly tested

### Required tests for every write operation

1. Success case on the correct file type
2. Written content is readable back and correct
3. A snapshot was created in `.mcp_versions/`
4. `"backup"` key is present in the return dict
5. File not found failure case
6. Wrong file type failure case
7. Formatting preservation (for DOCX operations on styled text)

---

## 16. MCP tool schema rules

### Allowed parameter types

- `str` — file paths, text, cell addresses, sheet names
- `int` — indices
- `float` — dimensions (inches, cm)
- `bool` — flags
- `list[dict]` — op arrays only

Do not use `Optional[T]`, `Union`, `Any`, `dict`, or Pydantic models as parameter
types. For optional parameters, use a primitive default value.

### Enum values

Document allowed string values in the docstring, not the type annotation:
```python
def add_chart(file_path: str, chart_type: str, ...) -> dict:
    """Create chart. chart_type: bar, line, pie, area, scatter."""
```

### Tool naming

Lowercase snake_case verbs: `read_document`, `replace_text`, `add_chart`.
Allowed verbs: `read`, `list`, `get`, `set`, `add`, `delete`, `insert`, `replace`,
`restore`, `export`, `search`, `fetch`, `diff`, `fill`, `create`, `merge`, `batch`.

---

## 17. Local model constraints

### Context budget

Local models typically have 12,000–32,000 usable tokens depending on hardware and
quantization. This covers CPU and GPU deployments.

Budget allocation with 8 tools loaded:
- Tool schemas: ~700 tokens
- System prompt: ~200 tokens
- Available for document + conversation: remainder

A 50-page Word document extracts to ~15,000–20,000 tokens. The `read_document` tool
truncates at `get_max_paragraphs()` and returns `"truncated": true` with a hint.

### Constrained mode

Set `OFFICE_MCP_8GB_MODE=1` in the MCP server `env` block to halve all output limits.
The installer detects low-resource machines and offers to set this automatically.

### Tool description length

Keep descriptions ≤ 80 characters. This is checked in CI. Test with:
```python
assert len(docstring) <= 80
```

---

## 18. Naming conventions

### Files and directories

- Server directories: `{app}_{tier}` — `docx_basic`, `xlsx_charts`, `pptx_design`
- Python files: `snake_case.py`
- Test files: `test_{server_name}.py`
- Fixture files: `{description}_{complexity}.{ext}`

### Python identifiers

- Functions: `snake_case` verbs — `read_document`, `apply_patch`
- Classes: `PascalCase` — `PatchValidator`
- Constants: `UPPER_SNAKE_CASE` — `MAX_OPS_PER_BATCH = 50`
- Private helpers: `_snake_case`

### Commit messages

Format: `{type}({scope}): {description}`

Types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`
Scope: server name or `shared` or `install`

---

## 19. What Claude must never do

1. **Never use `paragraph.text = value`** in DOCX editing. Use `docxedit.replace_string()`
   or run-level iteration.

2. **Never use `xlsxwriter` to open an existing `.xlsx` file.** It will truncate the
   file. Use it only for creating new files from scratch.

3. **Never write a tool with more than 10 parameters.** Split the tool or accept a
   `config: str` JSON string.

4. **Never add business logic to `server.py`.** All logic belongs in `engine.py`.

5. **Never print to stdout in any engine or shared module.** Use `sys.stderr` or
   `logging`. Stdout is the MCP JSON-RPC channel.

6. **Never write to a file without calling `snapshot()` first.** No exceptions.

7. **Never return a plain string from a tool function.** Always return a dict.

8. **Never exceed 10 tools in a single server.**

9. **Never add a new dependency without updating the server's `pyproject.toml`.**

10. **Never modify `shared/` from within a server directory.** `shared/` is a
    read-only import target.

11. **Never return a tool response without a `"progress"` array.** Use `[]` for trivial
    reads. A missing `"progress"` key is a defect.

12. **Never skip receipt logging after a write.** `append_receipt()` must be called
    after every write, success or failure.

13. **Never use full absolute paths in progress messages.** Use `Path(x).name`.

14. **Never skip file path normalisation.** Every tool must call `resolve_path()` as
    its first operation.

15. **Never hardcode output size limits.** Always call `platform_utils.get_max_*()`.

---

## 20. Adding a new tool — checklist

- [ ] Verify server will not exceed 10 tools
- [ ] Tool name follows verb-first snake_case convention
- [ ] Write the engine function in `engine.py` first (no MCP imports)
- [ ] Engine function returns dict with `"success"`, `"progress"`, `"token_estimate"`
- [ ] Engine function calls `snapshot()` before any write
- [ ] Engine function calls `append_receipt()` after every write
- [ ] Engine function includes `"backup"` path in return dict on writes
- [ ] Engine function returns error dict (not raise) for all failure cases
- [ ] Error dict includes `"hint"` field
- [ ] Output limits use `platform_utils.get_max_*()` helpers
- [ ] Add `@mcp.tool()` in `server.py` with single `return engine.fn(...)` body
- [ ] Tool docstring is ≤ 80 characters
- [ ] All parameters have type annotations
- [ ] Optional parameters have primitive default values
- [ ] Add success test in `tests/test_{server}.py`
- [ ] Add failure test (file not found)
- [ ] `uv run pytest tests/test_{server}.py` — all pass
- [ ] `uv run ruff check servers/{server}/`
- [ ] `uv run pyright servers/{server}/`
- [ ] Update tool inventory table in section 8 of this file

---

## 21. Common failure modes

**Tool output is empty string** — engine printed to stdout. Replace all `print()` with
`logging.getLogger(__name__).debug()`.

**`replace_text` strips bold/italic** — used `paragraph.text = value` instead of
`docxedit.replace_string()`. Fix: replace all direct `.text =` on paragraph objects.

**openpyxl produces corrupt `.xlsx` after chart modification** — chart data references
went stale. Fix: always delete-then-recreate charts, never modify in place.

**Version snapshot creates infinite loop** — `snapshot()` is being called with a path
inside `.mcp_versions/`. Fix: `resolve_path()` rejects `.mcp_versions/` paths.

**Local model hallucinates parameter names** — too many parameters or ambiguous names.
Fix: rename parameters to be maximally self-documenting, reduce parameter count.

**mcp_config_writer.py corrupts existing mcp.json** — LM Studio's mcp.json uses
relaxed JSON (trailing commas, inline comments). Fix: use `json5` for reading,
standard `json.dumps()` for writing.

---

## 22. Dependency policy

### Approved dependencies

| Library | Used in | Version |
|---|---|---|
| `mcp[cli]` | all servers | `>=1.2.0` |
| `python-docx` | docx servers | `>=1.1.0` |
| `docxedit` | docx servers | `>=1.2.0` |
| `openpyxl` | xlsx servers | `>=3.1.0` |
| `xlsxwriter` | xlsx_new, xlsx_charts | `>=3.2.0` |
| `python-pptx` | pptx servers | `>=0.6.23` |
| `docx2pdf` | docx_layout, pptx_design | `>=0.1.8` |
| `json5` | install only | `>=0.9.0` |
| `pytest` | tests | `>=8.0` |
| `ruff` | dev | `>=0.4.0` |
| `pyright` | dev | `>=1.1.0` |

### Before adding a new dependency

1. Check if an approved library already covers the need.
2. Verify license is MIT, Apache 2.0, or BSD. No GPL.
3. Check library was updated within the last 12 months.
4. Run `uv audit` for known vulnerabilities.
5. Add to the server's `pyproject.toml` with a minimum version constraint.
6. Update the approved table above.

### Prohibited libraries

- `Spire.Doc`, `Aspose` — commercial license
- `win32com` / `pywin32` — Windows-only
- `pandas` — too heavy; openpyxl is sufficient

---

## 23. Git and PR rules

### Branch naming

`{type}/{description-in-kebab-case}` — e.g. `feat/docx-basic-replace-text`

### PR requirements

Every PR must:
- Target `main`
- Pass all CI checks: `pytest`, `ruff check`, `pyright`
- Not decrease test coverage below 90% for modified files
- Not add a tool description > 80 chars
- Not add a server with > 10 tools

### CI checks

```yaml
- uv sync --frozen
- uv run ruff check .
- uv run ruff format --check .
- uv run pyright servers/ shared/
- uv run pytest tests/ --cov=servers --cov=shared --cov-fail-under=90
- python -c "check all tool docstrings <= 80 chars"
```

---

## 24. Source code editing protocol

### Core rule: never rewrite a file that already exists

Use targeted str_replace edits. Full-file rewrites are only acceptable for:
- Creating a brand new file that does not exist
- Files under 30 lines where the change touches > 60% of it

### str_replace format

```
EDIT: servers/docx_basic/engine.py
<<<OLD>>>
def replace_text(file_path: str, match_text: str) -> dict:
<<<NEW>>>
def replace_text(file_path: str, match_text: str, preserve_style: bool = True) -> dict:
<<<END>>>
```

Rules:
- OLD block must be verbatim — no paraphrasing, no line numbers
- OLD block must be unique in the file (add context lines if needed)
- NEW block contains only the replacement, not the whole function
- One edit per logical change
- Always read the file before editing

### Token cost reference

| Operation | str_replace | Full rewrite |
|---|---|---|
| Add one parameter | ~40 tokens | ~900 tokens |
| Fix one bug | ~65 tokens | ~1,200 tokens |
| Add one tool | ~95 tokens | ~450 tokens |

---

## 25. Cross-platform compatibility

### Path handling

All path operations use `pathlib.Path`. Never string concatenation with `/` or `\\`.

```python
# Correct
backup_path = Path(base_dir) / (filename + ".bak")
```

### Line endings

`.gitattributes` enforces LF for all files except `.bat`/`.cmd` (CRLF).

### Platform detection

All platform-specific logic goes through `shared/platform_utils.py`. Never inline
`sys.platform` checks in engine or server code.

### PDF export platform matrix

| Platform | Primary | Fallback | Error if unavailable |
|---|---|---|---|
| Windows | `docx2pdf` (Word via COM) | LibreOffice CLI | Yes |
| macOS | `docx2pdf` (Word via AppleScript) | LibreOffice CLI | Yes |
| Linux | LibreOffice CLI | None | Yes — with install hint |

### Windows long path

`resolve_path()` adds the `\\?\` prefix for paths > 200 characters on Windows.

---

## 26. Progress output system

### The progress field

Every tool response includes a `"progress"` array. Built with helpers from
`shared/progress.py`. Icons: `✔` success, `✘` failure, `→` info, `⚠` warning, `↩` undo.

```python
progress = []
progress.append(ok(f"Opened {path.name}", f"{para_count} paragraphs"))
progress.append(ok("Snapshot saved", Path(backup).name))
progress.append(ok(f"Replaced '{match}' → '{new_text}'", f"{n} occurrences"))
progress.append(ok(f"Saved {path.name}"))
```

### Standard message templates

- Open: `"Opened {filename}"` / detail: item count
- Save: `"Saved {filename}"`
- Snapshot: `"Snapshot saved"` / detail: snapshot filename
- Replace: `"Replaced '{old}' → '{new}'"` / detail: occurrence count
- Insert: `"Inserted paragraph at index {n}"`
- Set cell: `"Set {cell} = {value}"` / detail: sheet name
- Error: the exception message verbatim

---

## 27. File path handling

### resolve_path() behaviour

`shared/file_utils.resolve_path()` handles all of these:
- `~/Documents/file.docx` — home expansion
- `$HOME/file.docx` — env var expansion
- Paths with wrapping quotes (drag-and-drop artifacts) — stripped
- `C:\Users\...` Windows paths — normalised to forward slashes
- `\\?\` long path prefix — stripped before processing
- Relative paths — resolved from CWD

Rejects: paths containing null bytes, paths inside `.mcp_versions/`.

### file_path is always the first parameter

Every tool that operates on a file takes `file_path: str` as its first parameter.

### File type validation

Every engine function validates the file extension immediately after `resolve_path()`.
Wrong file type is the second most common user error after wrong path.

---

## 28. Operation receipt log

### What it is

Every write appends a structured entry to `{filename}.mcp_receipt.json` alongside the
document. This is the user's audit trail — what changed, when, by which tool.

```json
{
  "file": "contract.docx",
  "entries": [
    {
      "ts": "2026-03-25T14:30:00Z",
      "tool": "replace_text",
      "server": "docx_basic",
      "args": {"match": "PARTY_A", "new_text": "Acme Corp"},
      "result": "✔ Replaced 3 occurrences",
      "backup": ".mcp_versions/contract_2026-03-25T14-30-00Z.bak",
      "success": true
    }
  ]
}
```

### read_receipt tool

Every `_basic` server includes `read_receipt(file_path, last_n=10)` so the model can
show users what has been done to a file without opening any external log.

### Dry run mode

Every write tool supports `dry_run: bool = False`. When `True`, the tool shows what
would change — including the progress output — without modifying the file. No snapshot
is taken and no receipt entry is written.

---

## Transport and Deployment (STANDARDS.md §30, §31)

Each of the 11 servers still supports `--transport {stdio,http}` via its own
`server.py::main()` for local/individual use (LM Studio "add one server"
installs) — that per-server code is unchanged.

For Docker/remote deployment, `unified_server.py` (repo root) combines all 11
servers into **one process on one port**: each server's `FastMCP` instance
(raw `mcp` SDK) is mounted at its own path (`/docx-basic`, `/xlsx-basic`,
etc.) inside one Starlette app via `streamable_http_app()` + `Mount()`, with
each server's session-manager lifespan explicitly entered through
`contextlib.AsyncExitStack` — Starlette's `Mount()` does not auto-propagate
lifespan events to sub-apps, and the raw `mcp` SDK's `streamable_http_app()`
returns a plain `Starlette` (its lifespan reached via
`app.router.lifespan_context`, unlike the `fastmcp` package's convenience
`.lifespan` attribute) — verified live against real servers before relying
on it. Every server's own `/health`, `/version`, and `/mcp` routes (already
defined via `@mcp.custom_route` in its own `server.py`) come along for free
under its mount prefix — nothing server-specific is duplicated in
`unified_server.py`. This exists specifically to cut idle RAM:
python-docx/openpyxl/python-pptx previously loaded eleven times (one per
server's own process, ~650 MiB combined) now load once (~80–90 MiB total).

Bearer auth (`shared/shared/deploy_auth.py`, `build_auth("OFFICE", host, port)`) is
shared across all 11 servers via the `shared` workspace package — one token set
governs the whole repo:

- `OFFICE_TOKENS_FILE` (named tokens, JSON `{name: token}`) — highest priority
- `OFFICE_TOKENS` (inline `"name:token,name2:token2"`)
- `OFFICE_API_KEY` (single shared token)
- unset = open mode (no auth) — localhost/private-network use only

`Dockerfile` + `docker-compose.yml` build one image — **`uv sync --frozen --all-packages`**
is required (this is a true `[tool.uv.workspace]`; plain `uv sync` only installs the
root project's own deps, which are empty, not the 11 members' runtime deps like
`python-docx`/`python-pptx`/`openpyxl`) — and run **one container**
(`unified_server.py`, `OFFICE_HOST`/`OFFICE_PORT`, default port `8830`). CI
builds the image on every push (`docker-build` job, no push); `release.yml`
publishes `ghcr.io/<owner>/mcp-microsoft-office:<version>` on tag via the
shared `azzindani/MCP_Math` composite action.

---

*Last updated: 2026-04-11*
*Covers: office-mcp — 11 servers, 96 tools, Python 3.12+*
