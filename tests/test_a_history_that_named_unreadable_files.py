"""get_history handed back paths the tool family refused to open.

    get_history(report.docx)
      -> [{"timestamp": "2026-08-26T11-32-50-330732Z",
           "backup_path": ".../.mcp_versions/report_....docx.bak",
           "size_bytes": 37086}, ...]

    read_document(".../.mcp_versions/report_....docx.bak")
      -> "Path '...' is inside .mcp_versions/. Pass the original document
          path, not a backup path."

Every history entry names a backup_path, and resolve_path refuses exactly those
paths -- so the history advertised files nothing in the family would read back.
A round-16 phase followed that through and stopped there: to look at an earlier
version you had either to restore_version (which makes it the current file) or
copy the .bak out by hand.

The guard itself is right. Writing to a backup snapshots the snapshot, and
resolve_path is shared by every read *and* write tool, so it cannot tell one
from the other. What was wrong is that the message said only what not to pass.
Snapshots are addressed by timestamp plus the original path -- get_history
lists the timestamps, and restore_version and diff_versions both take one --
and the error never mentioned it.

So the fix is a sentence, not a new capability: name the addressing scheme the
tools already use. The test below refuses to take that on trust and drives the
whole route -- edit, get_history, diff_versions on the timestamp -- because a
hint pointing somewhere that does not work is worse than no hint at all.
"""

from __future__ import annotations

from pathlib import Path

import docx
import pytest

from docx_basic import engine as dbe  # type: ignore[reportMissingImports]
from docx_basic import helpers as H  # type: ignore[reportMissingImports]
from shared.file_utils import resolve_path  # type: ignore[reportMissingImports]


@pytest.fixture()
def edited_doc(tmp_path: Path) -> Path:
    """A document with one snapshot behind it."""
    doc = tmp_path / "report.docx"
    d = docx.Document()
    d.add_paragraph("first line")
    d.save(str(doc))
    r = dbe.append_text(str(doc), "second line")
    assert r["success"] is True, r.get("error")
    return doc


class TestTheHistoryStillNamesTheBackup:
    """The setup for the confusion, and it is deliberate -- keep it working."""

    def test_history_has_an_entry_with_a_backup_path(self, edited_doc: Path) -> None:
        history = H.get_history(str(edited_doc))
        assert history, "no snapshot was recorded"
        assert ".mcp_versions" in history[0]["backup_path"]

    def test_that_very_path_is_still_refused(self, edited_doc: Path) -> None:
        """The guard is correct: a write to a backup snapshots the snapshot."""
        backup = H.get_history(str(edited_doc))[0]["backup_path"]
        with pytest.raises(ValueError):
            resolve_path(backup)


class TestTheRefusalNowNamesTheRoute:
    def _message(self, doc: Path) -> str:
        """The advice, with the echoed path taken out.

        pytest names tmp_path after the test function, so the backup path in
        this message contains the test's own name. Asserting "get_history"
        against the raw string matched the *directory*, not the advice, and
        passed cleanly against a message that never mentioned get_history at
        all. Strip the path so the assertions can only see the sentence.
        """
        backup = H.get_history(str(doc))[0]["backup_path"]
        with pytest.raises(ValueError) as exc:
            resolve_path(backup)
        return str(exc.value).replace(backup, "<backup>")

    def test_it_says_versions_are_addressed_by_timestamp(self, edited_doc: Path) -> None:
        assert "addressed by timestamp" in self._message(edited_doc)

    def test_it_names_get_history(self, edited_doc: Path) -> None:
        assert "get_history" in self._message(edited_doc)

    def test_it_names_both_tools_that_take_a_timestamp(self, edited_doc: Path) -> None:
        msg = self._message(edited_doc)
        assert "restore_version" in msg and "diff_versions" in msg, msg

    def test_it_gives_an_escape_hatch_for_opening_the_bak(self, edited_doc: Path) -> None:
        """Not every server has diff_versions; copying out always works."""
        assert "copy it outside" in self._message(edited_doc)


class TestTheRouteItNamesActuallyWorks:
    """A hint pointing somewhere that fails would be worse than none."""

    def test_a_history_timestamp_drives_diff_versions(self, edited_doc: Path) -> None:
        entry = H.get_history(str(edited_doc))[0]
        result = H.diff_versions(str(edited_doc), timestamp_a=entry["timestamp"])
        assert result["success"] is True, result.get("error")

    def test_the_diff_reaches_both_versions(self, edited_doc: Path) -> None:
        """Proof it really read the snapshot, not just the current file."""
        entry = H.get_history(str(edited_doc))[0]
        result = H.diff_versions(str(edited_doc), timestamp_a=entry["timestamp"])
        assert result["paragraph_count_a"] != result["paragraph_count_b"], result
        assert result["change_count"] >= 1, result

    def test_the_original_path_is_what_diff_versions_takes(self, edited_doc: Path) -> None:
        """The message says original path + timestamp; confirm that is the shape."""
        entry = H.get_history(str(edited_doc))[0]
        assert H.diff_versions(str(edited_doc), timestamp_a=entry["timestamp"])["success"] is True
        # and the backup path itself is not the argument
        with pytest.raises(ValueError):
            resolve_path(entry["backup_path"])
