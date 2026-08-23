"""A write a reader cannot see is a hole in the audit trail.

read_receipt and get_history both read one per-file log. Two writes on this
server never reached it:

    append_text      the only edit tool that logged nothing, while
                     insert_paragraph, delete_paragraph and replace_text all did
    restore_version  which replaces the document's entire contents

The second is the one that matters. A reader asking read_receipt "what happened
to this file?" saw every edit and no sign that any of them had since been
rolled back -- the log described a document that no longer existed.

Found by asking which functions take a snapshot but never write a receipt: 39
of 93 across the four repos, of which the ones worth fixing are those a receipt
*reader* exists to expose.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "shared"), str(ROOT / "servers" / "docx_basic"), str(ROOT / "servers" / "docx_new")):
    if p not in sys.path:
        sys.path.insert(0, p)

from docx_basic import engine  # noqa: E402
from docx_new import engine as docx_new  # noqa: E402


def logged(doc: Path) -> list[str]:
    # Through read_receipt_log(), which is what the read_receipt tool calls:
    # what matters is not that a line reached a file but that the reader shows
    # it. (The log is stem-named here, d.mcp_receipt.json, where File_System
    # uses the full filename — one more reason not to open it by hand.)
    from shared.receipt import read_receipt_log

    return [str(e.get("tool")) for e in read_receipt_log(str(doc), last_n=50)]


@pytest.fixture
def doc(tmp_path):
    p = tmp_path / "d.docx"
    r = docx_new.create_from_text(
        str(p),
        [{"text": "one", "style": "Body Text"}, {"text": "two", "style": "Body Text"}],
        open_after=False,
    )
    assert r["success"] is True, r.get("error")
    return p


class TestEveryEditIsLogged:
    def test_append_text_is_logged_like_its_siblings(self, doc):
        assert engine.append_text(str(doc), "three")["success"] is True
        assert "append_text" in logged(doc)

    def test_the_log_holds_every_edit_in_order(self, doc):
        engine.append_text(str(doc), "three")
        engine.insert_paragraph(str(doc), 0, "zero")
        engine.replace_text(str(doc), "two", "TWO")
        assert logged(doc) == ["append_text", "insert_paragraph", "replace_text"]


class TestARestoreIsLogged:
    def test_rolling_back_leaves_a_trace(self, doc):
        engine.append_text(str(doc), "three")
        hist = engine.get_history_tool(str(doc))
        versions = hist.get("versions") or hist.get("history") or []
        assert versions, hist
        ts = versions[0].get("timestamp")
        assert ts, versions[0]

        r = engine.restore_version(str(doc), ts)
        assert r["success"] is True, r.get("error")

        entries = logged(doc)
        assert "restore_version" in entries, entries
        # The append must still be there: a restore adds to the history, it
        # does not replace it.
        assert entries.index("append_text") < entries.index("restore_version")
