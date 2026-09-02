# MCP Microsoft Office

A self-hosted MCP server that gives local LLMs full control over Word, Excel, and PowerPoint files. No cloud APIs, no API keys — everything runs on your machine and writes directly to your files.

**Release [`v0.1.2`](https://github.com/azzindani/MCP_Microsoft_Office/releases/tag/v0.1.2)** — source only. No wheel and no container image are published: install from the tag with the bundled installer, or build the image yourself from the `Dockerfile` in this repo.

## Features

- **98 tools** across 11 servers — Word, Excel, PowerPoint read, edit, and create
- **Create new documents** — blank or structured, from text, sections, templates, or outlines
- **Auto-open** — every creation and export tool opens the file in its native app automatically
- **Batch generation** — one template + a list of data → N output files (offer letters, invoices, proposals)
- **Fill formula down** — the drag-down equivalent: write a formula once, fill it across 1000 rows
- **Doc → Presentation** — convert a Word outline into a PowerPoint draft in one tool call
- **LOCATE → INSPECT → PATCH → VERIFY** workflow for surgical document edits
- **Automatic version control** — every write is snapshotted and fully restorable
- **Operation receipt logging** — full audit trail of all modifications per file
- **Constrained mode** — reduces response sizes for low-memory machines (CPU or GPU)
- **Works with any local model** — Qwen, Llama, Mistral, Phi — any model that supports tool calling
- **Zero cloud dependency** — no OneDrive, no Microsoft 365 subscription required

## Important: File Path Only

> **Do not attach files via the LM Studio attachment button.**
>
> LM Studio will RAG-chunk any attached file and send fragments to the model — the MCP tools will never see the actual document. This MCP works exclusively through **absolute file paths**.
>
> Always tell the model where the file lives on disk:
> ```
> Edit C:\Users\you\documents\report.docx
> ```
> The model will pass that path directly to the MCP tools. Attachment-based workflows are not supported and will silently produce wrong results.

## Quick Install (LM Studio)

> **Tested on Windows 11** with LM Studio 0.4.x and uv 0.5+.

### Requirements

- **Git** — `git --version`
- **uv** — `uv --version` ([install guide](https://docs.astral.sh/uv/getting-started/installation/))
- **Python 3.14 or higher** — `python --version`
- **LM Studio** with a model that supports tool calling (Gemma 4, Qwen 3.5, etc.)
- **Microsoft Office** installed is optional — only required for PDF export (`export_pdf`)

### Platform Support

| Platform | Status |
|---|---|
| Windows | Tested — real-world verified (Windows 11) |
| macOS | Untested — CI/CD pipeline passes |
| Linux | Untested — CI/CD pipeline passes |

> Real-world usage has only been verified on Windows. macOS and Linux are supported by design and pass the automated CI pipeline, but have not been tested by hand. Reports from non-Windows users are welcome.

### First Run

The first launch clones the repo and installs all dependencies (~2–5 minutes). Subsequent launches are instant.

> **Pre-install recommended:** To avoid the 60-second LM Studio connection timeout on first launch, run this once in PowerShell before connecting:
> ```powershell
> $d = Join-Path $env:USERPROFILE '.mcp_servers\MCP_Microsoft_Office'
> $g = Join-Path $d '.git'
> if (!(Test-Path $g)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d }; git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d --quiet }
> Set-Location $d; uv sync --all-packages
> ```
> If you skip this step and LM Studio times out, press **Restart** in the MCP Servers panel — it will reconnect and complete the install immediately.

### Steps

1. Open LM Studio → **Developer** tab (`</>` icon) or you can find via **Integrations**
2. Find **mcp.json** or **Edit mcp.json** → click to open
3. Paste the config for the servers you want (see combinations below)
4. Wait for the blue dot next to each server
5. Start chatting — the model will see all tools

### Recommended starting config — Word + Create

```json
{
  "mcpServers": {
    "docx_basic": {
      "command": "powershell",
      "args": [
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; $g = Join-Path $d '.git'; if (!(Test-Path $g)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d }; git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d --quiet } else { Set-Location $d; git fetch origin --quiet; git reset --hard FETCH_HEAD --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\docx_basic') docx-basic"
      ],
      "env": { "MCP_CONSTRAINED_MODE": "0" },
      "timeout": 600000
    },
    "docx_new": {
      "command": "powershell",
      "args": [
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; Set-Location $d; uv run --directory (Join-Path $d 'servers\\docx_new') docx-new"
      ],
      "env": { "MCP_CONSTRAINED_MODE": "0" },
      "timeout": 600000
    }
  }
}
```

### All Servers — Complete mcp.json

Copy-paste this to register all 11 servers at once. Every server entry is self-sufficient — each one clones the repo if missing, pulls the latest updates, installs dependencies, and runs.

```json
{
  "mcpServers": {
    "docx_basic": {
      "command": "powershell",
      "args": [
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; $g = Join-Path $d '.git'; if (!(Test-Path $g)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d }; git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d --quiet } else { Set-Location $d; git fetch origin --quiet; git reset --hard FETCH_HEAD --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\docx_basic') docx-basic"
      ],
      "env": { "MCP_CONSTRAINED_MODE": "0" },
      "timeout": 600000
    },
    "docx_tables": {
      "command": "powershell",
      "args": [
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; if (!(Test-Path $d)) { git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d } else { Set-Location $d; git pull --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\docx_tables') docx-tables"
      ],
      "env": { "MCP_CONSTRAINED_MODE": "0" },
      "timeout": 600000
    },
    "docx_layout": {
      "command": "powershell",
      "args": [
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; if (!(Test-Path $d)) { git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d } else { Set-Location $d; git pull --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\docx_layout') docx-layout"
      ],
      "env": { "MCP_CONSTRAINED_MODE": "0" },
      "timeout": 600000
    },
    "docx_new": {
      "command": "powershell",
      "args": [
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; if (!(Test-Path $d)) { git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d } else { Set-Location $d; git pull --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\docx_new') docx-new"
      ],
      "env": { "MCP_CONSTRAINED_MODE": "0" },
      "timeout": 600000
    },
    "xlsx_basic": {
      "command": "powershell",
      "args": [
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; if (!(Test-Path $d)) { git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d } else { Set-Location $d; git pull --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\xlsx_basic') xlsx-basic"
      ],
      "env": { "MCP_CONSTRAINED_MODE": "0" },
      "timeout": 600000
    },
    "xlsx_formulas": {
      "command": "powershell",
      "args": [
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; if (!(Test-Path $d)) { git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d } else { Set-Location $d; git pull --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\xlsx_formulas') xlsx-formulas"
      ],
      "env": { "MCP_CONSTRAINED_MODE": "0" },
      "timeout": 600000
    },
    "xlsx_charts": {
      "command": "powershell",
      "args": [
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; if (!(Test-Path $d)) { git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d } else { Set-Location $d; git pull --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\xlsx_charts') xlsx-charts"
      ],
      "env": { "MCP_CONSTRAINED_MODE": "0" },
      "timeout": 600000
    },
    "xlsx_new": {
      "command": "powershell",
      "args": [
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; if (!(Test-Path $d)) { git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d } else { Set-Location $d; git pull --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\xlsx_new') xlsx-new"
      ],
      "env": { "MCP_CONSTRAINED_MODE": "0" },
      "timeout": 600000
    },
    "pptx_basic": {
      "command": "powershell",
      "args": [
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; if (!(Test-Path $d)) { git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d } else { Set-Location $d; git pull --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\pptx_basic') pptx-basic"
      ],
      "env": { "MCP_CONSTRAINED_MODE": "0" },
      "timeout": 600000
    },
    "pptx_design": {
      "command": "powershell",
      "args": [
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; if (!(Test-Path $d)) { git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d } else { Set-Location $d; git pull --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\pptx_design') pptx-design"
      ],
      "env": { "MCP_CONSTRAINED_MODE": "0" },
      "timeout": 600000
    },
    "pptx_new": {
      "command": "powershell",
      "args": [
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; if (!(Test-Path $d)) { git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d } else { Set-Location $d; git pull --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\pptx_new') pptx-new"
      ],
      "env": { "MCP_CONSTRAINED_MODE": "0" },
      "timeout": 600000
    }
  }
}
```

### macOS / Linux

Replace the `"command"` and `"args"` in each server entry with the bash equivalent:

```json
{
  "mcpServers": {
    "docx_basic": {
      "command": "bash",
      "args": [
        "-c",
        "d=\"$HOME/.mcp_servers/MCP_Microsoft_Office\"; if [ ! -d \"$d/.git\" ]; then rm -rf \"$d\"; git clone https://github.com/azzindani/MCP_Microsoft_Office.git \"$d\" --quiet; else cd \"$d\" && git fetch origin --quiet && git reset --hard FETCH_HEAD --quiet; fi; cd \"$d\"; uv sync --all-packages --quiet; uv run --directory \"$d/servers/docx_basic\" docx-basic"
      ],
      "env": { "MCP_CONSTRAINED_MODE": "0" },
      "timeout": 600000
    }
  }
}
```

Repeat for each server, adjusting the server name in `--directory` and the entry point (e.g. `docx-basic`, `xlsx-basic`, `pptx-basic`).

### Individual Server Configs

Pick only what you need. Each block is standalone — paste it inside the `"mcpServers"` object.

<details>
<summary><strong>docx_basic</strong> — read, search, edit Word documents (15 tools)</summary>

```json
"docx_basic": {
  "command": "powershell",
  "args": [
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
    "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; $g = Join-Path $d '.git'; if (!(Test-Path $g)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d }; git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d --quiet } else { Set-Location $d; git fetch origin --quiet; git reset --hard FETCH_HEAD --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\docx_basic') docx-basic"
  ],
  "env": { "MCP_CONSTRAINED_MODE": "0" },
  "timeout": 600000
}
```

</details>

<details>
<summary><strong>docx_tables</strong> — table CRUD and cell shading in Word documents (10 tools)</summary>

```json
"docx_tables": {
  "command": "powershell",
  "args": [
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
    "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; $g = Join-Path $d '.git'; if (!(Test-Path $g)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d }; git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d --quiet } else { Set-Location $d; git fetch origin --quiet; git reset --hard FETCH_HEAD --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\docx_tables') docx-tables"
  ],
  "env": { "MCP_CONSTRAINED_MODE": "0" },
  "timeout": 600000
}
```

</details>

<details>
<summary><strong>docx_layout</strong> — styles, fonts, margins, PDF export (7 tools)</summary>

```json
"docx_layout": {
  "command": "powershell",
  "args": [
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
    "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; $g = Join-Path $d '.git'; if (!(Test-Path $g)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d }; git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d --quiet } else { Set-Location $d; git fetch origin --quiet; git reset --hard FETCH_HEAD --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\docx_layout') docx-layout"
  ],
  "env": { "MCP_CONSTRAINED_MODE": "0" },
  "timeout": 600000
}
```

</details>

<details>
<summary><strong>docx_new</strong> — create Word documents from scratch (8 tools)</summary>

```json
"docx_new": {
  "command": "powershell",
  "args": [
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
    "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; $g = Join-Path $d '.git'; if (!(Test-Path $g)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d }; git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d --quiet } else { Set-Location $d; git fetch origin --quiet; git reset --hard FETCH_HEAD --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\docx_new') docx-new"
  ],
  "env": { "MCP_CONSTRAINED_MODE": "0" },
  "timeout": 600000
}
```

</details>

<details>
<summary><strong>xlsx_basic</strong> — read, edit, sort Excel spreadsheets (14 tools)</summary>

```json
"xlsx_basic": {
  "command": "powershell",
  "args": [
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
    "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; $g = Join-Path $d '.git'; if (!(Test-Path $g)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d }; git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d --quiet } else { Set-Location $d; git fetch origin --quiet; git reset --hard FETCH_HEAD --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\xlsx_basic') xlsx-basic"
  ],
  "env": { "MCP_CONSTRAINED_MODE": "0" },
  "timeout": 600000
}
```

</details>

<details>
<summary><strong>xlsx_formulas</strong> — formulas, fill-down, auto-sum (9 tools)</summary>

```json
"xlsx_formulas": {
  "command": "powershell",
  "args": [
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
    "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; $g = Join-Path $d '.git'; if (!(Test-Path $g)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d }; git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d --quiet } else { Set-Location $d; git fetch origin --quiet; git reset --hard FETCH_HEAD --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\xlsx_formulas') xlsx-formulas"
  ],
  "env": { "MCP_CONSTRAINED_MODE": "0" },
  "timeout": 600000
}
```

</details>

<details>
<summary><strong>xlsx_charts</strong> — charts, pivot tables, cell styles (5 tools)</summary>

```json
"xlsx_charts": {
  "command": "powershell",
  "args": [
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
    "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; $g = Join-Path $d '.git'; if (!(Test-Path $g)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d }; git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d --quiet } else { Set-Location $d; git fetch origin --quiet; git reset --hard FETCH_HEAD --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\xlsx_charts') xlsx-charts"
  ],
  "env": { "MCP_CONSTRAINED_MODE": "0" },
  "timeout": 600000
}
```

</details>

<details>
<summary><strong>xlsx_new</strong> — create Excel workbooks from scratch (6 tools)</summary>

```json
"xlsx_new": {
  "command": "powershell",
  "args": [
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
    "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; $g = Join-Path $d '.git'; if (!(Test-Path $g)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d }; git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d --quiet } else { Set-Location $d; git fetch origin --quiet; git reset --hard FETCH_HEAD --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\xlsx_new') xlsx-new"
  ],
  "env": { "MCP_CONSTRAINED_MODE": "0" },
  "timeout": 600000
}
```

</details>

<details>
<summary><strong>pptx_basic</strong> — read, edit, add, reorder slides (10 tools)</summary>

```json
"pptx_basic": {
  "command": "powershell",
  "args": [
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
    "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; $g = Join-Path $d '.git'; if (!(Test-Path $g)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d }; git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d --quiet } else { Set-Location $d; git fetch origin --quiet; git reset --hard FETCH_HEAD --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\pptx_basic') pptx-basic"
  ],
  "env": { "MCP_CONSTRAINED_MODE": "0" },
  "timeout": 600000
}
```

</details>

<details>
<summary><strong>pptx_design</strong> — backgrounds, fonts, global slide changes (8 tools)</summary>

```json
"pptx_design": {
  "command": "powershell",
  "args": [
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
    "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; $g = Join-Path $d '.git'; if (!(Test-Path $g)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d }; git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d --quiet } else { Set-Location $d; git fetch origin --quiet; git reset --hard FETCH_HEAD --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\pptx_design') pptx-design"
  ],
  "env": { "MCP_CONSTRAINED_MODE": "0" },
  "timeout": 600000
}
```

</details>

<details>
<summary><strong>pptx_new</strong> — create presentations from scratch (6 tools)</summary>

```json
"pptx_new": {
  "command": "powershell",
  "args": [
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
    "$d = Join-Path $env:USERPROFILE '.mcp_servers\\MCP_Microsoft_Office'; $g = Join-Path $d '.git'; if (!(Test-Path $g)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d }; git clone https://github.com/azzindani/MCP_Microsoft_Office.git $d --quiet } else { Set-Location $d; git fetch origin --quiet; git reset --hard FETCH_HEAD --quiet }; Set-Location $d; uv sync --all-packages --quiet; uv run --directory (Join-Path $d 'servers\\pptx_new') pptx-new"
  ],
  "env": { "MCP_CONSTRAINED_MODE": "0" },
  "timeout": 600000
}
```

</details>

## Available Tools

### Word — docx_basic (15 tools)

Read, search, and edit existing `.docx` files surgically without touching surrounding content.

| Tool | Purpose |
|---|---|
| `get_document_outline` | Return heading structure and paragraph indices — navigate without reading the full doc |
| `get_document_index` | Section tree with paragraph ranges — zero body text returned |
| `fetch_section` | Read only the paragraphs inside one addressed section |
| `read_document` | Full document text (warns on large files, truncates at 150 paragraphs) |
| `read_paragraph` | Single paragraph with full run detail (bold, italic, font, size per run) |
| `read_paragraph_range` | Bounded paragraph range (max 50) |
| `search_paragraphs` | Scan for matching text — returns only matching paragraphs, not the full doc |
| `replace_text` | Find and replace preserving all run formatting (bold, italic, color) |
| `insert_paragraph` | Insert a new paragraph at index N with a named style |
| `delete_paragraph` | Remove paragraph by index or matching text |
| `append_text` | Add a paragraph at the end of the document |
| `get_history` | List all version snapshots for a file |
| `restore_version` | Roll back a file to any previous snapshot |
| `diff_versions` | Compare two versions — shows added, changed, and removed paragraphs |
| `read_receipt` | Full audit trail of all tool operations on a file |

### Word — docx_tables (10 tools)

| Tool | Purpose |
|---|---|
| `list_tables` | Count tables, return dimensions of each |
| `read_table` | Full table as 2D array with merged-cell handling |
| `search_table_cells` | Scan all cells for matching text — returns coordinates |
| `read_table_row` | Single row from table N |
| `set_cell` | Write text to table[N] row[R] col[C] at run level |
| `set_cell_style` | Shade and format cells — `fill`, `color`, `bold`, `align`; `row`/`col` `-1` means all; `band_fill` stripes alternate body rows |
| `add_row` | Append a row with data values to table N |
| `delete_row` | Remove row R from table N |
| `add_table` | Insert a new table at paragraph position N |
| `delete_table` | Remove table N from document |

### Word — docx_layout (7 tools)

| Tool | Purpose |
|---|---|
| `set_heading` | Apply Heading 1–6 style to paragraph N |
| `set_font` | Set font name, size, bold, italic, `color` (hex), `line_spacing` and `space_after` on paragraph N |
| `set_paragraph_style` | Apply any named style from the document gallery |
| `add_image` | Insert image at paragraph N with width control |
| `set_page_margins` | Set top/bottom/left/right margins in cm |
| `add_header_footer` | Set header or footer for all pages — `font_size`, `color`, `align`, and `page_numbers` for a live PAGE field |
| `export_pdf` | Export to PDF via LibreOffice or Word. `open_after=True` opens it automatically |

### Word — docx_new (8 tools)

Create new Word documents from scratch. Every tool accepts `open_after=True`.

| Tool | Purpose |
|---|---|
| `create_document` | Blank `.docx` — save and open |
| `create_from_text` | Build from a `[{text, style}]` paragraph list |
| `create_from_sections` | Structured doc from `[{heading, body}]` sections — Heading 1 title, Heading 2 sections |
| `create_from_blocks` | Designed doc in one call from typed blocks — `heading`, `text`, `bullets`, `table`, `kpi`, `callout`, `rule`, `pagebreak` (see below) |

#### `create_from_blocks` — a readable document in one call

`create_from_sections` writes one Heading and one paragraph per section, which
is a wall of text whenever the content has figures or lists in it. Blocks carry
the structure instead. One `accent` colour drives the headings, the table header
fill, the callout tint and the rules, so the document reads as one design.

```json
[
  {"kind": "callout", "title": "Bottom line", "text": "Volume is 46% below the 2000 peak."},
  {"kind": "heading", "text": "At a glance", "level": 2},
  {"kind": "kpi",     "items": [{"value": "12.69 M", "label": "Total tons"}, {"value": "43.6k", "label": "Avg / month"}]},
  {"kind": "table",   "header": ["Region", "Share"], "rows": [["US", "42.7%"], ["Asia", "40.8%"]], "widths": [6, 3]},
  {"kind": "rule"},
  {"kind": "bullets", "numbered": true, "items": ["Re-price for reality.", "De-risk carriers."]},
  {"kind": "pagebreak"}
]
```

Tables get a shaded header and banded body rows; a `kpi` row sets the figures
across the page with small-caps labels. An unrecognised `kind` is reported in
`skipped` rather than silently dropped.
| `create_from_template` | Copy a template and fill `{{PLACEHOLDER}}` substitutions |
| `create_letter` | Formatted business letter with sender, recipient, subject, body |
| `merge_documents` | Combine multiple `.docx` files into one with optional page breaks |
| `batch_create_from_template` | Template + `[{KEY: value}]` list → N output files (offer letters, proposals, contracts) |

---

### Excel — xlsx_basic (14 tools)

| Tool | Purpose |
|---|---|
| `get_sheet_summary` | Sheet dimensions, header row, first-column sample — no cell data |
| `list_sheets` | Sheet names with row/column counts |
| `search_cells` | Scan all cells for matching text — returns addresses only |
| `read_cell_range` | Bounded cell range as 2D array (max 200 cells) |
| `read_cell` | Single cell: value, formula string, and data type |
| `set_cell` | Write value to exact cell address |
| `set_range` | Write 2D array to a cell range |
| `insert_row` | Insert row at position N, shift down |
| `delete_row` | Remove row N, shift up |
| `add_sheet` | Create a new sheet with optional name |
| `sort_sheet` | Sort all rows by a column (A→Z or Z→A), preserves header row |
| `rename_sheet` | Rename a sheet tab |
| `find_duplicates` | Find repeated values in a column — returns row numbers per value |
| `copy_sheet` | Duplicate a sheet within the same workbook |

### Excel — xlsx_formulas (9 tools)

| Tool | Purpose |
|---|---|
| `set_formula` | Write a formula to a cell (`=SUM(B2:B10)` etc.) |
| `fill_formula_down` | Drag-down equivalent — fill formula from start cell to end row, adjusting all row references automatically |
| `auto_sum` | Add SUM / AVERAGE / COUNT / MAX / MIN formula for a range |
| `convert_to_values` | Paste-as-values — replace formula cells with their calculated results |
| `set_named_range` | Define a named range for formula use |
| `set_conditional_format` | Color cells by rule (greater than, less than, between, equal to) |
| `set_data_validation` | Add dropdown list or number constraint to a range |
| `freeze_panes` | Freeze header rows and/or columns |
| `set_autofilter` | Enable filter dropdowns on a header row range |

### Excel — xlsx_charts (5 tools)

| Tool | Purpose |
|---|---|
| `add_chart` | Create bar, line, pie, area, or scatter chart from a data range |
| `update_chart` | Change chart title or data range (delete-and-recreate internally) |
| `delete_chart` | Remove chart by name or index |
| `add_pivot_table` | Create a pivot summary table from a data range |
| `set_cell_style` | Set font, fill color (hex), border, and number format on a cell |

### Excel — xlsx_new (6 tools)

Create new Excel workbooks from scratch. Every tool accepts `open_after=True`.

| Tool | Purpose |
|---|---|
| `create_workbook` | Blank `.xlsx` with a named sheet |
| `create_from_data` | Workbook from headers + rows — first row auto-bolded |
| `create_report` | Multi-sheet workbook with auto-generated Cover sheet |
| `create_from_template` | Copy existing `.xlsx`, replace matching cell values |
| `create_from_csv` | Import CSV file → formatted Excel workbook (no pandas required) |
| `create_invoice` | Invoice with item rows, `=B*C` totals, SUM subtotal, tax formula |

---

### PowerPoint — pptx_basic (10 tools)

| Tool | Purpose |
|---|---|
| `read_presentation` | Slide count, titles, shape counts, available layouts |
| `read_slide` | All shapes with name, type, and text content for one slide |
| `read_slide_text` | Quick text-only scan of one slide |
| `search_slides` | Scan all slide text for a query — returns slide index + shape name |
| `set_text` | Replace text in a named shape on a slide (run-level, preserves formatting) |
| `add_slide` | Append slide with layout, title, and body text |
| `delete_slide` | Remove slide by index |
| `reorder_slide` | Move slide from index A to index B |
| `add_text_box` | Insert text box at x/y (inches) position |
| `diff_versions` | Compare two presentation versions by snapshot timestamp |

### PowerPoint — pptx_design (8 tools)

| Tool | Purpose |
|---|---|
| `set_background` | Solid hex color or image file background on a slide |
| `set_font_style` | Font name/size/bold/color on a named shape |
| `add_image_to_all_slides` | Add logo or watermark to every slide at a fixed position |
| `set_font_all_slides` | Apply font name/size/bold/color to all text runs on all slides |
| `add_table` | Insert table with data on a slide |
| `add_chart` | Add bar/line/pie chart from data dict on a slide |
| `duplicate_slide` | Copy slide N to position M |
| `export_pdf` | Export to PDF via LibreOffice or PowerPoint. `open_after=True` opens it automatically |

### PowerPoint — pptx_new (6 tools)

Create new presentations from scratch. Every tool accepts `open_after=True`.

| Tool | Purpose |
|---|---|
| `create_presentation` | Blank `.pptx` with a title slide |
| `create_from_outline` | Deck from `[{title, content, layout}]` slide list |
| `create_deck_from_data` | Title slide + content slides from `[{heading, bullets}]` list |
| `create_from_template` | Copy existing `.pptx` as a starting point |
| `create_agenda` | Meeting agenda deck: title slide + agenda slide from `[{topic, duration, owner}]` |
| `create_from_docx` | Convert Word document outline → PowerPoint draft (H1=slide, H2=bullets) |

## Recommended Server Combinations

Load only what the task requires — fewer tools in context means better model reliability.

| Task | Servers to load | Tools in context |
|---|---|---|
| Edit an existing contract | `docx_basic` | 15 |
| Contract + tables | `docx_basic` + `docx_tables` | 24 |
| Format a document | `docx_layout` | 7 |
| Write a new report or letter | `docx_new` | 7 |
| Generate 20 offer letters from template | `docx_new` | 7 |
| Data entry + formulas | `xlsx_basic` + `xlsx_formulas` | 23 |
| Build an invoice or budget | `xlsx_new` + `xlsx_formulas` | 15 |
| Create charts and dashboards | `xlsx_charts` | 5 |
| Edit an existing presentation | `pptx_basic` | 10 |
| Style and brand a deck | `pptx_basic` + `pptx_design` | 18 |
| Create a presentation from scratch | `pptx_new` | 6 |
| Full office workflow | Any 2 servers per format | ≤24 |

## Usage Examples

### Write a report

```
Write me a 5-section business report on Q3 performance, save it as report.docx
```

### Create an offer letter from a template

```
I have a template at C:\HR\offer_template.docx with {{NAME}}, {{POSITION}}, {{SALARY}}, {{START_DATE}} placeholders.
Generate offer letters for: Alice (Engineer, $90,000, May 1), Bob (Designer, $75,000, May 15).
Save them to C:\HR\Offers\
```

### Edit a contract

```
In contract.docx, replace all instances of "30 days" with "14 days" without changing the formatting
```

### Compare two contract versions

```
Show me what changed between contract_v1.docx and contract_v2.docx
```

### Apply a VLOOKUP across 500 rows

```
In budget.xlsx sheet "Q3", write =VLOOKUP(A2,Sheet2!A:B,2,0) in cell B2, then fill it down to row 500
```

### Build an invoice

```
Create an invoice for Acme Corp from Widget Ltd.
Invoice #INV-2026-001, items: Consulting 10 hours at $150, Support 5 hours at $80.
Apply 10% tax. Save as invoice_april.xlsx
```

### Import CSV to Excel

```
Import my data from C:\exports\sales_q3.csv into a formatted Excel file at C:\reports\sales_q3.xlsx
```

### Sort and clean a spreadsheet

```
In employees.xlsx sheet "Staff", sort all rows by column C alphabetically, then find any duplicate email addresses in column D
```

### Turn meeting notes into a presentation

```
I have meeting_notes.docx with sections for each agenda topic.
Convert it into a PowerPoint presentation and save as meeting_slides.pptx
```

### Create a meeting agenda deck

```
Create an agenda presentation for the Q2 planning meeting on April 15.
Items: Revenue Review (15 min, Alice), Product Roadmap (20 min, Bob), Action Items (10 min, All).
Presenter: Carol
```

### Add company logo to every slide

```
Add our logo from C:\assets\logo.png to every slide in pitch_deck.pptx.
Place it in the top-right corner, 1 inch wide, 0.5 inch tall.
```

### Undo a change

```
Restore budget.xlsx to the previous version
```

## Configuration

### Constrained Mode

For lower-memory machines, set `MCP_CONSTRAINED_MODE=1` in the `env` section of your MCP config. This reduces response sizes to keep tool results within the model's effective context window:

| Limit | Normal | Constrained |
|---|---|---|
| Max paragraphs returned | 50 | 20 |
| Max cells returned | 200 | 100 |
| Max search results | 50 | 10 |

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MCP_CONSTRAINED_MODE` | `0` | Set to `1` for low-memory machines |
| `GIT_INTEGRATION` | `true` | Set to `false` to disable auto Git commits on edits |
| `MCP_OUTPUT_DIR` | `~/Downloads` | Where new documents land by default |
| `MCP_PUBLIC_BASE_URL` | _(unset)_ | Public URL serving `MCP_OUTPUT_DIR`; adds `public_url` to results |
| `MCP_FETCH_URLS` | `0` | `1` lets any file path argument be an `http(s)` URL |
| `MCP_FETCH_ALLOW_PRIVATE` | `0` | `1` permits fetching hosts on private/loopback addresses |
| `MCP_MAX_FETCH_MB` | `100` | Size cap for a fetched URL |

### Hybrid local + remote file handling

The same engine serves a local stdio install and a self-hosted HTTP endpoint,
but over HTTP the caller shares no filesystem with the server: a server-local
output path means nothing to it, and it may hold a link rather than a path.
Three opt-in variables close that gap without changing local behaviour — all
are unset by default, so a local install stays offline and writes to
`~/Downloads` exactly as before:

- **`MCP_OUTPUT_DIR`** — bind-mount a directory here and every generated
  `.docx`/`.xlsx`/`.pptx`/`.pdf` defaults into it, so documents land somewhere
  you can actually see. An explicit `output_path` still wins.
- **`MCP_PUBLIC_BASE_URL`** — the public URL that serves that directory. Every
  produced document then comes back with a `public_url` you can open or pass on.
- **`MCP_FETCH_URLS=1`** — a file path argument may be a link
  (`read_document("https://…/contract.docx")`), downloaded into
  `MCP_OUTPUT_DIR/inbox` before the tool runs. Hosts resolving to
  loopback/link-local/private addresses are refused, redirects included,
  unless `MCP_FETCH_ALLOW_PRIVATE=1`.

Document-creating tools also accept `return_content=True`, which embeds the
file's bytes as `content_base64` for callers that have neither a shared
filesystem nor access to the public URL.

## Deployment

| Mode | Best for | Transport | Auth |
|---|---|---|---|
| **Local stdio** (default, above) | LM Studio / Claude Code on your machine | stdio | none |
| **Local Docker / HTTP** | Testing, or one other machine on your LAN | HTTP | optional |
| **VPS Docker** | Remote MCP clients (claude.ai, hosted harnesses) | HTTP | **required** |

Each server keeps its own stdio server for local LM Studio "add one server"
installs. For Docker/remote deployment all 11 run as separate MCP endpoints
inside **one process** (`unified_server.py`) on **one port** —
python-docx/openpyxl/python-pptx load once instead of eleven times (~90 MiB
vs ~650 MiB idle), and all 11 still share one bearer-token set.

### HTTP transport (no Docker)

```bash
uv run python unified_server.py --port 8830
curl http://localhost:8830/health              # {"status":"ok","version":"0.1.2","sub_servers":[...]}
curl http://localhost:8830/docx-basic/health   # per-server health
```

### Docker

Requires `uv sync --frozen --all-packages` (a true uv workspace — plain `uv sync`
only installs the root project's own deps, not the 11 members' runtime deps),
already wired into the Dockerfile:

```bash
docker compose up -d --build
curl http://localhost:8830/health            # aggregate
curl http://localhost:8830/docx-basic/mcp    # docx-basic
curl http://localhost:8830/pptx-new/mcp      # pptx-new
```

With auth (**required** for any publicly reachable deploy — this is how the
production `office.casava.space` endpoint runs):

```bash
echo "OFFICE_API_KEY=$(openssl rand -hex 24)" > .env   # gitignored, auto-loaded by docker-compose.yml
docker compose up -d --build
```

For multiple named clients instead of one shared key (Folio-style):

```bash
cp tokens.example.json tokens.json   # edit: replace placeholders with `openssl rand -hex 32`
OFFICE_TOKENS_FILE=/path/to/tokens.json docker compose up -d --build
```

`/<name>/mcp` requires `Authorization: Bearer <token>` once any of
`OFFICE_TOKENS_FILE` / `OFFICE_TOKENS` / `OFFICE_API_KEY` is set; `/health`
and `/version` (aggregate and per-server) stay unauthenticated.

### Deployment environment variables

| Variable | Default | Description |
|---|---|---|
| `OFFICE_HOST` | `0.0.0.0` | Bind address for the unified server |
| `OFFICE_PORT` | `8830` | Port for the unified server (all 11 sub-servers) |
| `OFFICE_TOKENS_FILE` | unset | JSON file of named bearer tokens (`{"name": "token"}`) — highest priority, shared across all 11 servers |
| `OFFICE_TOKENS` | unset | Inline `"name:token,name2:token2"` |
| `OFFICE_API_KEY` | unset | Single shared bearer token |

### Remote testing (Cloudflare Quick Tunnel)

Same idea as `azzindani/Folio`'s `launch.sh`: bring the Docker deployment up
and expose it at an ephemeral `*.trycloudflare.com` URL — no VPS, no DNS, no
account — so all 11 sub-servers are reachable from any MCP-compatible
harness for a quick remote smoke test.

```bash
./launch_tunnel.sh          # docker compose up -d --build, then tunnel
./launch_tunnel.sh stop     # tear the tunnel down (container keeps running)
```

Not for production: Quick Tunnels are unauthenticated at the transport layer.
Set `OFFICE_API_KEY` or `OFFICE_TOKENS_FILE` before tunneling so `/<name>/mcp`
still requires a bearer token even while it's publicly reachable.

### Remote smoke test (`remote_smoke_test.sh`)

Run in CI against a container (the `e2e` job) and by hand against the
deployment. `pytest` itself stays offline. Exercises a running HTTP endpoint: auth enforcement plus a real
handwritten-prompt-style call for **all 98 tools** across all 11 sub-servers
(docx-new/basic/tables/layout, xlsx-new/basic/formulas/charts,
pptx-new/basic/design), producing real `.docx`/`.xlsx`/`.pptx` files from a
real generated logo image and CSV, chaining real outputs (paragraph indices,
shape names, snapshot timestamps) between calls. This is what caught
`export_pdf` always failing because LibreOffice wasn't installed in the
runtime image — exactly the kind of deployment-only gap pytest alone can't
catch.

```bash
./remote_smoke_test.sh                          # reads OFFICE_API_KEY from .env, targets office.casava.space
DOMAIN=http://localhost:8830 ./remote_smoke_test.sh   # test a different target
CONTAINER=mcp-office ./remote_smoke_test.sh      # override container name
```

## Uninstall

**Step 1:** Remove from LM Studio
1. Open LM Studio → Developer tab (`</>`)
2. Delete the office MCP entries from MCP Servers
3. Restart LM Studio

**Step 2:** Delete installed files

```cmd
rmdir /s /q %USERPROFILE%\.mcp_servers\MCP_Microsoft_Office
```

## Architecture

```
MCP_Microsoft_Office/
├── servers/
│   ├── docx_basic/          ← 15 tools: read, search, edit, history
│   │   ├── server.py        ← thin MCP wrapper (zero domain logic)
│   │   ├── engine.py        ← pure python-docx logic
│   │   └── pyproject.toml
│   ├── docx_tables/         ← 9 tools: table CRUD
│   ├── docx_layout/         ← 7 tools: styles, fonts, margins, PDF export
│   ├── docx_new/            ← 7 tools: create, merge, batch generate
│   ├── xlsx_basic/          ← 14 tools: read, edit, sort, dedup
│   ├── xlsx_formulas/       ← 9 tools: formulas, fill-down, auto-sum
│   ├── xlsx_charts/         ← 5 tools: charts, pivot tables, cell styles
│   ├── xlsx_new/            ← 6 tools: create, CSV import, invoice
│   ├── pptx_basic/          ← 10 tools: read, edit, add, reorder slides
│   ├── pptx_design/         ← 8 tools: backgrounds, fonts, global changes
│   └── pptx_new/            ← 6 tools: create, agenda, doc→deck
├── shared/
│   ├── version_control.py   ← snapshot() and restore()
│   ├── patch_validator.py   ← validate op arrays before apply
│   ├── file_utils.py        ← path resolution, atomic writes
│   ├── platform_utils.py    ← 8GB mode, limits, open_file()
│   ├── progress.py          ← ok/fail/info/warn step helpers
│   ├── receipt.py           ← per-file operation audit log
│   ├── address_resolver.py  ← §N.pM / A1:B5 / slide[N]/shape[name] addressing
│   ├── doc_diff.py          ← paragraph/cell/shape-level diff engine
│   ├── gitops.py            ← optional auto-commit on every write
│   └── live_edit.py         ← auto-reload in Word/Excel/LibreOffice after save
├── tests/
│   ├── fixtures/            ← real .docx .xlsx .pptx test files
│   ├── conftest.py
│   └── test_*.py            ← one test file per server
├── install/
│   ├── install.sh           ← Linux / macOS interactive installer
│   ├── install.bat          ← Windows interactive installer
│   └── mcp_config_writer.py ← writes LM Studio / Claude Desktop / Cursor config
└── pyproject.toml           ← uv workspace root
```

Every server follows the same pattern: `server.py` is a thin MCP wrapper, `engine.py` contains all document logic and has zero MCP imports, making it directly testable with pytest.

## Development

### Local setup

```bash
# Clone
git clone https://github.com/azzindani/MCP_Microsoft_Office.git
cd MCP_Microsoft_Office

# Install all dependencies
uv sync --all-packages

# Generate test fixtures
uv run python tests/create_fixtures.py

# Run all tests
uv run pytest tests/ -v --tb=short

# Lint
uv run ruff check .

# Format check
uv run ruff format --check .
```

### Run a single server locally

```bash
uv run --directory servers/docx_basic docx-basic
```

### Interactive installer (Linux / macOS)

```bash
bash install/install.sh
```

### Interactive installer (Windows)

```cmd
install\install.bat
```

## License

MIT
