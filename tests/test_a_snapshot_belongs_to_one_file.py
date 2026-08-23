"""One document's history must not be offered as another document's.

Two records are kept beside every file these servers edit, and both were named
for the file's *stem*:

    .mcp_versions/{stem}_{timestamp}.bak
    {stem}.mcp_receipt.json

A report built as report.docx, report.xlsx and report.pptx in one folder -- the
ordinary shape of a piece of work on these eleven servers -- therefore had one
snapshot history and one audit trail between all three. Proved against the live
endpoints with a CSV and a Word document sharing a stem: restoring the CSV with
no timestamp returned the newest snapshot under that stem, which was the .docx,
and answered success: true. 12 bytes of CSV came back as 37,117 bytes of Word
document.

The receipt name had a second consequence. All three sibling repos write
`{filename}.mcp_receipt.json`, so an Office edit was invisible to a File_System
or Data_Analyst read_receipt on the same document -- they looked for
`report.docx.mcp_receipt.json` and Office had written `report.mcp_receipt.json`.
Office was the odd one out of four.

Reading stays more forgiving than writing so nothing already on disk is
stranded, but only where the old name cannot be ambiguous.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"
for _p in (str(ROOT), str(SHARED)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shared.receipt import append_receipt, read_receipt_log  # noqa: E402
from shared.version_control import get_history, restore, snapshot  # noqa: E402


def pair(tmp_path: Path) -> tuple[Path, Path]:
    docx = tmp_path / "report.docx"
    docx.write_bytes(b"PK\x03\x04" + b"d" * 200)
    xlsx = tmp_path / "report.xlsx"
    xlsx.write_bytes(b"PK\x03\x04" + b"x" * 900)
    return docx, xlsx


class TestTheExtensionIsPartOfTheSnapshotName:
    def test_two_namesakes_do_not_share_a_history(self, tmp_path):
        docx, xlsx = pair(tmp_path)
        snapshot(str(docx))
        snapshot(str(xlsx))
        assert len(get_history(str(docx))) == 1, get_history(str(docx))
        assert len(get_history(str(xlsx))) == 1, get_history(str(xlsx))

    def test_restoring_a_docx_does_not_hand_back_the_xlsx(self, tmp_path):
        docx, xlsx = pair(tmp_path)
        original = docx.read_bytes()
        snapshot(str(docx))
        snapshot(str(xlsx))
        docx.write_bytes(b"PK\x03\x04edited")
        newest = get_history(str(docx))[0]["timestamp"]
        assert restore(str(docx), newest) is True
        assert docx.read_bytes() == original

    def test_a_longer_name_is_not_a_version_of_a_shorter_one(self, tmp_path):
        base = tmp_path / "report.docx"
        base.write_bytes(b"PK\x03\x04a")
        other = tmp_path / "report_final.docx"
        other.write_bytes(b"PK\x03\x04b")
        snapshot(str(other))
        assert get_history(str(base)) == []
        assert len(get_history(str(other))) == 1

    def test_the_timestamp_does_not_carry_the_extension(self, tmp_path):
        docx, _ = pair(tmp_path)
        snapshot(str(docx))
        ts = get_history(str(docx))[0]["timestamp"]
        assert "." not in ts and ts.startswith("20"), ts


class TestOlderSnapshotsAreStillReachable:
    def test_a_legacy_snapshot_is_listed_when_nothing_shares_the_stem(self, tmp_path):
        docx = tmp_path / "solo.docx"
        docx.write_bytes(b"PK\x03\x04new")
        versions = tmp_path / ".mcp_versions"
        versions.mkdir()
        (versions / "solo_2026-08-01T00-00-00-000000Z.bak").write_bytes(b"PK\x03\x04old")
        assert len(get_history(str(docx))) == 1

    def test_a_legacy_snapshot_still_restores(self, tmp_path):
        docx = tmp_path / "solo.docx"
        docx.write_bytes(b"PK\x03\x04new")
        versions = tmp_path / ".mcp_versions"
        versions.mkdir()
        (versions / "solo_2026-08-01T00-00-00-000000Z.bak").write_bytes(b"PK\x03\x04old")
        assert restore(str(docx), "2026-08-01T00-00-00-000000Z") is True
        assert docx.read_bytes() == b"PK\x03\x04old"

    def test_a_legacy_snapshot_is_withheld_when_a_namesake_exists(self, tmp_path):
        docx, _ = pair(tmp_path)
        versions = tmp_path / ".mcp_versions"
        versions.mkdir()
        (versions / "report_2026-08-01T00-00-00-000000Z.bak").write_bytes(b"?")
        # Ambiguous: it could be either document's.
        assert get_history(str(docx)) == []
        assert restore(str(docx), "2026-08-01T00-00-00-000000Z") is False


class TestTheReceiptIsNamedForTheWholeFilename:
    def test_two_namesakes_keep_separate_logs(self, tmp_path):
        docx, xlsx = pair(tmp_path)
        append_receipt(str(docx), tool="set_font", server="docx_layout")
        append_receipt(str(xlsx), tool="sort_sheet", server="xlsx_basic")
        docx_tools = [e["tool"] for e in read_receipt_log(str(docx))]
        xlsx_tools = [e["tool"] for e in read_receipt_log(str(xlsx))]
        assert docx_tools == ["set_font"], docx_tools
        assert xlsx_tools == ["sort_sheet"], xlsx_tools

    def test_the_log_is_where_the_sibling_repos_look_for_it(self, tmp_path):
        docx, _ = pair(tmp_path)
        append_receipt(str(docx), tool="set_font")
        assert (tmp_path / "report.docx.mcp_receipt.json").exists()

    def test_the_log_names_the_file_it_belongs_to(self, tmp_path):
        docx, xlsx = pair(tmp_path)
        append_receipt(str(docx), tool="set_font")
        append_receipt(str(xlsx), tool="sort_sheet")
        import json

        data = json.loads((tmp_path / "report.xlsx.mcp_receipt.json").read_text(encoding="utf-8"))
        assert data["file"] == "report.xlsx"


class TestOlderReceiptsAreStillReadable:
    def test_a_legacy_log_is_read_when_nothing_shares_the_stem(self, tmp_path):
        import json

        docx = tmp_path / "solo.docx"
        docx.write_bytes(b"PK\x03\x04")
        legacy = tmp_path / "solo.mcp_receipt.json"
        legacy.write_text(
            json.dumps({"file": "solo.docx", "entries": [{"tool": "append_text"}]}),
            encoding="utf-8",
        )
        assert [e["tool"] for e in read_receipt_log(str(docx))] == ["append_text"]

    def test_a_legacy_log_is_carried_forward_on_the_next_write(self, tmp_path):
        import json

        docx = tmp_path / "solo.docx"
        docx.write_bytes(b"PK\x03\x04")
        (tmp_path / "solo.mcp_receipt.json").write_text(
            json.dumps({"file": "solo.docx", "entries": [{"tool": "append_text"}]}),
            encoding="utf-8",
        )
        append_receipt(str(docx), tool="set_font")
        tools = [e["tool"] for e in read_receipt_log(str(docx))]
        assert tools == ["append_text", "set_font"], tools

    def test_a_legacy_log_is_withheld_when_a_namesake_exists(self, tmp_path):
        import json

        docx, _ = pair(tmp_path)
        (tmp_path / "report.mcp_receipt.json").write_text(
            json.dumps({"file": "?", "entries": [{"tool": "append_text"}]}),
            encoding="utf-8",
        )
        assert read_receipt_log(str(docx)) == []
