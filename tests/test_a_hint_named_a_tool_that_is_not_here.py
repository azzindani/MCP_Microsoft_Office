"""fetch_section told the caller to run a tool this server does not have.

    fetch_section(...)
      hint: "Call replace_text() or apply_patch() to edit the paragraphs you found."

`apply_patch` is a Data_Analyst tool. It edits CSVs, it lives in a different
repository behind a different endpoint, and it has never existed on any Office
server. A caller following that half of the sentence gets "unknown tool" from
their client, or -- if they happen to have both servers connected -- points a
CSV patcher at a .docx.

The advice was written twice in the same dict: once as prose in `hint`, once as
structured `suggested_next` inside `handover`. The structured copy named
replace_text and search_paragraphs, both real, both right. Only the prose drifted,
and nothing compared them, because a hint is just a string.

This is the guard rather than the fix. The fix is one word; what was missing is
anything that could notice. So: every literal `name()` written in any `hint` in
this repo has to be a real `@mcp.tool()` somewhere in it -- repo-wide rather than
per-server, because the handover protocol deliberately points across the Office
servers, and `server=` is part of its vocabulary.

Offline, AST only. No MCP process, no network, so it runs in CI with everything
else.

Run across all four repos when this was found: 606 hint strings, one offender,
the one above.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Tools are referred to in prose with empty parentheses -- `replace_text()`.
# Requiring the empty pair keeps ordinary prose about library calls out of it:
# "scipy.special.inv_boxcox(data, lambda)" is documentation, not a claim that
# this server offers a tool by that name.
_INVOKED = re.compile(r"\b([a-z_][a-z0-9_]{2,})\(\)")

_SKIP_DIRS = {".venv", "__pycache__", "tests", "node_modules", ".git"}


def _python_files() -> list[Path]:
    return [p for p in ROOT.rglob("*.py") if not _SKIP_DIRS & set(p.parts)]


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return None


def _is_tool(node: ast.AST) -> bool:
    """A function carrying an @mcp.tool() decorator.

    Its own function, and the loops below stay loops rather than becoming
    comprehensions, so that every line here is short enough to satisfy both
    ruff configurations in the fleet: File_System sets line-length 100 and the
    others 120. A vendored file written at 120 is reformatted on sight in one
    of the four repos, and then the copies are no longer copies.
    """
    if not isinstance(node, ast.FunctionDef):
        return False
    return any("mcp.tool" in ast.unparse(dec) for dec in node.decorator_list)


def tool_names() -> set[str]:
    """Every @mcp.tool() function name in the repo."""
    found: set[str] = set()
    for path in _python_files():
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if _is_tool(node):
                found.add(node.name)  # type: ignore[attr-defined]
    return found


def _literal_text(node: ast.AST) -> str:
    """Only the parts of a hint an author actually typed.

    An f-string's `{expr}` slots are runtime values -- a column list, a path --
    and unparsing them puts helper names like `hint_for_error` into the text,
    which then read as tool references and drown the real ones.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else ""
    if isinstance(node, ast.JoinedStr):
        return "".join(_literal_text(v) for v in node.values)
    if isinstance(node, ast.BinOp):
        return _literal_text(node.left) + _literal_text(node.right)
    return ""


def hints() -> list[tuple[str, str]]:
    """(location, text) for every literal `"hint"` value in the repo."""
    out: list[tuple[str, str]] = []
    for path in _python_files():
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "hint":
                    text = _literal_text(value)
                    if text:
                        out.append((f"{path.relative_to(ROOT)}:{key.lineno}", text))
    return out


class TestEveryHintNamesARealTool:
    def test_the_scan_found_something_to_check(self) -> None:
        """A guard that reads nothing passes for the wrong reason.

        Deliberately a floor rather than an exact count: this file is vendored
        into four repos that have between 6 and 88 tools, and a threshold tuned
        to one of them is a threshold that has to be edited in the other three.
        """
        assert len(tool_names()) >= 5, "no @mcp.tool() functions found — the scan is broken"
        assert len(hints()) >= 5, "no hint strings found — the scan is broken"

    def test_no_hint_names_a_tool_this_repo_does_not_have(self) -> None:
        real = tool_names()
        offenders = []
        for loc, text in hints():
            for name in sorted(set(_INVOKED.findall(text))):
                if name not in real:
                    offenders.append(f"{name}() at {loc}")
        assert not offenders, "hints naming tools that do not exist here: " + "; ".join(offenders)


class TestTheGuardCanFail:
    """Both halves of it, on text built to break each one."""

    def test_a_made_up_tool_is_caught(self) -> None:
        assert set(_INVOKED.findall("Call frobnicate() next.")) == {"frobnicate"}
        assert "frobnicate" not in tool_names()

    def test_a_real_tool_is_not(self) -> None:
        """Taken from the scan, not hard-coded, so the file vendors unchanged."""
        some_tool = sorted(tool_names())[0]
        assert _INVOKED.findall(f"Call {some_tool}() next.") == [some_tool]
        assert some_tool in tool_names()

    def test_a_library_call_with_arguments_is_not_a_tool_claim(self) -> None:
        assert _INVOKED.findall("Store lambda: scipy.special.inv_boxcox(data, lam).") == []

    def test_an_f_string_slot_is_not_read_as_prose(self) -> None:
        tree = ast.parse('x = {"hint": f"Available: {sorted(cols)}. Use some_tool()."}')
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.Dict))
        text = _literal_text(node.values[0])
        assert "sorted" not in text, text
        assert "some_tool()" in text
