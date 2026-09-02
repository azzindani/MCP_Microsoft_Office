"""Three tools put `table_index` beside a bare `row`, and said neither.

Calling read_table_row the way its sibling read_table reads:

    read_table_row(file_path=..., table_index=0, row_index=0)
      1 validation error for read_table_rowArguments
      row
        Field required [type=missing, ...]

`table_index` sets the expectation that a selector carries the suffix, so a
caller who has just used it writes `row_index`. pydantic refuses the call before
any of this server's code can explain, and the tool's own description was
"Return all cells in one table row." -- 34 characters naming no argument at all,
with 46 to spare. `delete_row` said "Remove row R from table N", where R and N
are defined nowhere.

The live schemas carry no property descriptions, so for these tools the
parameter name *is* the contract and the docstring is the only place it can be
written down. The names are unchanged -- renaming would break every existing
caller -- but every one of them is now stated.

A round-8 sweep phase spent three attempts on this server and produced no
report.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SERVERS = Path(__file__).parent.parent / "servers"
TABLES = SERVERS / "docx_tables" / "docx_tables" / "server.py"

# A selector that names a thing to act on, in the two shapes this repo uses.
BARE_SELECTORS = {"row", "col", "column", "slide", "para", "cell"}


def tools_in(path: Path) -> list[ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.decorator_list]


def arg_names(fn: ast.FunctionDef) -> list[str]:
    return [a.arg for a in fn.args.args]


class TestEveryTableToolNamesItsSelectors:
    @pytest.mark.parametrize(
        "tool,expected",
        [
            ("read_table_row", ["table_index", "row"]),
            ("delete_row", ["table_index", "row"]),
            ("set_cell", ["table_index", "row", "col"]),
            ("set_cell_style", ["row", "col"]),
            ("read_table", ["table_index"]),
            ("delete_table", ["table_index"]),
            ("add_row", ["table_index"]),
        ],
    )
    def test_the_docstring_names_them(self, tool: str, expected: list[str]):
        fn = next(f for f in tools_in(TABLES) if f.name == tool)
        doc = ast.get_docstring(fn) or ""
        for name in expected:
            assert name in doc, f"{tool}: {name!r} not in {doc!r}"

    @pytest.mark.parametrize("tool", ["read_table_row", "delete_row", "set_cell", "read_table", "set_cell_style"])
    def test_every_name_it_mentions_is_a_real_parameter(self, tool: str):
        """A docstring naming an argument the tool does not take is worse than
        one naming none."""
        fn = next(f for f in tools_in(TABLES) if f.name == tool)
        doc = ast.get_docstring(fn) or ""
        args = set(arg_names(fn))
        for word in ("table_index", "row_index", "col_index", "row", "col", "data", "text"):
            if word in doc:
                assert word in args, f"{tool} docstring names {word!r}, which is not a parameter"

    def test_they_all_stay_within_the_limit(self):
        for fn in tools_in(TABLES):
            doc = ast.get_docstring(fn) or ""
            assert len(doc) <= 80, (fn.name, len(doc))

    def test_each_still_says_what_the_tool_does(self):
        verbs = {
            "read_table_row": "row",
            "delete_row": "Remove",
            "set_cell": "Write",
            "add_row": "Append",
            "add_table": "Insert",
            "delete_table": "Remove",
            "read_table": "Return",
            "list_tables": "List",
            "search_table_cells": "Scan",
            "set_cell_style": "Shade",
        }
        for fn in tools_in(TABLES):
            doc = ast.get_docstring(fn) or ""
            assert verbs[fn.name] in doc, (fn.name, doc)


class TestTheClashIsConfinedToThisServer:
    def test_no_other_office_tool_mixes_the_two_shapes(self):
        """`table_index` beside a bare `row` is what makes the name a coin flip.
        If another server grows the same pair, it needs the same treatment."""
        offenders = []
        for server in sorted(SERVERS.iterdir()):
            path = server / server.name / "server.py"
            if not path.exists() or path == TABLES:
                continue
            for fn in tools_in(path):
                args = arg_names(fn)
                if any(a.endswith("_index") for a in args) and set(args) & BARE_SELECTORS:
                    offenders.append(f"{server.name}.{fn.name}({', '.join(args)})")
        assert not offenders, offenders

    def test_the_known_ones_are_still_the_only_ones_here(self):
        mixed = [
            fn.name
            for fn in tools_in(TABLES)
            if any(a.endswith("_index") for a in arg_names(fn)) and set(arg_names(fn)) & BARE_SELECTORS
        ]
        assert sorted(mixed) == ["delete_row", "read_table_row", "set_cell", "set_cell_style"], mixed
