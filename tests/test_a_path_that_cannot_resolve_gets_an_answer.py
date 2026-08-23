"""A tool whose file_path cannot resolve must still return a dict.

Forty-nine write tools across nine modules opened with

    try:
        from docx import Document
        path = resolve_path(file_path)
        ...
    except Exception as e:
        return {..., "hint": hint_for_error(e, path)}

`resolve_path()` raises ValueError on four caller-reachable inputs: a
`workspace:`/`project:` alias that does not resolve, a path inside
`.mcp_versions/`, a null byte, and a URL that cannot be fetched. When it did,
`path` had never been bound, so the handler itself raised

    UnboundLocalError: cannot access local variable 'path'

and the tool returned nothing at all — no dict, no success flag, no error the
caller could read, in violation of the return-value contract. Live, before the
fix:

    set_cell("workspace:nope/nope", ...)          -> UnboundLocalError
    set_cell("/tmp/x/.mcp_versions/a.xlsx", ...)  -> UnboundLocalError

Nothing caught it: the code compiles, lints and type-checks, and the handler
only runs on a failure path no test reached. It was found by walking every
except handler for names that only its own try binds.

The tool list is read from each server's own registry rather than written out
here, so a tool added later is covered without editing this file.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path

import pytest
from mcp.types import CallToolResult

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SERVERS = [
    "docx_basic",
    "docx_layout",
    "docx_tables",
    "pptx_basic",
    "pptx_design",
    "xlsx_basic",
    "xlsx_charts",
    "xlsx_formulas",
]

# Each is rejected by resolve_path() before file_path ever becomes a Path.
UNRESOLVABLE = [
    "workspace:no-such-workspace/no-such-alias",
    "/tmp/nowhere/.mcp_versions/snapshot.docx",
]


def load(name: str):
    pkg = ROOT / "servers" / name / name
    if str(pkg.parent) not in sys.path:
        sys.path.insert(0, str(pkg.parent))
    return importlib.import_module(f"{name}.server")


def _filler(prop_name: str, schema: dict, tmp: Path):
    """A value of the right type, so only file_path is the interesting input."""
    if "path" in prop_name or "dir" in prop_name:
        return str(tmp / "out.bin")
    raw = schema.get("type")
    if isinstance(raw, list):
        raw = next((k for k in raw if k != "null"), "string")
    kind = raw if isinstance(raw, str) else "string"
    defaults: dict[str, object] = {
        "string": "x",
        "integer": 1,
        "number": 1.0,
        "boolean": False,
        "array": [],
        "object": {},
    }
    return defaults.get(kind, "x")


def tools_taking_a_file_path(server: str) -> list[tuple[str, dict]]:
    mod = load(server)
    found = []
    for name, tool in mod.mcp._tool_manager._tools.items():
        params = tool.parameters or {}
        props = params.get("properties", {})
        if "file_path" not in props:
            continue
        found.append((name, params))
    return found


ALL = [(s, name, params) for s in SERVERS for name, params in tools_taking_a_file_path(s)]


class TestAnUnresolvablePathIsReported:
    def test_the_servers_expose_the_tools_this_covers(self):
        # A registry that came back empty would make every case below vacuous.
        assert len(ALL) >= 40, f"only {len(ALL)} file_path tools found"

    @pytest.mark.parametrize("bad", UNRESOLVABLE)
    @pytest.mark.parametrize("server,tool,params", ALL, ids=[f"{s}.{n}" for s, n, _ in ALL])
    def test_a_dict_comes_back(self, server, tool, params, bad, tmp_path):
        args = {"file_path": bad}
        for prop, schema in params.get("properties", {}).items():
            if prop in args or prop not in params.get("required", []):
                continue
            args[prop] = _filler(prop, schema, tmp_path)

        mod = load(server)
        result = asyncio.run(mod.mcp._tool_manager.call_tool(tool, args, convert_result=True))
        CallToolResult(content=list(result))
        assert result and hasattr(result[0], "text"), f"not renderable: {result!r}"
        payload = json.loads(result[0].text)

        assert payload.get("success") is False, payload
        assert payload.get("error"), payload
        # The old handler crashed before it could say anything; the new one has
        # to name the real problem, not leak the UnboundLocalError.
        assert "cannot access local variable" not in str(payload.get("error"))
        assert payload.get("hint"), payload

    def test_the_hint_points_at_the_argument(self, tmp_path):
        # "Use restore_version to undo if a snapshot was taken" is wrong twice
        # over here: nothing was written, and the fix is to the argument.
        mod = load("xlsx_basic")
        result = asyncio.run(
            mod.mcp._tool_manager.call_tool(
                "set_cell",
                {"file_path": UNRESOLVABLE[0], "sheet_name": "S", "cell_address": "A1", "value": "v"},
                convert_result=True,
            )
        )
        payload = json.loads(result[0].text)
        assert "file_path" in payload["hint"], payload["hint"]
