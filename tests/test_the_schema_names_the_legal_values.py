"""The schema names the legal values now, and must keep naming the real ones.

Round 28 censused the fleet and found 55 parameters whose only job is to select
behaviour and not one that declared an `enum`, so every legal value lived in
prose. The runtime side was fixed that round; this is the schema side.

The enum ADVERTISES rather than enforces -- `shared/schema_enum.py` sets out why
`Literal` is the wrong mechanism here, in one sentence: it would make pydantic
reject a value before the tool body runs, which costs the aliases and the
refusals this fleet has spent twenty-eight rounds building.

That is precisely why the last test matters: an advertised set can lie, and must
not. Every value the schema names has to be a value the tool takes.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DISPATCH = re.compile(
    r"^(action|mode|method|agg_func|chart_type|how|direction|normalize|format|format_|task|model|"
    r"model_type|models|algorithm|op|test|test_type|period_unit|rule|validation_type|to|type_?|"
    r"style)$"
)

NO_ENUM_IS_CORRECT: dict[str, str] = {
    # A .docx carries its own style set: the stock template defines about a
    # hundred and a caller's template can define any name it likes. Naming a
    # fixed list here would be this repo asserting something about a document
    # it has not opened. `resolve_style` reads the real set at call time and
    # the refusal lists it.
    "office-docx-basic/append_text.style": "the document defines its own styles",
    "office-docx-basic/insert_paragraph.style": "the document defines its own styles",
}


def _dispatch_params():
    from servers.docx_basic.docx_basic import server as docx_basic
    from servers.pptx_design.pptx_design import server as pptx_design
    from servers.xlsx_charts.xlsx_charts import server as xlsx_charts
    from servers.xlsx_formulas.xlsx_formulas import server as xlsx_formulas

    for app, label in [
        (docx_basic.mcp, "office-docx-basic"),
        (pptx_design.mcp, "office-pptx-design"),
        (xlsx_charts.mcp, "office-xlsx-charts"),
        (xlsx_formulas.mcp, "office-xlsx-formulas"),
    ]:
        for tool in asyncio.run(app.list_tools()):
            props = (tool.inputSchema or {}).get("properties") or {}
            for param, spec in props.items():
                if DISPATCH.match(param):
                    # A list parameter carries its enum on the ITEM schema --
                    # `models: list[one_of(...)]` -- so that is where to look.
                    if spec.get("type") == "array" and isinstance(spec.get("items"), dict):
                        spec = spec["items"]
                    yield f"{label}/{tool.name}.{param}", spec


def test_the_census_finds_them():
    found = list(_dispatch_params())
    assert len(found) >= 4, f"only {len(found)} dispatch parameters seen -- did the census break?"


def test_none_is_left_undeclared():
    missing = [k for k, spec in _dispatch_params() if "enum" not in spec and k not in NO_ENUM_IS_CORRECT]
    assert not missing, (
        f"{len(missing)} dispatch parameter(s) still name no values: {missing}. "
        "Add the enum with shared.schema_enum.one_of, or list it in NO_ENUM_IS_CORRECT "
        "with the reason it cannot have one."
    )


def test_the_exceptions_are_still_real():
    """An exception that no longer exists is a stale excuse."""
    seen = {k for k, _ in _dispatch_params()}
    stale = [k for k in NO_ENUM_IS_CORRECT if k not in seen]
    assert not stale, f"NO_ENUM_IS_CORRECT names parameters that are gone: {stale}"


def test_no_enum_is_empty_or_repeats_itself():
    for key, spec in _dispatch_params():
        values = spec.get("enum")
        if values is None:
            continue
        assert values, f"{key} declares an empty enum"
        assert len(values) == len(set(values)), f"{key} repeats a value: {values}"


def test_a_default_is_one_of_the_declared_values():
    for key, spec in _dispatch_params():
        values, default = spec.get("enum"), spec.get("default")
        if not values or default in (None, ""):
            continue
        assert default in values, f"{key} defaults to {default!r}, which its enum does not list"
