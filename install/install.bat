@echo off
setlocal enabledelayedexpansion

echo ===================================
echo   office-mcp installer
echo ===================================
echo.

set REPO_DIR=%~dp0..
cd /d "%REPO_DIR%"

:: ─── 1. Check Python ──────────────────────────────────────────────────────────

set PYTHON_CMD=
for %%P in (py python3 python) do (
    if "!PYTHON_CMD!"=="" (
        where %%P >nul 2>&1
        if not errorlevel 1 (
            set PYTHON_CMD=%%P
        )
    )
)

if "!PYTHON_CMD!"=="" (
    echo Error: Python not found.
    echo Install Python 3.11+: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2" %%V in ('!PYTHON_CMD! --version 2^>^&1') do set PYTHON_VERSION=%%V
echo [OK] Python %PYTHON_VERSION% found

:: ─── 2. Enable long paths ─────────────────────────────────────────────────────

reg add "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled /t REG_DWORD /d 1 /f >nul 2>&1
echo [OK] Long path support enabled

:: ─── 3. Check / install uv ────────────────────────────────────────────────────

where uv >nul 2>&1
if errorlevel 1 (
    echo [->] uv not found. Installing...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    :: Refresh PATH
    set PATH=%USERPROFILE%\.local\bin;%PATH%
    where uv >nul 2>&1
    if errorlevel 1 (
        echo Error: uv installation failed.
        echo Install manually: https://docs.astral.sh/uv/getting-started/installation/
        pause
        exit /b 1
    )
    echo [OK] uv installed
) else (
    for /f "tokens=*" %%V in ('uv --version') do echo [OK] uv found: %%V
)

:: ─── 4. Install dependencies ──────────────────────────────────────────────────

echo.
echo [->] Installing Python dependencies...
uv sync --all-packages
if errorlevel 1 (
    echo Error: dependency installation failed.
    pause
    exit /b 1
)
echo [OK] Dependencies installed

:: ─── 5. Platform selection ────────────────────────────────────────────────────

echo.
echo Which AI platform do you use?
echo   1) LM Studio (recommended for local LLMs)
echo   2) Claude Desktop
echo   3) Cursor
echo   4) Windsurf
echo   5) Cline (VS Code)
echo   6) Multiple platforms -- write all configs
echo.
set /p PLATFORM_CHOICE="Enter number [1]: "

if "!PLATFORM_CHOICE!"=="2" (set PLATFORM=claude-desktop) else (
if "!PLATFORM_CHOICE!"=="3" (set PLATFORM=cursor) else (
if "!PLATFORM_CHOICE!"=="4" (set PLATFORM=windsurf) else (
if "!PLATFORM_CHOICE!"=="5" (set PLATFORM=cline) else (
if "!PLATFORM_CHOICE!"=="6" (set PLATFORM=all) else (
    set PLATFORM=lmstudio
)))))

echo [->] Selected platform: !PLATFORM!

:: ─── 6. Server selection ──────────────────────────────────────────────────────

echo.
echo Which servers do you want to register?
echo   1) docx_basic   -- Word documents (read, edit, search)
echo   2) docx_tables  -- Word tables (CRUD)
echo   3) docx_layout  -- Word styles, fonts, margins, PDF export
echo   4) xlsx_basic   -- Excel sheets (read, edit cells)
echo   5) xlsx_formulas -- Excel formulas, validation, filters
echo   6) xlsx_charts  -- Excel charts and pivot tables
echo   7) pptx_basic   -- PowerPoint slides (read, edit, add)
echo   8) pptx_design  -- PowerPoint styling, backgrounds, charts
echo   9) All servers
echo.
set /p SERVER_CHOICE="Enter number [9]: "

if "!SERVER_CHOICE!"=="1" (set SERVERS=docx_basic) else (
if "!SERVER_CHOICE!"=="2" (set SERVERS=docx_tables) else (
if "!SERVER_CHOICE!"=="3" (set SERVERS=docx_layout) else (
if "!SERVER_CHOICE!"=="4" (set SERVERS=xlsx_basic) else (
if "!SERVER_CHOICE!"=="5" (set SERVERS=xlsx_formulas) else (
if "!SERVER_CHOICE!"=="6" (set SERVERS=xlsx_charts) else (
if "!SERVER_CHOICE!"=="7" (set SERVERS=pptx_basic) else (
if "!SERVER_CHOICE!"=="8" (set SERVERS=pptx_design) else (
    set SERVERS=all
))))))))

echo [->] Selected servers: !SERVERS!

:: ─── 7. 8GB mode ──────────────────────────────────────────────────────────────

echo.
set /p MODE_8GB_CHOICE="Enable 8GB VRAM mode? (y/N): "
if /i "!MODE_8GB_CHOICE!"=="y" (
    set MODE_8GB=--8gb-mode
) else (
    set MODE_8GB=
)

:: ─── 8. Write config ──────────────────────────────────────────────────────────

echo.
echo [->] Registering servers in !PLATFORM! config...
uv run python install\mcp_config_writer.py --servers !SERVERS! --platform !PLATFORM! !MODE_8GB!

echo.
echo ===================================
echo   Installation complete!
echo ===================================
echo.
echo Restart your AI application to load the new MCP tools.
echo.
echo For help: https://github.com/azzindani/mcp_microsoft_office/issues
echo.
pause
