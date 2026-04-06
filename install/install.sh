#!/bin/sh
# office-mcp installer — Linux / macOS
# POSIX sh compatible (no bash-isms)

set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_MIN_VERSION="3.11"

echo "==================================="
echo "  office-mcp installer"
echo "==================================="
echo ""

# ─── 1. Check Python version ──────────────────────────────────────────────────

check_python() {
    if command -v python3 > /dev/null 2>&1; then
        PYTHON_CMD=python3
    elif command -v python > /dev/null 2>&1; then
        PYTHON_CMD=python
    else
        echo "Error: Python not found."
        echo "Install Python 3.11+: https://www.python.org/downloads/"
        exit 1
    fi

    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f2)

    if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; }; then
        echo "Error: Python $PYTHON_MIN_VERSION+ required, found $PYTHON_VERSION"
        echo "Install Python 3.11+: https://www.python.org/downloads/"
        exit 1
    fi
    echo "✔ Python $PYTHON_VERSION found"
}

# ─── 2. Check / install uv ────────────────────────────────────────────────────

check_uv() {
    if command -v uv > /dev/null 2>&1; then
        echo "✔ uv found: $(uv --version)"
    else
        echo "→ uv not found. Installing..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        # Add to PATH for current session
        export PATH="$HOME/.local/bin:$PATH"
        if command -v uv > /dev/null 2>&1; then
            echo "✔ uv installed: $(uv --version)"
            echo "  Note: Add ~/.local/bin to your PATH to use uv in future sessions."
        else
            echo "Error: uv installation failed."
            echo "Install manually: curl -LsSf https://astral.sh/uv/install.sh | sh"
            exit 1
        fi
    fi
}

# ─── 3. Install dependencies ──────────────────────────────────────────────────

install_deps() {
    echo ""
    echo "→ Installing Python dependencies..."
    cd "$REPO_DIR"
    uv sync --all-packages
    echo "✔ Dependencies installed"
}

# ─── 4. Platform selection ────────────────────────────────────────────────────

select_platform() {
    echo ""
    echo "Which AI platform do you use?"
    echo "  1) LM Studio (recommended for local LLMs)"
    echo "  2) Claude Desktop"
    echo "  3) Cursor"
    echo "  4) Windsurf"
    echo "  5) Cline (VS Code)"
    echo "  6) Multiple platforms — write all configs"
    echo ""
    printf "Enter number [1]: "
    read PLATFORM_CHOICE

    case "$PLATFORM_CHOICE" in
        2) PLATFORM="claude-desktop" ;;
        3) PLATFORM="cursor" ;;
        4) PLATFORM="windsurf" ;;
        5) PLATFORM="cline" ;;
        6) PLATFORM="all" ;;
        *) PLATFORM="lmstudio" ;;
    esac
    echo "→ Selected platform: $PLATFORM"
}

# ─── 5. Server selection ──────────────────────────────────────────────────────

select_servers() {
    echo ""
    echo "Which servers do you want to register?"
    echo "  1)  docx_basic   — Word documents (read, edit, search)"
    echo "  2)  docx_tables  — Word tables (CRUD)"
    echo "  3)  docx_layout  — Word styles, fonts, margins, PDF export"
    echo "  4)  docx_new     — Create new Word documents from scratch"
    echo "  5)  xlsx_basic   — Excel sheets (read, edit cells)"
    echo "  6)  xlsx_formulas — Excel formulas, validation, filters"
    echo "  7)  xlsx_charts  — Excel charts and pivot tables"
    echo "  8)  xlsx_new     — Create new Excel workbooks from scratch"
    echo "  9)  pptx_basic   — PowerPoint slides (read, edit, add)"
    echo "  10) pptx_design  — PowerPoint styling, backgrounds, charts"
    echo "  11) pptx_new     — Create new PowerPoint presentations from scratch"
    echo "  12) All servers"
    echo ""
    printf "Enter number(s) separated by space [12]: "
    read SERVER_CHOICES

    SERVERS=""
    for choice in $SERVER_CHOICES; do
        case "$choice" in
            1)  SERVERS="$SERVERS docx_basic" ;;
            2)  SERVERS="$SERVERS docx_tables" ;;
            3)  SERVERS="$SERVERS docx_layout" ;;
            4)  SERVERS="$SERVERS docx_new" ;;
            5)  SERVERS="$SERVERS xlsx_basic" ;;
            6)  SERVERS="$SERVERS xlsx_formulas" ;;
            7)  SERVERS="$SERVERS xlsx_charts" ;;
            8)  SERVERS="$SERVERS xlsx_new" ;;
            9)  SERVERS="$SERVERS pptx_basic" ;;
            10) SERVERS="$SERVERS pptx_design" ;;
            11) SERVERS="$SERVERS pptx_new" ;;
            *)  SERVERS="all" ; break ;;
        esac
    done

    if [ -z "$SERVERS" ] || [ "$SERVERS" = "all" ]; then
        SERVERS="all"
    else
        # Trim leading/trailing spaces and replace spaces with commas
        SERVERS=$(echo "$SERVERS" | sed 's/^ //;s/ $//' | tr ' ' ',')
    fi
    echo "→ Selected servers: $SERVERS"
}

# ─── 6. 8GB mode selection ────────────────────────────────────────────────────

select_8gb_mode() {
    echo ""
    printf "Enable 8GB VRAM mode? (smaller response limits for low-RAM machines) [y/N]: "
    read MODE_8GB_CHOICE
    case "$MODE_8GB_CHOICE" in
        [Yy]*) MODE_8GB="--8gb-mode" ;;
        *) MODE_8GB="" ;;
    esac
}

# ─── 7. Write config ──────────────────────────────────────────────────────────

write_config() {
    echo ""
    echo "→ Registering servers in $PLATFORM config..."
    cd "$REPO_DIR"
    uv run python install/mcp_config_writer.py \
        --servers "$SERVERS" \
        --platform "$PLATFORM" \
        $MODE_8GB
}

# ─── Main ─────────────────────────────────────────────────────────────────────

check_python
check_uv
install_deps
select_platform
select_servers
select_8gb_mode
write_config

echo ""
echo "==================================="
echo "  Installation complete!"
echo "==================================="
echo ""
echo "Restart your AI application to load the new MCP tools."
echo ""
echo "For help or issues: https://github.com/azzindani/mcp_microsoft_office/issues"
