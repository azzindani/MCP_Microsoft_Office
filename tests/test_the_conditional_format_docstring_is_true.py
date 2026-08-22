"""set_conditional_format rejected the rule names its own docstring gives.

The tool description is

    Apply color rule to range. rule: gt/lt/between/eq. color: green/red/yellow/blue.

and the tool answered `rule="gt"` with:

    error: Unknown rule: gt
    hint:  Allowed rules: between, equal_to, greater_than, less_than

A coverage sweep hit it exactly that way and needed a retry. The schema for this
tool carries no enum and no per-parameter description -- properties are bare
{"type": "string"} -- so the docstring is the whole contract, and this one named
three values that did not work.

Correcting the docstring instead would mean dropping something: "greater_than
less_than between equal_to" plus the four colour names does not fit in the
80-character limit the standards impose, which is why the rules were
abbreviated in the first place. So the short forms are accepted rather than the
colours going undocumented. auto_sum, in the same server, already normalises its
own function_name for the same reason.

The response echoes the canonical name, so a caller who sends "gt" is told which
rule was actually applied.
"""

from __future__ import annotations

import re
from pathlib import Path

import openpyxl
import pytest

from xlsx_formulas.engine import VALID_COLORS, set_conditional_format  # type: ignore[reportMissingImports]
from xlsx_formulas.server import set_conditional_format as tool  # type: ignore[reportMissingImports]

CANONICAL = {"gt": "greater_than", "lt": "less_than", "eq": "equal_to", "between": "between"}


@pytest.fixture()
def book(tmp_path: Path) -> str:
    path = tmp_path / "book.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Spend"
    ws.append(["Platform", "Spend"])
    ws.append(["Google Ads", 1939000])
    ws.append(["Facebook Ads", 564100])
    wb.save(str(path))
    return str(path)


def documented(kind: str) -> list[str]:
    """Read a vocabulary out of the docstring the caller actually sees."""
    doc = tool.__doc__ or ""
    body = re.search(rf"{kind}:\s*([^.]+)\.", doc)
    assert body, doc
    return [v.strip() for v in body.group(1).replace(",", "/").split("/") if v.strip()]


class TestEveryRuleTheDocstringNamesWorks:
    @pytest.mark.parametrize("rule", ["gt", "lt", "between", "eq"])
    def test_it_is_accepted(self, book: str, rule: str):
        r = set_conditional_format(book, "Spend", "B2:B3", rule, 100000.0, "green", 2000000.0)
        assert r["success"] is True, f"{rule}: {r.get('error')} / {r.get('hint')}"

    @pytest.mark.parametrize("rule", ["gt", "lt", "between", "eq"])
    def test_the_response_says_which_rule_was_applied(self, book: str, rule: str):
        r = set_conditional_format(book, "Spend", "B2:B3", rule, 100000.0, "green", 2000000.0)
        assert r["rule"] == CANONICAL[rule], r["rule"]

    @pytest.mark.parametrize("rule", ["gt", "lt", "between", "eq"])
    def test_the_rule_reaches_the_file(self, book: str, rule: str):
        set_conditional_format(book, "Spend", "B2:B3", rule, 100000.0, "green", 2000000.0)
        wb = openpyxl.load_workbook(book)
        rules = [r for rng in wb["Spend"].conditional_formatting for r in rng.rules]
        assert len(rules) == 1, rules

    def test_the_docstring_vocabulary_has_not_moved(self):
        """If the docstring is reworded, the list above must move with it."""
        assert documented("rule") == ["gt", "lt", "between", "eq"], documented("rule")


class TestEveryColourTheDocstringNamesWorks:
    @pytest.mark.parametrize("color", ["green", "red", "yellow", "blue"])
    def test_it_is_accepted(self, book: str, color: str):
        r = set_conditional_format(book, "Spend", "B2:B3", "gt", 100000.0, color)
        assert r["success"] is True, f"{color}: {r.get('error')}"

    def test_the_docstring_names_exactly_the_supported_colours(self):
        assert sorted(documented("color")) == sorted(VALID_COLORS), documented("color")


class TestTheCanonicalNamesStillWork:
    @pytest.mark.parametrize("rule", ["greater_than", "less_than", "between", "equal_to"])
    def test_they_are_unchanged(self, book: str, rule: str):
        r = set_conditional_format(book, "Spend", "B2:B3", rule, 100000.0, "red", 2000000.0)
        assert r["success"] is True, f"{rule}: {r.get('error')}"


class TestSomethingThatIsNotARuleIsStillRejected:
    @pytest.mark.parametrize("rule", ["greater", "GT", "", "!="])
    def test_it_fails(self, book: str, rule: str):
        assert set_conditional_format(book, "Spend", "B2:B3", rule, 1.0, "green")["success"] is False

    def test_the_hint_names_both_spellings(self, book: str):
        hint = set_conditional_format(book, "Spend", "B2:B3", "greater", 1.0, "green")["hint"]
        assert "greater_than (gt)" in hint, hint

    def test_the_error_is_not_empty(self, book: str):
        r = set_conditional_format(book, "Spend", "B2:B3", "greater", 1.0, "green")
        assert r["error"].strip() not in ("", "''", '""')
