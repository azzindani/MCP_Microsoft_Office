"""Every tool this repo registers must appear in the README.

Cutting this release meant counting the tools by hand, and the README was wrong
in four repos at once: Data_Analyst said 71 and had 72, Office said 98 and had
99, File_System said 6 and had 7, and Web_Browser's total was right while its
per-tier breakdown was wrong twice in ways that cancelled out. Each README was
written true and went stale the moment a tool was added, because nothing was
checking.

The check is deliberately a source scan rather than an import: it needs no
server to start and no optional dependency installed, and it sees the tools
where they are declared. A tool missing from the README is a tool a caller
cannot discover without calling `tools/list` and guessing.
"""

from __future__ import annotations

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
GLOBS = ("servers/*/*/server.py",)
DECORATORS = ("mcp.tool", "app.tool")


def registered_tools() -> list[str]:
    names: list[str] = []
    for glob in GLOBS:
        for path in sorted(REPO.glob(glob)):
            if ".venv" in path.parts or "tests" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for decorator in node.decorator_list:
                    if ast.unparse(decorator).startswith(DECORATORS):
                        names.append(node.name)
                        break
    return names


class TestTheReadmeDocumentsEveryTool:
    def test_the_scan_finds_them(self):
        found = registered_tools()
        assert len(found) == 99, (
            f"{len(found)} tools registered, expected 99. If a tool was added or "
            "removed, update this number AND the counts in README.md -- they are the "
            "thing this file exists to keep honest."
        )

    def test_none_is_undocumented(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        missing = sorted({name for name in registered_tools() if name not in readme})
        assert not missing, f"registered but absent from README.md: {missing}"
