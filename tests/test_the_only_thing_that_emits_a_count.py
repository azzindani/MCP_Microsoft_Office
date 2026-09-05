"""Every response that reports a count reports it the same way.

`shared/counts.py` derives `truncated` from `returned` and `total` rather than
accepting one, so the flag cannot disagree with the numbers printed beside it.
The static rule below is repeated per repo on purpose: it has to read *this*
repo's source on *this* repo's CI runner, where the sibling repos do not exist.

Wiring the six emitters here turned up the same defect three times, in three
servers that had never shared a line of code:

    docx_basic.search_paragraphs   "truncated": len(matches) >= max_results
    docx_tables.search_tables      "truncated": len(matches) >= max_results
    xlsx_basic.search_cells        truncated = len(matches) >= cap

Each loop stopped *at* the cap, so `>= cap` cannot tell "exactly this many
exist" from "more exist". A document with precisely max_results matches came
back truncated, and a caller who believed it paged through nothing. Collecting
one past the cap is what makes the comparison mean something --
MCP_File_System reached the same fix from the same symptom in fs_query, which
is the argument for the shared helper rather than three more local repairs.

Two more were flags that could not be wrong because they could not vary:

* `docx_basic.read_paragraphs` returned a literal `"truncated": False`.
* `docx_basic.read_document` and `doc_diff` set `truncated` only inside their
  `if truncated:` branches, so a complete answer carried no flag at all. An
  absent flag and a False one are not the same claim.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVERS = ROOT / "servers"
SHARED = ROOT / "shared"

_HAND_WRITTEN = re.compile(r'"truncated"\s*:')
_EXEMPT = "counts-contract: composite"
_LOOKBACK = 15


def _py_files() -> list[Path]:
    files = [p for p in SERVERS.rglob("*.py") if "__pycache__" not in p.parts]
    files += [p for p in SHARED.rglob("*.py") if "__pycache__" not in p.parts]
    return [p for p in files if p.name != "counts.py"]


def test_no_module_writes_the_truncated_key_by_hand():
    offenders: list[str] = []
    for path in _py_files():
        lines = path.read_text().splitlines()
        for i, line in enumerate(lines):
            if line.strip().startswith("#"):
                continue  # modules quote the banned string while explaining it
            if not _HAND_WRITTEN.search(line):
                continue
            if _EXEMPT in "\n".join(lines[max(0, i - _LOOKBACK) : i]):
                continue
            offenders.append(f"{path.relative_to(ROOT)}:{i + 1}: {line.strip()}")
    assert not offenders, (
        "these write `truncated` by hand instead of calling counted():\n  "
        + "\n  ".join(offenders)
        + "\n\ncounted(returned, total) derives it, so the flag cannot disagree "
        "with the numbers printed beside it."
    )


def test_no_search_infers_truncation_from_reaching_its_cap():
    """`>= cap` cannot tell "exactly cap exist" from "more exist"."""
    pattern = re.compile(r"len\(matches\)\s*>=\s*(max_results|cap)\b")
    offenders: list[str] = []
    for path in _py_files():
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if pattern.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not offenders, (
        "these decide truncation by having reached a limit:\n  "
        + "\n  ".join(offenders)
        + "\n\nCollect one past the cap and compare counts instead. Stopping at "
        "the cap makes a result set of exactly that size indistinguishable from "
        "a larger one, and reports the complete answer as truncated."
    )


def test_the_searches_that_were_fixed_still_collect_one_past_the_cap():
    """Guards the shape of the fix, not only the absence of the old form."""
    checks = {
        "servers/docx_basic/docx_basic/engine.py": "len(matches) > max_results",
        "servers/docx_tables/docx_tables/engine.py": "len(matches) > max_results",
        "servers/xlsx_basic/xlsx_basic/engine.py": "len(matches) > cap",
    }
    for rel, needle in checks.items():
        src = (ROOT / rel).read_text()
        assert needle in src, f"{rel} no longer collects one past its cap"
        assert "counted(" in src, f"{rel} must report through the shared helper"
