"""Verify that all @mcp.tool() docstrings are <= 80 characters."""

import ast
import pathlib
import sys

errors = []
for f in pathlib.Path("servers").rglob("server.py"):
    tree = ast.parse(f.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            has_tool = any(
                (isinstance(d, ast.Attribute) and d.attr == "tool")
                or (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "tool")
                for d in node.decorator_list
            )
            if has_tool:
                doc = ast.get_docstring(node) or ""
                if len(doc) > 80:
                    errors.append(f"{f}:{node.lineno} {node.name}: {len(doc)} chars > 80")

if errors:
    print("Tool docstring violations:")
    for e in errors:
        print(" ", e)
    sys.exit(1)
else:
    print("All tool docstrings within 80 char limit.")
