"""Writing a new document over an existing one must leave a way back.

The three `*_new` servers -- nineteen tools between them -- never called
snapshot(), while every editing tool on the same eleven servers snapshots before
it writes. So the one operation with no undo was the one annotated
destructiveHint: False, and it is exactly the retry case. Against the live
endpoints:

    create_document(output_path="plan.docx")      -> success
    append_text("plan.docx", "IRREPLACEABLE ...") -> success, 1 snapshot
    create_document(output_path="plan.docx")      -> success

    36,626 bytes -> 36,563 bytes, the paragraph gone, still 1 snapshot

A client whose create call times out and re-sends it discards whatever was
written in between, with nothing in .mcp_versions to recover from and
success: true on both calls.

The fix keeps the overwrite -- regenerating a report over its own path is
ordinary and refusing it would break every re-run -- and restores the safety
net every other write on these servers already had. It sits in
resolve_output_path because all 24 callers write to what it returns, so a
nineteenth-and-first tool cannot forget it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"
for _p in (str(ROOT), str(SHARED)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shared.platform_utils import resolve_output_path  # noqa: E402
from shared.version_control import get_history  # noqa: E402


def load(name: str):
    import importlib

    pkg = ROOT / "servers" / name / name
    if str(pkg.parent) not in sys.path:
        sys.path.insert(0, str(pkg.parent))
    return importlib.import_module(f"{name}.server")


class TestTheResolverSnapshotsWhatItIsAboutToReplace:
    def test_an_existing_file_is_snapshotted(self, tmp_path):
        target = tmp_path / "plan.docx"
        target.write_bytes(b"PK\x03\x04original")
        resolve_output_path(str(target), "document.docx")
        history = get_history(str(target))
        assert len(history) == 1, history
        assert Path(history[0]["backup_path"]).read_bytes() == b"PK\x03\x04original"

    def test_a_new_path_snapshots_nothing(self, tmp_path):
        target = tmp_path / "fresh.docx"
        resolve_output_path(str(target), "document.docx")
        assert get_history(str(target)) == []
        assert not (tmp_path / ".mcp_versions").exists()

    def test_the_resolved_path_is_unchanged(self, tmp_path):
        target = tmp_path / "plan.docx"
        target.write_bytes(b"PK\x03\x04")
        assert resolve_output_path(str(target), "document.docx") == target.resolve()

    def test_a_directory_in_the_way_is_not_snapshotted(self, tmp_path):
        # is_file() rather than exists(): a directory at the path is the
        # caller's problem to report, not something to try to copy.
        d = tmp_path / "plan.docx"
        d.mkdir()
        assert resolve_output_path(str(d), "document.docx") == d.resolve()


class TestTheRetryCase:
    @pytest.mark.parametrize(
        "server,tool,kwargs,name",
        [
            ("docx_new", "create_document", {}, "plan.docx"),
            ("pptx_new", "create_presentation", {"title": "Deck"}, "deck.pptx"),
            ("xlsx_new", "create_workbook", {}, "book.xlsx"),
        ],
    )
    def test_a_repeat_create_leaves_the_previous_file_recoverable(self, tmp_path, server, tool, kwargs, name):
        mod = load(server)
        out = tmp_path / name
        fn = getattr(mod, tool)
        fn = getattr(fn, "fn", fn)  # the SDK decorator returns the function itself here

        first = fn(output_path=str(out), **kwargs)
        assert first["success"] is True, first.get("error")
        out.write_bytes(out.read_bytes() + b"EDITED-IN-BETWEEN")
        edited = out.read_bytes()

        second = fn(output_path=str(out), **kwargs)
        assert second["success"] is True, second.get("error")

        history = get_history(str(out))
        assert history, f"{tool} overwrote {name} with no snapshot"
        assert any(Path(h["backup_path"]).read_bytes() == edited for h in history), (
            f"no snapshot of {name} as it stood before the repeat call"
        )
