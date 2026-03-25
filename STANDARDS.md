# STANDARDS.md — MCP Server Development Standards

This document defines the complete standard for building open-source MCP
(Model Context Protocol) servers intended for local LLM use. It is derived from
real architectural decisions, real failure modes, and real hardware constraints
encountered while building production-grade MCP tooling.

These standards apply to any MCP server regardless of domain — document editing,
browser automation, email, calendar, database, file management, or anything else.
They are not optional guidelines. They are the rules that determine whether a server
works reliably on constrained hardware with a 9B parameter local model.

---

## Table of contents

1.  [Why these standards exist](#1-why-these-standards-exist)
2.  [The core mental model — what an MCP server actually is](#2-the-core-mental-model--what-an-mcp-server-actually-is)
3.  [Language and runtime selection](#3-language-and-runtime-selection)
4.  [Repository structure](#4-repository-structure)
5.  [The three-tier split — when to build separate servers](#5-the-three-tier-split--when-to-build-separate-servers)
6.  [Tool count discipline](#6-tool-count-discipline)
7.  [The four-tool pattern — the fundamental execution loop](#7-the-four-tool-pattern--the-fundamental-execution-loop)
8.  [Surgical read protocol — never return more than needed](#8-surgical-read-protocol--never-return-more-than-needed)
9.  [Tool schema design](#9-tool-schema-design)
10. [The patch protocol — structured ops over full rewrites](#10-the-patch-protocol--structured-ops-over-full-rewrites)
11. [Engine and server separation](#11-engine-and-server-separation)
12. [Return value contract](#12-return-value-contract)
13. [Error handling contract](#13-error-handling-contract)
14. [State and version control](#14-state-and-version-control)
15. [Token budget discipline](#15-token-budget-discipline)
16. [VRAM tiers and hardware constraints](#16-vram-tiers-and-hardware-constraints)
17. [Testing standards](#17-testing-standards)
18. [Cross-platform compatibility](#18-cross-platform-compatibility)
19. [Multi-platform AI client compatibility](#19-multi-platform-ai-client-compatibility)
20. [Transport modes — stdio and HTTP](#20-transport-modes--stdio-and-http)
21. [Installation and distribution](#21-installation-and-distribution)
22. [Naming conventions](#22-naming-conventions)
23. [Dependency policy](#23-dependency-policy)
24. [CI/CD requirements](#24-cicd-requirements)
25. [Documentation requirements](#25-documentation-requirements)
26. [What to never do](#26-what-to-never-do)
27. [Checklist — new server from scratch](#27-checklist--new-server-from-scratch)
28. [Checklist — new tool in existing server](#28-checklist--new-tool-in-existing-server)

---

## 1. Why these standards exist

Most MCP servers are built for cloud AI with large context windows and fast inference.
When those servers are used with local LLMs on consumer hardware, they fail in
predictable ways:

- Tool schemas consume 20-30% of the available context window before any work starts
- Tools return entire file contents when only three lines are needed
- A single "helpful" tool does too many things, confusing a 9B model into picking wrong
- No version control means a bad tool call silently corrupts the user's file
- Install requires 15 manual steps, so nobody uses it

These standards exist to prevent all of these failures by design, not by luck.

The target constraint that drives every decision in this document:

> **A user with an 8GB GPU, running a 9B parameter local model, doing real work on
> real files, must be able to use these tools without hitting context limits, without
> corrupting data, and without needing a developer to set it up.**

Every rule in this document traces back to that constraint.

---

## 2. The core mental model — what an MCP server actually is

An MCP server is a **structured API that a language model calls with JSON arguments
and receives JSON results from**. It is not a chat assistant. It is not a script
runner. It is not an AI agent. It is a deterministic function executor.

The model provides intelligence — deciding what to call, in what order, with what
arguments. The MCP server provides execution — doing the operation reliably, returning
structured confirmation, never guessing.

This distinction matters because it defines the boundary:

```
Model's job:        understand intent, choose tools, generate arguments, decide next step
MCP server's job:   validate input, execute operation, return structured result
```

The server must never cross into the model's job. No AI inference inside tools. No
"smart" behavior that guesses what the user probably meant. No tools that decide
to do extra work beyond what was asked. Deterministic in, deterministic out.

---

## 3. Language and runtime selection

### The rule: libraries dictate language, not preference

Choose the language that has the best library support for your domain. Not the language
you prefer. Not the language that's fashionable. The language where the problem is
already solved.

| Domain | Best language | Reason |
|---|---|---|
| Office document editing (docx, xlsx, pptx) | Python | python-docx, openpyxl, python-pptx — no equivalents elsewhere |
| PDF manipulation | Python | pdfplumber, PyMuPDF, reportlab |
| Browser automation | Python or TypeScript | playwright-python or playwright (Node) |
| Email / IMAP / SMTP | Python | imaplib, smtplib — mature, stdlib |
| Database (SQL) | Python or TypeScript | Either has mature connectors |
| File system operations | Go or Rust | Single binary, no runtime, fastest |
| Web API wrappers | TypeScript | Best for JSON-heavy REST APIs |
| OS-level automation | Rust or Go | Single binary, zero dependencies |
| Image processing | Python | Pillow, OpenCV |

### Python setup

Pin Python to `3.11`. Use `uv` as the package manager. Never use pip directly.
Never use conda. Never use poetry for new projects — uv workspaces are superior
for monorepos.

```toml
# .python-version
3.11
```

```toml
# pyproject.toml (root)
[project]
requires-python = ">=3.11"
```

### TypeScript setup

Use Node.js 20 LTS. Use `npm` with `package-lock.json` committed. Pin the
`@modelcontextprotocol/sdk` version.

### Go setup

Use Go 1.22+. Commit `go.sum`. Use the community MCP SDK (`github.com/mark3labs/mcp-go`).

### Rust setup

Use Rust stable channel. Use the `rmcp` crate. Commit `Cargo.lock`.

---

## 4. Repository structure

### Monorepo is the default for multi-server projects

If you are building more than one MCP server that share a domain (e.g., three servers
for Word/Excel/PowerPoint, or two servers for email read vs email write), use a monorepo
with a workspace. One repo, one lockfile, one CI pipeline, one install script.

If you are building a single standalone server, a flat repo is fine.

### Monorepo layout

```
{project-name}/
│
├── shared/                     # code shared by ALL servers — never duplicate
│   ├── __init__.py
│   ├── version_control.py      # snapshot / rollback — if your tools write files
│   ├── patch_validator.py      # validate op arrays before applying
│   ├── file_utils.py           # path resolution, atomic writes, JSON helpers
│   └── platform_utils.py       # OS detection, config paths, VRAM mode
│
├── servers/
│   ├── {name}_basic/           # tier 1 — CRUD only
│   │   ├── __init__.py
│   │   ├── server.py           # FastMCP setup + tool definitions (thin)
│   │   ├── engine.py           # pure domain logic (no MCP imports)
│   │   └── pyproject.toml
│   │
│   ├── {name}_medium/          # tier 2 — structured operations
│   │   └── ...
│   │
│   └── {name}_advanced/        # tier 3 — complex operations
│       └── ...
│
├── tests/
│   ├── fixtures/               # real test files, committed to repo
│   ├── conftest.py
│   └── test_{server_name}.py
│
├── install/
│   ├── install.sh              # Linux / macOS — POSIX sh compatible
│   ├── install.bat             # Windows CMD
│   └── mcp_config_writer.py    # writes to AI platform config files
│
├── pyproject.toml              # root workspace
├── uv.lock                     # single lockfile
├── .python-version             # pinned Python version
├── .gitattributes              # LF line endings, CRLF for .bat
├── .editorconfig               # UTF-8, 4-space indent, final newline
├── CLAUDE.md                   # AI coding agent instructions
├── STANDARDS.md                # this file
└── README.md
```

### Single-server flat layout

```
{server-name}/
├── server.py
├── engine.py
├── shared/                     # only if truly needed
├── tests/
│   ├── fixtures/
│   └── test_engine.py
├── install/
│   ├── install.sh
│   └── install.bat
├── pyproject.toml
├── uv.lock
├── CLAUDE.md
└── README.md
```

---

## 5. The three-tier split — when to build separate servers

Every MCP server targets a specific complexity tier. Never mix tiers in one server.
This is the most important structural decision because it directly controls how many
tools the local model has to reason about at once.

### Tier 1 — Basic (CRUD only)

Tools that read data and perform simple create/update/delete operations on individual
nodes. No complex transformations. No formatting. No cross-reference operations.

Examples: read a paragraph, replace text, add a row to a table, set a cell value,
add a slide, delete a record.

**Tool count target: 6-8 tools.**
**This tier must stand alone** — a user doing simple tasks should never need to load
tier 2 or 3 alongside it.

### Tier 2 — Medium (structured operations)

Tools that perform multi-step structured operations — formulas, conditional logic,
template filling, relationships between parts. These operations are more complex than
CRUD but do not require layout or visual reasoning.

Examples: inject Excel formulas, set data validation, manage table relationships,
fill template placeholders, parse structured data from documents.

**Tool count target: 5-7 tools.**
**Can be loaded alongside tier 1.** Total combined should not exceed 15 tools.

### Tier 3 — Advanced (layout, visual, export)

Tools that deal with visual layout, formatting, style application, cross-element
alignment, and export operations. These require more context to use correctly and
are rarely needed alongside tier 1 operations.

Examples: set fonts, apply styles, create charts, set page margins, export to PDF,
manage slide layouts, add images with positioning.

**Tool count target: 5-6 tools.**
**Load standalone** — advanced tools are used in dedicated formatting sessions, not
mixed with content editing.

### Decision tree for tier assignment

```
Does the tool read or write a single named node (paragraph, cell, shape)?
  Yes → Tier 1

Does the tool apply a structured formula, rule, or relationship between nodes?
  Yes → Tier 2

Does the tool change visual appearance, layout, or export format?
  Yes → Tier 3

Does the tool span all three concerns?
  → Split it into multiple tools, one per tier
```

---

## 6. Tool count discipline

### Hard limits by tier and hardware target

| Target hardware | Max tools per server | Max tools loaded simultaneously |
|---|---|---|
| 4-6 GB VRAM (≤7B model) | 6 | 6 (one server only) |
| 8 GB VRAM (9B model) | 8 | 12 (tier 1 + tier 2) |
| 12-16 GB VRAM (14B model) | 10 | 16 (any two servers) |
| 24 GB+ VRAM (32B+ model) | 12 | 20 |

**The general open-source target is 8GB VRAM.** Design for 8 tools per server, 12
tools maximum loaded simultaneously. If a domain naturally produces more tools, split
into more servers at finer tier granularity.

### Why tool count matters more than you think

Every tool's JSON schema sits in the model's KV cache for the entire conversation.
At 8GB VRAM with a 9B model, the KV cache budget is approximately 10,000-12,000 tokens.
Each tool schema with a docstring and 3-4 parameters consumes approximately 80-120
tokens. Ten tools consume ~1,000 tokens — roughly 8-10% of the entire available context
window — before the model has seen a single byte of user data.

Beyond the token cost, there is a cognitive cost: the model must choose from N tools
on every turn. At 8 tools, a 9B model makes correct selections reliably. At 15 tools,
errors increase. At 20 tools, the model frequently confuses similar-named tools or
hallucinates parameters.

**The rule is: fewer tools, sharper tools.** A tool that does one thing precisely is
better than a tool that does three things approximately.

---

## 7. The four-tool pattern — the fundamental execution loop

Every document or data editing task follows this exact four-step loop. Encode this
in your tool design so the model is guided through it naturally.

```
LOCATE  →  INSPECT  →  PATCH  →  VERIFY
```

### Step 1: LOCATE

Find the node(s) that need changing without reading everything else.
Tool design: `search_*` or `get_*_index` or `list_*` — returns addresses/indices only.

### Step 2: INSPECT

Read only the located node(s) to understand current content and structure.
Tool design: `read_*` with a specific address parameter — returns one node in detail.

### Step 3: PATCH

Apply the targeted edit to only that node.
Tool design: `set_*`, `replace_*`, `update_*` — writes to address, returns confirmation.

### Step 4: VERIFY

Read back only the edited node to confirm the change applied correctly.
Tool design: same `read_*` from Step 2 — model confirms result matches intent.

### Example — updating a value in a database record

```
User: "Update the price of Product ID 42 to $149.99"

Round 1 (LOCATE):   search_records(table="products", where="id=42")
                    → {"matches": [{"id": 42, "name": "Widget Pro", "price": 129.99}]}

Round 2 (INSPECT):  read_record(table="products", id=42)
                    → {"id": 42, "name": "Widget Pro", "price": 129.99, "sku": "WP-001"}

Round 3 (PATCH):    set_field(table="products", id=42, field="price", value=149.99)
                    → {"success": true, "old_value": 129.99, "new_value": 149.99}

Round 4 (VERIFY):   read_record(table="products", id=42)
                    → {"id": 42, "name": "Widget Pro", "price": 149.99, "sku": "WP-001"}

Total tokens read from database: ~200
If a "read full table" approach had been used: potentially thousands
```

### Tools that violate this pattern

These patterns are anti-patterns. If your tool design produces these, refactor:

- A tool that searches AND reads AND edits in one call — split into three
- A tool that returns the full dataset to let the model "find what it needs"
- A tool that writes without returning what changed
- A tool that reads 10 records to let the model pick the right one

---

## 8. Surgical read protocol — never return more than needed

### The fundamental rule

A tool that returns data must return **only the data the model asked for**. Not
the surrounding context. Not related data "that might be useful". Not the full
parent structure because reading a child is convenient.

This is the most important performance decision in the entire server. Get this wrong
and every operation costs 10x the tokens it should.

### Mandatory surgical tools for every domain

Every server that manages structured data must implement these classes of tools:

**Index tool** — returns structure without content:
```python
# Returns keys, addresses, counts, metadata — zero actual content
get_document_outline()  # heading text + paragraph indices, not body text
get_sheet_summary()     # column names + row count, not cell values
list_endpoints()        # route names + methods, not request/response bodies
list_records()          # IDs + primary key values, not full records
```

**Search tool** — scans content, returns matching addresses:
```python
# Returns matches with their addresses — caller then reads only those
search_paragraphs(query)  # returns paragraph indices, not full paragraphs
search_cells(query)       # returns cell addresses, not full rows
search_records(where)     # returns IDs, not full records
search_logs(pattern)      # returns line numbers, not surrounding lines
```

**Bounded read tool** — reads a specific address with a hard size limit:
```python
# Returns exactly one node or a bounded slice
read_paragraph(index)          # one paragraph with run details
read_cell_range(range_address) # bounded range, hard cap on cells returned
read_record(id)                # one full record
read_log_range(start, end)     # bounded line range, hard cap on lines
```

### Return size limits by data type

Enforce these limits in the engine, not in the model. The model cannot be trusted
to limit its own reads.

| Data type | Default limit | 8GB VRAM limit | Enforcement |
|---|---|---|---|
| Text paragraphs | 50 per call | 20 per call | Error if exceeded |
| Table/spreadsheet rows | 50 per call | 20 per call | Error if exceeded |
| Table columns | 20 per call | 10 per call | Truncate with warning |
| Search results | 50 per call | 10 per call | `max_results` parameter |
| Log lines | 100 per call | 50 per call | Error if exceeded |
| JSON object depth | 5 levels | 3 levels | Flatten deeper structures |
| List items | 100 per call | 40 per call | Truncate with flag |

Every tool response that was limited must include:
```python
{
    "truncated": True,  # or False — always explicit
    "returned": 20,
    "total_available": 847,
    "hint": "Use read_paragraph(index) to read specific paragraphs."
}
```

### The token_estimate field

Every tool response must include a rough token count of its own output:
```python
response["token_estimate"] = len(str(response)) // 4
```

This is not for the developer — it's for the model. When the model can see how much
context each tool call consumed, it can budget remaining calls accordingly without
exceeding the context window.

---

## 9. Tool schema design

### Docstring length — the 80-character rule

Every `@mcp.tool()` docstring must be 80 characters or fewer. These strings are
sent to the model on every turn as part of the tool schema. They are not documentation
for humans — they are context that the model uses to decide which tool to call.

Long descriptions waste tokens. Ambiguous descriptions cause wrong tool selection.
The ideal description is a precise action statement:

```python
# Good — 52 characters, unambiguous
"""Find paragraphs matching query. Returns indices only."""

# Bad — 94 characters, wastes tokens
"""This tool searches through all paragraphs in the document and returns the ones
that contain the specified query string."""

# Bad — 38 characters but ambiguous
"""Search the document."""
```

Test this in CI: `assert len(tool.__doc__) <= 80`.

### Parameter naming

Parameters are lowercase snake_case nouns that describe what they contain, not what
to do with them.

```python
# Correct
file_path: str
paragraph_index: int
sheet_name: str
cell_address: str
max_results: int

# Wrong — verb-first
get_file_path: str
target_index: int

# Wrong — camelCase
filePath: str
sheetName: str

# Wrong — abbreviations
fp: str
p_idx: int
```

### Allowed parameter types

Only use these types in tool function signatures:
- `str` — paths, names, addresses, text content, enum values as strings
- `int` — indices, counts, limits
- `float` — dimensions, percentages, numeric values
- `bool` — flags with sensible defaults
- `list[dict]` — only for batch op arrays

Never use:
- `Optional[T]` — use `T = None` instead
- `Union[T, S]` — split into two tools or use a discriminated string param
- `Any` — always type it precisely
- `dict` — too vague; model hallucinate arbitrary keys
- Custom Pydantic models — generates complex schemas that confuse small models
- `Enum` — use `str` with documented valid values in the docstring

### Optional parameters

Optional parameters add to schema size on every turn. Every optional parameter
that exists has a cost. Rules:

1. Default must be a primitive: `None`, `""`, `0`, `False`, `10`
2. Never use `[]` or `{}` as defaults — Python mutable default bug
3. If removing the default makes the tool significantly harder to use, keep it
4. If the optional parameter is rarely used, consider making it a separate tool

### Enum values in docstrings

When a parameter accepts only specific values, list them in the docstring:

```python
@mcp.tool()
def add_chart(
    file_path: str,
    sheet_name: str,
    chart_type: str,    # "bar", "line", "pie", "area", "scatter"
    data_range: str,
    title: str,
) -> dict:
    """Create chart from data range. chart_type: bar line pie area scatter."""
```

List the values compactly in the docstring, not as `Field(description=...)`.
Both consume tokens but the docstring approach is simpler and keeps the schema
cleaner.

---

## 10. The patch protocol — structured ops over full rewrites

### When to use a patch protocol

Any tool that modifies structured data should accept a **list of operations** rather
than a single operation when the task naturally involves multiple changes. A contract
with 5 placeholder fields should be filled in one `apply_patch` call with 5 ops, not
5 separate tool calls.

The patch protocol reduces agentic loop turns, which directly reduces token consumption
in the KV cache accumulation across the conversation.

### Standard op array format

Every patch op array follows this structure:

```json
[
  {
    "op": "operation_name",
    "required_field_1": "value",
    "required_field_2": "value"
  },
  {
    "op": "another_operation",
    "required_field": "value"
  }
]
```

Rules:
- `"op"` is always the first key
- All other fields are operation-specific required fields
- Unknown extra fields are allowed (ignored) for forward compatibility
- Maximum 50 ops per batch — force multiple calls for larger batches
- Ops are applied sequentially — document this clearly

### Op naming convention

Op names are `verb_noun` snake_case:
- `replace_text`, `set_cell`, `insert_row`, `delete_paragraph`
- `add_chart`, `set_formula`, `update_style`
- Not: `textReplace`, `cell_setter`, `chart-add`

The verb set is: `replace`, `set`, `insert`, `delete`, `add`, `update`, `move`.
Do not invent new verbs without strong reason.

### Validation before execution

Always validate the entire op array **before** applying any operation:

```python
def apply_patch(file_path: str, ops: list[dict]) -> dict:
    # Step 1: validate all ops first — no partial application
    valid, error = validate_ops(ops, ALLOWED_OPS)
    if not valid:
        return {"success": False, "error": error, "applied": 0}

    # Step 2: snapshot before any write
    backup = snapshot(file_path)

    # Step 3: apply ops sequentially
    results = []
    for op in ops:
        result = _apply_single_op(file_path, op)
        results.append(result)
        if not result["success"]:
            # Stop on first failure — do not partially apply
            return {
                "success": False,
                "error": f"Op {len(results)} failed: {result['error']}",
                "applied": len(results) - 1,
                "backup": backup,
                "hint": "Use restore_version to undo partial changes."
            }

    return {
        "success": True,
        "applied": len(ops),
        "backup": backup,
        "results": results,
    }
```

Stop on first failure. Never partially apply a batch and report success. Include the
backup path in the failure response so the model can offer rollback.

---

## 11. Engine and server separation

### The mandatory split

Every server has exactly two Python files for logic:

**`engine.py`** — pure domain logic, zero MCP imports:
```python
# engine.py imports
from pathlib import Path
from shared.version_control import snapshot
from shared.patch_validator import validate_ops
# domain library imports (docx, openpyxl, requests, sqlite3, etc.)

# engine.py does NOT import:
# from mcp import ...
# from fastmcp import ...
# import mcp
```

**`server.py`** — thin MCP wrapper, zero domain logic:
```python
# server.py structure
from mcp.server.fastmcp import FastMCP
from . import engine

mcp = FastMCP("server-name")

@mcp.tool()
def tool_name(param: str) -> dict:
    """Short description under 80 chars."""
    return engine.tool_name(param)       # one line only

def main() -> None:
    mcp.run()
```

**The rule for what goes where:**

Any line that touches domain data (files, databases, APIs, format-specific libraries)
belongs in `engine.py`. Any line that touches the MCP protocol belongs in `server.py`.
If a function body in `server.py` is more than two lines (the `return engine.call()`
plus maybe one argument-prep line), it has logic that belongs in `engine.py`.

### Why this split matters

1. **Testability** — `pytest` tests import and call `engine.py` directly without
   starting an MCP server process. Tests are fast, simple, and don't require MCP
   client infrastructure.

2. **Debuggability** — when a tool fails, you can reproduce the failure in a Python
   REPL by importing `engine.py` and calling the function with the same arguments.
   No MCP overhead in the debug loop.

3. **Reusability** — if you build a CLI tool or a web API on top of the same domain
   logic, you import `engine.py`, not `server.py`.

4. **Clarity** — a reviewer reading `engine.py` sees only domain logic. A reviewer
   reading `server.py` sees only tool definitions. The concerns are cleanly separated.

---

## 12. Return value contract

### Every tool returns a dict

No exceptions. Never return:
- A plain string: `"Done."` `"Success."` `"Error: file not found."`
- A list directly: `[item1, item2, item3]`
- `None`
- A boolean: `True` or `False`

Always return a dict:
```python
{"success": True, "op": "replace_text", ...}
{"success": False, "error": "...", "hint": "..."}
```

### Required fields in every response

| Field | Type | When required | Purpose |
|---|---|---|---|
| `"success"` | `bool` | Always | Model checks this first |
| `"op"` | `str` | On success | Confirms which operation ran |
| `"error"` | `str` | On failure | Human-readable failure reason |
| `"hint"` | `str` | On failure | Actionable recovery instruction |
| `"backup"` | `str` | After any write | Path to snapshot taken before write |
| `"token_estimate"` | `int` | Always | `len(str(response)) // 4` |
| `"truncated"` | `bool` | On bounded reads | Always explicit, never absent |

### What to include in write confirmations

When a write operation succeeds, return enough information for the model to verify
the change without needing to make an additional read call:

```python
# Good — model can verify without a follow-up read
{
    "success": True,
    "op": "replace_text",
    "match": "30 days",
    "new_text": "45 days",
    "replaced_in": [{"paragraph_index": 47, "context": "Payment is due within 45 days"}],
    "backup": ".mcp_versions/contract_2026-03-25T14-30-00Z.bak",
    "token_estimate": 42
}

# Bad — model must make another read call to confirm
{
    "success": True,
    "message": "Text replaced successfully."
}
```

### What to never include in write confirmations

Never return the full document/file content after a write. If the model wants to see
the document state after editing, it calls a read tool. Write tools confirm the write;
read tools read. They are separate concerns.

---

## 13. Error handling contract

### Never raise exceptions to the caller

All exceptions are caught in `engine.py` and converted to error dicts. The MCP layer
never sees a Python exception from domain logic — only success or failure dicts.

```python
def replace_text(file_path: str, match: str, new_text: str) -> dict:
    path = resolve_path(file_path)
    backup = None
    try:
        backup = snapshot(str(path))
        # ... do work ...
        return {"success": True, ...}
    except FileNotFoundError:
        return {
            "success": False,
            "error": f"File not found: {file_path}",
            "hint": "Check that file_path is absolute and the file exists.",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "backup": backup,
            "hint": "Use restore_version to undo if a snapshot was taken.",
        }
```

### Standard error messages

Use consistent error message phrasing across all tools. The model learns from
repeated exposure to the same error patterns. Inconsistent messages require more
context to interpret.

```python
# File errors
f"File not found: {path}"
f"Expected .docx file, got .{ext}"
f"File is locked by another process: {path}"

# Index/address errors
f"Index {n} out of range (0–{max_val})"
f"Invalid cell address: {addr}"
f"Sheet '{name}' not found"
f"Column '{name}' not found"

# Content errors
f"Match text not found: '{match}'"
f"Record ID {id} not found"
f"Template variable '{var}' not found in document"

# Validation errors
f"Unknown op: '{op_name}'. Allowed: {', '.join(allowed_ops)}"
f"Required field missing: '{field}'"
f"Value '{value}' not in allowed values: {', '.join(allowed)}"
```

### The hint field — rules for writing actionable hints

The `"hint"` field is what allows a local 9B model to self-correct without human
intervention. Bad hints make the model repeat the same mistake. Good hints give a
specific next action.

```python
# Bad hints
"hint": "Invalid input."
"hint": "Try again."
"hint": "Check the parameters."

# Good hints
"hint": "Use read_document() to get current paragraph count before using paragraph_index."
"hint": "Sheet names are case-sensitive. Use list_sheets() to see available names."
"hint": "Cell address must use Excel notation like B5 or C12."
"hint": "Allowed ops for this server: replace_text, insert_paragraph, delete_paragraph"
```

The hint should complete the sentence "To fix this, ..." and should name a specific
tool to call or a specific value to check.

---

## 14. State and version control

### The snapshot rule

**Every tool that modifies persistent data must snapshot before writing.**

This is non-negotiable. It applies to:
- Files on disk (documents, spreadsheets, databases)
- Database records (include a `before_state` in the response)
- Configuration files
- Any data that cannot be trivially regenerated

If your domain cannot support snapshots (e.g., you are calling an external API that
has no undo), document this limitation clearly and make the write tool require an
explicit `confirm: bool = False` parameter that defaults to False, forcing the model
to explicitly pass `confirm=True` before any destructive write.

### Snapshot implementation

```python
# shared/version_control.py pattern
from pathlib import Path
from datetime import datetime, timezone
import shutil

def snapshot(file_path: str) -> str:
    """
    Copy file to .mcp_versions/{name}_{timestamp}.bak
    Returns the backup path string.
    Raises FileNotFoundError if source does not exist.
    """
    source = Path(file_path).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Cannot snapshot: {source}")

    versions_dir = source.parent / ".mcp_versions"
    versions_dir.mkdir(exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    backup = versions_dir / f"{source.stem}_{ts}{source.suffix}.bak"
    shutil.copy2(source, backup)
    return str(backup)
```

### The companion state file pattern

For complex structured files (spreadsheets, databases, configuration), maintain a
companion JSON state file alongside the working file:

```
budget_q3.xlsx
budget_q3.xlsx.mcp_state.json   ← companion
```

The state file tracks the current known values of key nodes, the patch history, and
the last modification timestamp. The model reads the state file instead of parsing
the full binary file to understand current state:

```json
{
    "version": 4,
    "file": "budget_q3.xlsx",
    "last_modified": "2026-03-25T14:30:00Z",
    "known_state": {
        "Q3 Revenue.B5": {"value": 142500, "formula": null},
        "Q3 Revenue.D5": {"formula": "=SUM(B5:C5)*1.1"}
    },
    "patches": [
        {"version": 1, "ts": "2026-03-25T10:00Z", "ops": 3},
        {"version": 2, "ts": "2026-03-25T14:30Z", "ops": 1}
    ]
}
```

### Restore tool — mandatory in tier 1

Every tier 1 server must include a `restore_version` tool:

```python
@mcp.tool()
def restore_version(file_path: str, timestamp: str) -> dict:
    """Restore file to a previous snapshot by timestamp."""
    return engine.restore_version(file_path, timestamp)
```

This is the undo button. Without it, every mistake is permanent on the user's machine.

---

## 15. Token budget discipline

### The VRAM → context window → token budget chain

```
GPU VRAM
  └→ Model weights occupy most of VRAM
       └→ Remaining VRAM = KV cache
            └→ KV cache size = effective context window in tokens
                 └→ Token budget per tool call = context / expected_turns
```

On an 8GB GPU with a 9B model in Q4_K_M quantization:
- Model weights: ~5.5 GB
- Available KV cache: ~1.7 GB
- Effective context: ~10,000-12,000 tokens

Across a 10-turn agentic loop, that is ~1,000 tokens per turn maximum — including
the tool schema overhead (~700 tokens for 8 tools), system prompt (~200 tokens),
and the turn's conversation. The actual per-tool content budget is approximately
**100-300 tokens per turn** on an 8GB machine.

### Budget rules

1. **Tool schemas (set once per session):** keep under 700 tokens total (≤8 tools,
   ≤80 char docstrings, ≤4 params each)

2. **Per-tool response (set per call):** keep under 500 tokens for read tools,
   under 150 tokens for write confirmations

3. **Accumulated history:** the model's full conversation history stays in KV cache.
   After 10 turns, the accumulated tokens approach the limit. Design for short focused
   sessions — one task, then fresh session.

4. **The `token_estimate` field** in every response lets the model track its own
   budget consumption. Include it. The model will use it.

### The 8GB mode flag

Every server reads the `OFFICE_MCP_8GB_MODE` environment variable and reduces all
return size limits when it is set:

```python
# shared/platform_utils.py
import os

def is_8gb_mode() -> bool:
    return os.environ.get("OFFICE_MCP_8GB_MODE", "0") == "1"

def get_max_items() -> int:
    """Max items to return in a list or search result."""
    return 10 if is_8gb_mode() else 50

def get_max_depth() -> int:
    """Max nesting depth for returned JSON structures."""
    return 3 if is_8gb_mode() else 5
```

The installer sets `OFFICE_MCP_8GB_MODE=1` automatically when it detects ≤8GB VRAM.
Never hardcode limits in engine functions — always call these helpers.

---

## 16. VRAM tiers and hardware constraints

### Design for 8GB — test on 16GB — document for 24GB

The project must work on 8GB. It should work well on 16GB. On 24GB it should be
excellent. Write code for 8GB constraints and let users with more hardware benefit
automatically through the absence of artificial limits.

### Model recommendation table

Document this in your README so users choose the right model before installing:

| VRAM | Model family | Quant | Context | Max tools |
|---|---|---|---|---|
| 4 GB | 3-4B models | Q4_K_M | ~5K tokens | 5 |
| 6 GB | 7B models | Q4_K_M | ~7K tokens | 6 |
| 8 GB | 9B models | Q3_K_S | ~12K tokens | 8 |
| 12 GB | 9B models | Q8_0 | ~20K tokens | 10 |
| 16 GB | 14B models | Q4_K_M | ~24K tokens | 12 |
| 24 GB | 32B models | Q4_K_M | ~32K tokens | 15 |

### The honest statement to include in README

Include this exact paragraph in every MCP server README:

> **A note on local LLMs and context limits:**
> MCP tool schemas consume real context window tokens on every turn. On 8GB VRAM with
> a 9B model, your effective context is approximately 10,000-12,000 tokens — not the
> 32K the model theoretically supports. This server is designed to stay within that
> budget through surgical read tools that fetch only what is needed. For best results,
> run one focused task per session, then start a fresh chat. Loading fewer tools
> means more context for your actual work.

---

## 17. Testing standards

### The test-engine-not-server rule

Tests import and call `engine.py` functions directly. Never spin up an MCP server
process in a test. The MCP layer is thin wrapper — test the domain logic, not the
protocol.

```python
# Correct
from servers.docx_basic.engine import replace_text, search_paragraphs

def test_replace_text(tmp_path, contract_fixture):
    doc = tmp_path / "contract.docx"
    shutil.copy(contract_fixture, doc)
    result = replace_text(str(doc), "PARTY_A", "Acme Corp")
    assert result["success"] is True
    assert result["replaced_in"][0]["new_text"] == "Acme Corp"

# Wrong
def test_replace_text():
    subprocess.run(["uv", "run", "docx-basic", "--transport", "stdio"])
    # ... MCP client setup ...
    # This is testing MCP infrastructure, not your logic
```

### Real fixture files — never generated

Test fixtures must be real files created by the actual application (Word, Excel,
PowerPoint). Never use files generated programmatically as primary fixtures.

The reason: bugs in format-specific operations (run-level editing, formula
evaluation, style application) only appear in real documents with real formatting
history. A programmatically-generated clean document hides the edge cases.

Required fixture categories:
- `simple` — plain content, minimal formatting, no edge cases
- `complex` — mixed formatting, embedded objects, tracked changes, tables
- `large` — >50 pages / >500 rows to test truncation and performance

### What to test for every write operation

1. **Success** — operation completes, return dict has `"success": True`
2. **Content correct** — read back the written node, verify content matches
3. **Snapshot created** — `.mcp_versions/` directory has a new `.bak` file
4. **Backup in response** — `"backup"` key present in return dict
5. **Formatting preserved** — for rich-format files, verify style/bold/font unchanged
6. **Wrong file type** — passing `.xlsx` to a DOCX tool returns error dict
7. **File not found** — missing file returns error dict with correct hint
8. **Index out of range** — bad index returns error dict with total count hint

### Coverage requirements

| Module | Minimum coverage |
|---|---|
| `shared/` | 100% |
| `engine.py` | ≥ 90% |
| Error paths | All documented error conditions tested |
| Happy paths | All tools tested |

### CI must run on all three platforms

```yaml
strategy:
  matrix:
    os: [ubuntu-22.04, windows-latest, macos-13]
```

A test that passes on Linux but fails on Windows is a bug. Path separator assumptions
are the most common cause. Fix with `pathlib.Path`.

---

## 18. Cross-platform compatibility

### The path rule — pathlib everywhere

Never use string concatenation or `os.path.join()` for paths. Always use
`pathlib.Path`. This is the single most impactful cross-platform rule.

```python
# Wrong on Windows — / separator
path = base_dir + "/" + filename

# Wrong — hides platform issues
path = os.path.join(base_dir, filename)

# Correct — works everywhere
path = Path(base_dir) / filename
```

### Line endings — enforce in .gitattributes

```
# .gitattributes
* text=auto eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf
```

All files use LF. Windows batch files use CRLF (CMD requires it).

### Shell scripts — POSIX sh, not bash

`install.sh` must use `#!/bin/sh` and POSIX-compatible syntax. macOS ships bash 3.x
under GPL restrictions. Ubuntu uses dash for `/bin/sh`. Using bash-specific syntax
breaks on both.

```sh
#!/bin/sh
# Correct POSIX
if [ "$var" = "value" ]; then echo "yes"; fi
command -v uv > /dev/null 2>&1 && echo "found"

# Wrong — bash only
if [[ "$var" == "value" ]]; then echo "yes"; fi
uv 2>/dev/null && echo "found"   # &> is bash only
```

### stdout is the MCP protocol channel

Never write to stdout in any engine or server module. LM Studio and Claude Desktop
use stdout for MCP JSON-RPC communication. Any `print()` statement in server code
corrupts the channel and breaks the connection.

```python
# Wrong — breaks MCP on stdio transport
print("Processing file...")
print(f"Found {count} paragraphs")

# Correct — logs go to stderr only
import logging
logger = logging.getLogger(__name__)
logger.debug("Processing file...")   # goes to stderr, not stdout
```

Configure logging to stderr in `server.py`:
```python
import sys, logging
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
```

### Windows-specific concerns

**Long paths:** Windows has a 260-character MAX_PATH limit by default. If your server
handles files in deeply-nested directories, use the `\\\\?\\` prefix on Windows:
```python
if sys.platform == "win32" and len(str(path)) > 200:
    path = Path("\\\\?\\" + str(path.resolve()))
```

Enable long paths in `install.bat`:
```bat
reg add "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled /t REG_DWORD /d 1 /f
```

**File locking:** Windows locks open files more aggressively than Unix. When writing
to a file that might be open in another application, use a temp-file-then-rename
pattern for atomic writes:
```python
import tempfile, shutil
with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=path.parent) as tmp:
    # write to tmp
    tmp_path = tmp.name
shutil.move(tmp_path, path)  # atomic on same filesystem
```

---

## 19. Multi-platform AI client compatibility

### Every server supports two transport modes

**stdio** (default) — for local AI clients (LM Studio, Claude Desktop, Cursor,
Windsurf, Cline):
```bash
uv run --directory servers/my_server my-server
```

**HTTP** (for cloud AI platforms with remote tool access — ChatGPT, Gemini):
```bash
uv run --directory servers/my_server my-server --transport http --port 8765 --auth-token <token>
```

Add this to every `server.py`:
```python
import argparse

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--auth-token", type=str, default=None)
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="streamable-http", host="127.0.0.1",
                port=args.port, path="/mcp")
    else:
        mcp.run()
```

### Config file locations by platform

The `mcp_config_writer.py` in `install/` writes to the correct config file for
each AI client platform:

| Platform | Config file (macOS) | Config file (Windows) |
|---|---|---|
| LM Studio | `~/Library/Application Support/LM Studio/mcp.json` | `%APPDATA%\LM Studio\mcp.json` |
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` | `%APPDATA%\Claude\claude_desktop_config.json` |
| Cursor | `~/.cursor/mcp.json` | `~/.cursor/mcp.json` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | `~/.codeium/windsurf/mcp_config.json` |
| Cline | `~/Library/Application Support/Code/User/settings.json` | `%APPDATA%\Code\User\settings.json` |

The JSON structure differs slightly by platform. LM Studio, Claude Desktop, and
Cursor use `"mcpServers": {}`. Cline uses `"cline.mcpServers": {}`. The config writer
handles these differences — server code is identical regardless of client.

### Installer platform selection menu

```
Which AI platform do you use?
  1) LM Studio (recommended for local LLMs)
  2) Claude Desktop
  3) Cursor
  4) Windsurf
  5) Cline (VS Code)
  6) Multiple — write all detected configs

Enter number: _
```

---

## 20. Transport modes — stdio and HTTP

### stdio — default for local use

The MCP server communicates via stdin/stdout JSON-RPC. LM Studio starts the server
as a child process and communicates through its stdio pipes.

Key rules for stdio mode:
- **Never write to stdout** — only the MCP framework writes to stdout
- **Always write logs to stderr** — `logging.basicConfig(stream=sys.stderr)`
- **No interactive prompts** — the server is headless
- **Fast startup** — the client may kill and restart the server between sessions

### HTTP / Streamable HTTP — for remote use

When `--transport http` is specified, the server listens on `http://localhost:{port}/mcp`.
For security, always require an auth token in HTTP mode:

```python
# Reject requests without valid auth token
if args.auth_token:
    # FastMCP handles token validation via headers
    mcp.run(transport="streamable-http", auth_token=args.auth_token, ...)
```

The auth token should be:
- Generated by the installer and stored in the config
- Never hardcoded in source
- At least 32 random hex characters
- Changed by the user via `--auth-token <new-token>` if compromised

### SSE transport — legacy fallback

Some older MCP clients support only Server-Sent Events transport, not Streamable HTTP.
FastMCP supports both. If a user reports connection errors in HTTP mode, document
the SSE fallback:
```bash
uv run ... my-server --transport sse --port 8765
```

---

## 21. Installation and distribution

### The install experience standard

A user who has never used a terminal must be able to install and use your MCP server.
The standard is:

1. Download the repo (as a zip from GitHub, or via `git clone`)
2. Double-click `install.bat` (Windows) or run `./install.sh` (macOS/Linux)
3. Answer one menu question (which AI platform)
4. Restart their AI client
5. Start using the tools

If any step requires manual JSON editing, terminal commands, or developer knowledge,
the install experience is failing the standard.

### install.sh checklist

```sh
#!/bin/sh

# 1. Check Python 3.11+
python_version=$(python3 --version 2>&1 | cut -d' ' -f2)
# compare version, print URL and exit 1 if too old

# 2. Check/install uv
if ! command -v uv > /dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# 3. Install all dependencies
uv sync

# 4. Ask which platforms
# ... menu ...

# 5. Write mcp config
python3 install/mcp_config_writer.py --servers "$selected" --platform "$platform"

# 6. Confirm
echo "Done. Restart your AI client to activate the tools."
```

### mcp_config_writer.py rules

- Parse existing config with `json5` — handles comments and trailing commas
- Append-only — never modify or remove existing entries
- Skip servers already registered (idempotent — safe to run twice)
- Write with `json.dumps()` — output is strict valid JSON
- Use atomic write (temp file + rename) — never corrupt config on partial write
- Print which servers were added, which were skipped (already registered)

### GitHub release artifacts

For every version tag, build and attach release archives:
- `{project}-windows-x64.zip` — repo + install.bat + pre-downloaded wheels
- `{project}-macos.tar.gz` — repo + install.sh + pre-downloaded wheels
- `{project}-linux.tar.gz` — repo + install.sh + pre-downloaded wheels

Pre-bundling wheels means the user does not need internet access after downloading.
Use `uv export --frozen > requirements.txt` and `pip download` to collect wheels.

---

## 22. Naming conventions

### Files and directories

```
servers/{domain}_{tier}/    — server directories (docx_basic, xlsx_charts)
shared/                     — shared utilities
tests/                      — all tests in one flat directory
install/                    — installer scripts
```

### Python identifiers

```python
# Functions — snake_case verb
read_document()
apply_patch()
search_paragraphs()

# Classes — PascalCase
PatchValidator
VersionControl

# Constants — UPPER_SNAKE_CASE
MAX_SEARCH_RESULTS = 50
DEFAULT_TIMEOUT = 30

# Private helpers — leading underscore
_apply_single_op()
_parse_address()
```

### MCP tool function names

Tool names follow the pattern `verb_noun`:
```python
read_document    list_sheets      search_records
set_cell         add_row          delete_paragraph
replace_text     insert_after     restore_version
```

Allowed verbs: `read`, `list`, `search`, `get`, `set`, `add`, `insert`, `delete`,
`replace`, `restore`, `export`, `apply`

Do not use: `fetch` (ambiguous), `query` (SQL-specific), `pull` (Git-specific),
`push` (Git-specific), `run` (too general), `process` (vague)

### Commit message format

```
{type}({scope}): {description}

Types:   feat | fix | test | docs | refactor | chore
Scope:   server name, shared, install, or root

feat(docx_basic): add surgical paragraph search tool
fix(shared): handle Windows long path in snapshot
test(xlsx_basic): add formula injection edge cases
docs(readme): add VRAM budget guidance
```

---

## 23. Dependency policy

### License requirements

Only libraries with these licenses are permitted:
- MIT
- Apache 2.0
- BSD 2-Clause or 3-Clause
- ISC
- Python Software Foundation License

**Not permitted:**
- GPL / LGPL — copyleft infects the project
- Commercial / proprietary — not open source
- No license — legally unsafe

### Dependency vetting checklist

Before adding any new library:
- [ ] License is in the approved list above
- [ ] Last release within 12 months (not abandoned)
- [ ] No known CVEs via `uv audit`
- [ ] Does not pull in a large dependency tree unnecessarily
- [ ] Alternative using an already-approved library does not exist
- [ ] Documented in `pyproject.toml` with minimum version constraint (`>=x.y.z`)
- [ ] Added to STANDARDS.md approved table

### Prohibited libraries (Python)

```
win32com / pywin32     — Windows only
Spire.Doc              — commercial license
Aspose.*               — commercial license
pandas                 — too heavy; use openpyxl directly
LibreOffice UNO API    — too complex a dependency; use subprocess instead
```

---

## 24. CI/CD requirements

### Required CI checks on every PR

```yaml
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-22.04, windows-latest, macos-13]
    steps:
      - uv sync --frozen
      - uv run ruff check .
      - uv run ruff format --check .
      - uv run pyright servers/ shared/
      - uv run pytest tests/ --cov=servers --cov=shared --cov-fail-under=90
      - python verify_tool_docstrings.py   # fails if any docstring > 80 chars
```

### verify_tool_docstrings.py

This script is part of every project. It enforces the 80-character docstring rule:

```python
import ast
import pathlib
import sys

errors = []
for f in pathlib.Path("servers").rglob("server.py"):
    tree = ast.parse(f.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            has_tool_decorator = any(
                (isinstance(d, ast.Attribute) and d.attr == "tool") or
                (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "tool")
                for d in node.decorator_list
            )
            if has_tool_decorator:
                docstring = ast.get_docstring(node) or ""
                if len(docstring) > 80:
                    errors.append(f"{f}:{node.lineno} {node.name}: {len(docstring)} chars > 80")

if errors:
    print("\n".join(errors))
    sys.exit(1)
```

### Required CI environment variables

```yaml
env:
  OFFICE_MCP_8GB_MODE: "1"   # run CI in 8GB mode to catch limit violations
```

Running CI with `OFFICE_MCP_8GB_MODE=1` ensures that tests validate the stricter
8GB return size limits, catching tools that would fail on consumer hardware.

---

## 25. Documentation requirements

### README.md required sections

Every MCP server project must have these sections in `README.md`:

1. **One-line description** — what domain, what tier, how many tools
2. **Prerequisites** — Python version, uv, any OS-specific requirements
3. **Quick install** — three commands or fewer to get running
4. **Platform setup** — per-platform screenshots or JSON snippets for LM Studio,
   Claude Desktop, Cursor (the three most common)
5. **Tool reference** — table of tools with name, description, key parameters
6. **Recommended usage patterns** — 2-3 example prompts showing the four-tool loop
7. **Hardware requirements** — VRAM table with model recommendations
8. **The VRAM honesty paragraph** — see section 16 for exact wording
9. **Contributing** — how to add tools, link to STANDARDS.md
10. **License**

### CLAUDE.md — required in every repo

Every repository that an AI coding agent will work in must have a `CLAUDE.md`.
This file is the authoritative instruction set for the AI. It must include:

- Project overview and goals
- Repository structure
- Architecture principles (at minimum: engine/server split, tool count limits,
  surgical read protocol, snapshot-before-write)
- Tool design rules specific to this domain
- What the AI must never do (the prohibitions list)
- The progress tracker with checkboxes

CLAUDE.md is not documentation for humans. It is a machine-readable instruction
set optimised for AI coding agents. Write it accordingly — prescriptive, numbered,
checkboxes, explicit prohibitions.

### In-code documentation

```python
# Tool docstrings — ≤ 80 chars, machine-readable
"""Find paragraphs matching query. Returns indices only."""

# Engine function docstrings — full human-readable explanation
def replace_text(file_path: str, match: str, new_text: str) -> dict:
    """
    Replace the first occurrence of match_text in the document with new_text.
    Uses run-level editing to preserve all character formatting.
    Snapshots the file before writing.

    Returns:
        dict with "success", "replaced_in" (list of paragraph indices),
        "backup" (snapshot path), "token_estimate"
    Raises:
        Never — all exceptions are caught and returned as error dicts
    """
```

---

## 26. What to never do

These are absolute prohibitions. Any code that violates them is a defect.

### Never

1. **Print to stdout in any server or engine module.**
   Stdout is the MCP JSON-RPC channel. Any print statement corrupts it.
   All logging goes to stderr.

2. **Return a plain string from a tool function.**
   Always return a dict. The model depends on structured responses.

3. **Write to a file without calling `snapshot()` first.**
   No exceptions for "small changes" or "non-destructive edits".

4. **Swallow exceptions silently.**
   Every exception must either be re-raised or converted to an error dict with
   `"success": False`, `"error"`, and `"hint"`.

5. **Return the entire file content from a write tool.**
   Write tools confirm the write. Read tools read. They are separate.

6. **Return all records/rows/paragraphs from a search that finds zero matches.**
   Return an empty list and a helpful hint. Never fall back to "here's everything".

7. **Exceed 10 tools in a single server.**
   Split into multiple servers before exceeding this limit.

8. **Put business logic in server.py.**
   Tool functions in server.py are one-liners that call engine.py.

9. **Use `paragraph.text = value` to edit a Word document.**
   (Or equivalent "full node replacement" in any rich-format library.)
   This destroys formatting. Always edit at the run/cell/shape level.

10. **Hardcode token or size limits as magic numbers in engine functions.**
    Always call `get_max_items()`, `get_max_depth()` from `platform_utils.py`.
    This allows the 8GB mode flag to work.

11. **Use string concatenation for file paths.**
    Always use `pathlib.Path / operator`.

12. **Write a tool that both reads and writes in a single call.**
    LOCATE and INSPECT are separate from PATCH. Keep them separate.

13. **Add a dependency without checking its license.**
    GPL dependencies are never permitted.

14. **Make the installer require terminal commands from the user.**
    The install experience standard requires zero terminal interaction.

---

## 27. Checklist — new server from scratch

Use this checklist every time you create a new MCP server. Do not skip steps.

### Discovery

- [ ] Define the domain clearly — what real-world task does this server support?
- [ ] Define the tier — Basic / Medium / Advanced (one tier per server)
- [ ] List all tools — count them before writing any code
- [ ] Confirm tool count ≤ 10 (target 6-8)
- [ ] Identify the surgical read tools — `search_*`, `get_*_index`, `list_*`
- [ ] Identify the write tools — confirm each has a snapshot before write
- [ ] Choose language based on library availability, not preference
- [ ] Confirm all required libraries have approved licenses

### Setup

- [ ] Create server directory: `servers/{domain}_{tier}/`
- [ ] Create `__init__.py` (empty)
- [ ] Create `pyproject.toml` with `shared` dependency
- [ ] Add to workspace `pyproject.toml` members list
- [ ] Run `uv sync` — no errors

### Shared module

- [ ] `shared/version_control.py` exists and is tested
- [ ] `shared/patch_validator.py` exists and is tested
- [ ] `shared/file_utils.py` exists and is tested
- [ ] `shared/platform_utils.py` exists with `is_8gb_mode()` and limit helpers

### Engine

- [ ] Create `engine.py` with zero MCP imports
- [ ] Implement all tools in `engine.py` first
- [ ] Surgical read tools implemented first (LOCATE and INSPECT before PATCH)
- [ ] Every tool returns a dict with `"success"` as first key
- [ ] Every write tool calls `snapshot()` before writing
- [ ] Every write tool includes `"backup"` in return dict
- [ ] Every tool response includes `"token_estimate"`
- [ ] Bounded reads use `get_max_*()` from `platform_utils`, never hardcoded
- [ ] No `print()` statements
- [ ] `restore_version` tool delegates to `shared.version_control.restore()`

### Server

- [ ] Create `server.py` with FastMCP setup
- [ ] One `@mcp.tool()` per tool, each body is `return engine.func(params)`
- [ ] Every docstring ≤ 80 characters
- [ ] All parameters typed with allowed types only
- [ ] `--transport` and `--port` CLI args in `main()`
- [ ] `project.scripts` entry in `pyproject.toml`

### Tests

- [ ] Create `tests/fixtures/` with real files (simple + complex)
- [ ] Create `tests/test_{server_name}.py`
- [ ] Test every tool: success case
- [ ] Test every tool: file-not-found error case
- [ ] Test every write tool: snapshot was created
- [ ] Test every write tool: `"backup"` in return dict
- [ ] Test every bounded read: truncation at limit
- [ ] Test `restore_version`: file reverts correctly
- [ ] `uv run pytest` — all pass
- [ ] `uv run pyright servers/{name}/` — no errors
- [ ] `uv run ruff check servers/{name}/` — no errors
- [ ] Run on all three platforms if CI is not yet set up

### Distribution

- [ ] Add server to `install/install.sh` menu
- [ ] Add server to `install/install.bat` menu
- [ ] Add server to `install/mcp_config_writer.py` registry
- [ ] Test install on clean machine (or VM)
- [ ] Document mcp.json snippet in README

### Review

- [ ] Run `verify_tool_docstrings.py` — all ≤ 80 chars
- [ ] Manual test in LM Studio with Qwen 3.5 9B — four-tool loop works
- [ ] Manual test in Claude Desktop — tools appear and execute
- [ ] Token budget test: run 10-step task, confirm context window not exceeded
- [ ] Update CLAUDE.md progress tracker

---

## 28. Checklist — new tool in existing server

- [ ] Confirm server tool count will not exceed 10 after adding this tool
- [ ] Confirm tool name follows `verb_noun` snake_case convention
- [ ] Confirm verb is in the approved verb list
- [ ] Write engine function in `engine.py` first — no MCP imports
- [ ] Engine function returns dict with `"success"` as first key
- [ ] Engine function calls `snapshot()` if it writes anything
- [ ] Engine function includes `"backup"` in return dict on writes
- [ ] Engine function includes `"token_estimate"` in return dict
- [ ] Engine function catches all exceptions and returns error dict
- [ ] Error dict includes `"hint"` with actionable recovery instruction
- [ ] Engine function calls `get_max_*()` helpers for any bounded return
- [ ] No `print()` statements
- [ ] Add `@mcp.tool()` decorator in `server.py` calling engine function
- [ ] Tool docstring is ≤ 80 characters
- [ ] All parameters have type annotations using allowed types only
- [ ] Optional parameters have primitive defaults
- [ ] Add success test in `tests/test_{server_name}.py`
- [ ] Add file-not-found failure test
- [ ] Add snapshot-created test (if write tool)
- [ ] Run `uv run pytest tests/test_{server_name}.py` — all pass
- [ ] Run `uv run ruff check servers/{name}/`
- [ ] Run `uv run pyright servers/{name}/`
- [ ] Run `verify_tool_docstrings.py` — ≤ 80 chars confirmed

---

*Version: 1.0*
*Derived from: office-mcp architecture decisions, 2026-03-25*
*This document should be linked from every MCP server project's README and CLAUDE.md.*
*When these standards conflict with a specific project's CLAUDE.md, the project's
CLAUDE.md takes precedence for that project. These are the defaults.*
