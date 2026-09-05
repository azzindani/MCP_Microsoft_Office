"""A declared capability nobody implements burns a loop every time it is tried.

The review's §3.3:

    `folio_templates list` is a dead feature. Returns "catalog asset dir/index
    was not located on the server," 0 templates. Room for improvement: fix the
    index or remove the op. **A dead op burns a loop iteration every time an
    agent reasonably tries it.**

That specific op belongs to Folio, which is not one of these repos. The
principle is not Folio's, and the shape it takes here is a *block kind*: the
tool description names the kinds it accepts, and an agent will send exactly what
it is told to send. Three lists have to agree, and nothing made them:

* `BLOCK_KINDS`, which the validator checks a block against;
* the `elif kind == ...` chain, which is what actually draws something;
* the tool docstring, which is the only one the agent ever sees.

A kind in the first two and missing from the third is invisible. A kind in the
first and third with no branch in the second is worse: it validates, draws
nothing, is counted as written, and the caller gets a document quietly missing a
section. That is the dead op, wearing a different hat.

`image` was added the day this file was written, which is exactly when the three
lists are easiest to leave disagreeing.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

from servers.docx_new.docx_new import engine
from servers.docx_new.docx_new.engine import BLOCK_KINDS, create_from_blocks

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "servers/docx_new/docx_new/engine.py"
SERVER = ROOT / "servers/docx_new/docx_new/server.py"


def _drawn_kinds() -> set[str]:
    """Kinds the render loop actually has a branch for, read from the source."""
    src = ENGINE.read_text(encoding="utf-8")
    return set(re.findall(r'kind\s*==\s*"([a-z_]+)"', src))


def test_every_declared_kind_is_drawn():
    """The dead-op shape: it validates, draws nothing, and is counted anyway."""
    missing = sorted(set(BLOCK_KINDS) - _drawn_kinds())
    assert not missing, (
        f"these kinds are accepted by the validator and have no branch that draws them: {missing}. "
        "A block like that is written as nothing, counted as written, and leaves the caller a "
        "document quietly missing a section."
    )


def test_nothing_is_drawn_that_is_not_declared():
    """The other direction: a branch nobody can reach, because validation refuses it first."""
    extra = sorted(_drawn_kinds() - set(BLOCK_KINDS))
    assert not extra, f"these have a render branch but are refused by the validator: {extra}"


def _tool_doc(name: str) -> str:
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_docstring(node) or ""
    return ""


def test_every_kind_is_discoverable_from_the_tool_surface():
    """An agent sends what it is told to send.

    This used to demand that the description name every kind. Twelve kinds do
    not fit in eighty characters, and the cap below is not negotiable either --
    every client pays for that string on every tools/list. The review's own
    scaling section resolves it: *"Never list 1000: expose
    `search/get_capabilities/get_state`, sparse outline then detail"*. So the
    description points at `list_block_kinds`, and that is where the list has to
    be complete.
    """
    doc = _tool_doc("create_from_blocks")
    assert doc, "create_from_blocks has no docstring, so its kinds are undiscoverable"
    assert "list_block_kinds" in doc, (
        "the description neither names the kinds nor points at what does, so an agent "
        "reading tools/list cannot find out that `risks` exists"
    )
    assert _tool_doc("list_block_kinds"), "the tool the description points at does not exist"

    listed = {entry["kind"] for entry in engine.list_block_kinds()["kinds"]}
    assert listed == set(BLOCK_KINDS), listed.symmetric_difference(BLOCK_KINDS)


def test_the_discovery_op_carries_enough_to_call_with():
    """A list of names an agent still has to guess the arguments for is half an answer."""
    for entry in engine.list_block_kinds()["kinds"]:
        assert entry["does"], f"{entry['kind']} has no description"
        assert entry["example"].get("kind") == entry["kind"], entry
        # `rule` and `pagebreak` genuinely take nothing; everything else must
        # say what it needs.
        if entry["kind"] not in ("rule", "pagebreak"):
            assert entry["keys"], f"{entry['kind']} lists no keys"


def test_the_kinds_cannot_drift_from_the_specs():
    """One list, not two: BLOCK_KINDS is derived, so disagreement is unrepresentable."""
    assert BLOCK_KINDS == tuple(engine.BLOCK_KIND_SPECS)


def test_every_example_in_the_discovery_op_actually_renders(tmp_path):
    """The example is a promise. An example that does not work is a dead op with a manual."""
    examples = [entry["example"] for entry in engine.list_block_kinds()["kinds"]]
    # The image example points at a path that does not exist here; every other
    # kind must draw from its own documented example unchanged.
    drawable = [e for e in examples if e["kind"] != "image"]
    out = tmp_path / "examples.docx"
    r = create_from_blocks(str(out), "T", drawable, open_after=False)
    assert r["success"] is True
    assert r["skipped"] == [], r["skipped"]
    assert r["block_count"] == len(drawable)


def test_the_description_still_fits_the_cap():
    """Adding a kind must not smuggle a long description past the gate."""
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "create_from_blocks":
            doc = ast.get_docstring(node) or ""
            assert len(doc) <= 80, f"{len(doc)} chars: {doc!r}"


def test_an_unknown_kind_is_refused_with_the_valid_list(tmp_path):
    """The refusal has to carry the answer, or it costs the loop it saved."""
    out = tmp_path / "d.docx"
    r = create_from_blocks(str(out), "T", [{"kind": "chart"}], open_after=False)
    assert r["success"] is True
    assert r["skipped"], "an unrecognised kind must be reported, not dropped"
    warned = " ".join(str(p) for p in r["progress"])
    for kind in BLOCK_KINDS:
        assert kind in warned, f"the valid list in the warning omits {kind}"


def test_every_kind_actually_produces_something(tmp_path):
    """Exercised, not just declared -- the census above reads source, this runs it."""
    blocks = [
        {"kind": "heading", "text": "H"},
        {"kind": "text", "text": "body"},
        {"kind": "bullets", "items": ["a", "b"]},
        {"kind": "table", "header": ["c1"], "rows": [["v"]]},
        {"kind": "kpi", "items": [{"label": "Rate", "value": "13.8%"}]},
        {"kind": "callout", "text": "note"},
        {"kind": "links", "items": [{"label": "Chart", "url": "https://example.test/c.html"}]},
        {"kind": "risks", "items": [{"risk": "Leakage", "level": "high"}]},
        {"kind": "checklist", "items": [{"text": "Drop id", "done": True}]},
        {"kind": "rule"},
        {"kind": "pagebreak"},
    ]
    assert {b["kind"] for b in blocks} | {"image"} == set(BLOCK_KINDS), (
        "a kind was added without a case here; image is covered in the sibling file"
    )
    out = tmp_path / "all.docx"
    r = create_from_blocks(str(out), "T", blocks, open_after=False)
    assert r["success"] is True
    assert r["skipped"] == [], r["skipped"]
    assert r["block_count"] == len(blocks)


def test_the_engine_and_the_wrapper_agree_on_the_signature():
    """A parameter the wrapper drops is a capability the agent cannot reach."""
    engine_params = set(inspect.signature(engine.create_from_blocks).parameters)
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "create_from_blocks":
            wrapper = {a.arg for a in node.args.args}
            # open_after is set by the wrapper rather than exposed; everything
            # else the engine takes should be reachable.
            assert engine_params - wrapper <= {"open_after"}, engine_params - wrapper
