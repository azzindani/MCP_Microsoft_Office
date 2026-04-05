#!/usr/bin/env python3
"""
MCP config writer for office-mcp.

Writes server entries to the appropriate config file for each AI platform.
Usage:
    python install/mcp_config_writer.py --servers docx_basic,xlsx_basic --platform lmstudio
    python install/mcp_config_writer.py --servers all --platform claude-desktop
"""

import argparse
import os
import sys
from pathlib import Path

# Add repo root to path so we can import shared
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.file_utils import read_mcp_json, write_mcp_json
from shared.platform_utils import (
    get_claude_desktop_config_path,
    get_cline_config_path,
    get_cursor_config_path,
    get_lmstudio_mcp_config_path,
    get_windsurf_config_path,
    is_linux,
    is_macos,
    is_windows,
)

REPO_ROOT = Path(__file__).parent.parent.resolve()

ALL_SERVERS = [
    "docx_basic",
    "docx_tables",
    "docx_layout",
    "xlsx_basic",
    "xlsx_formulas",
    "xlsx_charts",
    "pptx_basic",
    "pptx_design",
]

SERVER_DISPLAY_NAMES = {
    "docx_basic": "docx-basic",
    "docx_tables": "docx-tables",
    "docx_layout": "docx-layout",
    "xlsx_basic": "xlsx-basic",
    "xlsx_formulas": "xlsx-formulas",
    "xlsx_charts": "xlsx-charts",
    "pptx_basic": "pptx-basic",
    "pptx_design": "pptx-design",
}

PLATFORM_CONFIG_PATHS = {
    "lmstudio": get_lmstudio_mcp_config_path,
    "claude-desktop": get_claude_desktop_config_path,
    "cursor": get_cursor_config_path,
    "windsurf": get_windsurf_config_path,
    "cline": get_cline_config_path,
}


def build_server_entry(server_dir: str, env: dict | None = None) -> dict:
    """Build the mcp.json entry for a server."""
    server_path = REPO_ROOT / "servers" / server_dir
    entry: dict = {
        "command": "uv",
        "args": [
            "run",
            "--directory",
            str(server_path),
            SERVER_DISPLAY_NAMES[server_dir],
        ],
        "env": env or {},
    }
    return entry


def write_lmstudio_config(
    config_path: Path,
    servers: list[str],
    env: dict | None = None,
) -> list[str]:
    """Write standard mcpServers format (LM Studio / Claude Desktop / Cursor / Windsurf)."""
    data = read_mcp_json(str(config_path))
    if "mcpServers" not in data:
        data["mcpServers"] = {}

    registered = []
    skipped = []
    for server_dir in servers:
        name = SERVER_DISPLAY_NAMES[server_dir]
        if name in data["mcpServers"]:
            skipped.append(name)
            continue
        data["mcpServers"][name] = build_server_entry(server_dir, env)
        registered.append(name)

    write_mcp_json(str(config_path), data)
    return registered


def write_cline_config(
    config_path: Path,
    servers: list[str],
    env: dict | None = None,
) -> list[str]:
    """Write Cline format (nested under cline.mcpServers in settings.json)."""
    data = read_mcp_json(str(config_path))
    if "cline.mcpServers" not in data:
        data["cline.mcpServers"] = {}

    registered = []
    for server_dir in servers:
        name = SERVER_DISPLAY_NAMES[server_dir]
        if name in data["cline.mcpServers"]:
            continue
        data["cline.mcpServers"][name] = build_server_entry(server_dir, env)
        registered.append(name)

    write_mcp_json(str(config_path), data)
    return registered


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Register office-mcp servers in AI platform config files."
    )
    parser.add_argument(
        "--servers",
        default="all",
        help=(
            "Comma-separated server names to register, or 'all'. "
            f"Available: {', '.join(ALL_SERVERS)}"
        ),
    )
    parser.add_argument(
        "--platform",
        default="lmstudio",
        choices=list(PLATFORM_CONFIG_PATHS.keys()) + ["all"],
        help="Target AI platform config to update.",
    )
    parser.add_argument(
        "--8gb-mode",
        action="store_true",
        dest="mode_8gb",
        help="Enable 8GB VRAM mode (smaller response limits).",
    )
    parser.add_argument(
        "--config",
        default="",
        help="Override config file path (default: auto-detect for platform).",
    )

    args = parser.parse_args()

    # Resolve server list
    if args.servers.lower() == "all":
        servers = ALL_SERVERS
    else:
        servers = [s.strip() for s in args.servers.split(",")]
        invalid = [s for s in servers if s not in ALL_SERVERS]
        if invalid:
            print(f"Error: unknown servers: {invalid}")
            print(f"Available: {ALL_SERVERS}")
            sys.exit(1)

    # Build env
    env: dict = {}
    if args.mode_8gb:
        env["OFFICE_MCP_8GB_MODE"] = "1"

    # Resolve platforms
    platforms: list[str] = []
    if args.platform == "all":
        platforms = [p for p in PLATFORM_CONFIG_PATHS if p != "cline"]
        platforms.append("cline")
    else:
        platforms = [args.platform]

    for platform in platforms:
        if args.config:
            config_path = Path(args.config)
        else:
            config_path = PLATFORM_CONFIG_PATHS[platform]()

        # Check if config file's parent directory exists
        if not config_path.parent.exists():
            print(f"  [{platform}] Skipping — config directory not found: {config_path.parent}")
            continue

        try:
            if platform == "cline":
                registered = write_cline_config(config_path, servers, env)
            else:
                registered = write_lmstudio_config(config_path, servers, env)

            if registered:
                print(f"  [{platform}] Registered: {', '.join(registered)}")
                print(f"             Config: {config_path}")
            else:
                print(f"  [{platform}] All servers already registered — nothing changed.")

        except Exception as e:
            print(f"  [{platform}] Error: {e}")

    print()
    print("Done. Restart your AI application to load the new tools.")


if __name__ == "__main__":
    main()
