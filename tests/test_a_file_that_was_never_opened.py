"""Every write said it opened the document. Nothing opened it.

`open_after` defaults to True on every write tool here, and the three `*_new`
servers followed each `open_file(path)` with an unconditional

    progress.append(ok("Opened <file> in default app"))

`open_file` is documented "Silently ignored on failure" and returned None either
way, so the success line was appended whether or not anything happened. On a
headless container -- which is how this fleet is deployed, and where there is no
`xdg-open` and no DISPLAY -- every document written reported, with status `ok`,
that a desktop application had opened it.

Nothing breaks: the file is correct and the caller gets it. What made this worth
fixing is what it did to an earlier decision. `open_after` was reviewed and
closed as "not a defect" on the stated grounds that *"no response field ever
claims it opened"*. A `progress` entry with `status: ok` is a response field,
and it did. The decision stands; the reason for it did not.

`open_file` now returns whether a handler was actually launched, and every
caller gates its claim on that.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shared.platform_utils import open_file  # noqa: E402


class TestOpenFileReportsWhatHappened:
    def test_it_returns_a_bool(self, tmp_path):
        result = open_file(tmp_path / "nothing.docx")
        assert isinstance(result, bool)

    def test_under_pytest_it_never_launches_and_says_so(self, tmp_path):
        """The suite must not start Word; that guard must also not claim success."""
        assert open_file(tmp_path / "nothing.docx") is False

    def test_a_headless_linux_box_answers_false(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.setattr("shared.platform_utils.is_windows", lambda: False)
        monkeypatch.setattr("shared.platform_utils.is_macos", lambda: False)
        assert open_file(tmp_path / "nothing.docx") is False

    def test_a_launcher_that_raises_answers_false(self, tmp_path, monkeypatch):
        def boom(*args, **kwargs):
            raise FileNotFoundError("xdg-open")

        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("DISPLAY", ":0")
        monkeypatch.setattr("shared.platform_utils.is_windows", lambda: False)
        monkeypatch.setattr("shared.platform_utils.is_macos", lambda: False)
        monkeypatch.setattr("shared.platform_utils.shutil.which", lambda _: "/usr/bin/xdg-open")
        monkeypatch.setattr("shared.platform_utils.subprocess.Popen", boom)
        assert open_file(tmp_path / "nothing.docx") is False

    def test_a_launcher_that_starts_answers_true(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("DISPLAY", ":0")
        monkeypatch.setattr("shared.platform_utils.is_windows", lambda: False)
        monkeypatch.setattr("shared.platform_utils.is_macos", lambda: False)
        monkeypatch.setattr("shared.platform_utils.shutil.which", lambda _: "/usr/bin/xdg-open")
        monkeypatch.setattr("shared.platform_utils.subprocess.Popen", lambda *a, **k: object())
        assert open_file(tmp_path / "nothing.docx") is True


class TestNoWriteClaimsAnOpenThatDidNotHappen:
    def test_docx_new_says_nothing_when_nothing_opened(self, tmp_path):
        sys.path.insert(0, str(ROOT / "servers" / "docx_new"))
        from docx_new import engine

        out = engine.create_from_text(
            str(tmp_path / "r.docx"), [{"text": "hello", "style": "Normal"}], open_after=True
        )
        assert out["success"] is True, out.get("error")
        messages = " ".join(str(entry) for entry in out.get("progress", []))
        assert "Opened" not in messages, "claimed an open on a headless box"

    def test_the_document_is_still_written(self, tmp_path):
        sys.path.insert(0, str(ROOT / "servers" / "docx_new"))
        from docx_new import engine

        target = tmp_path / "r2.docx"
        out = engine.create_from_text(str(target), [{"text": "hello", "style": "Normal"}], open_after=True)
        assert out["success"] is True
        assert target.exists(), "gating the message must not gate the write"

    @pytest.mark.parametrize(
        "relpath",
        [
            "servers/docx_new/docx_new/engine.py",
            "servers/pptx_new/pptx_new/engine.py",
            "servers/xlsx_new/xlsx_new/engine.py",
        ],
    )
    def test_no_engine_appends_the_claim_unconditionally(self, relpath):
        """Static, because the message must be gated at every one of 13 call sites.

        Only claims about the *default application* count. "Opened report.docx
        -- 7 paragraphs" and "Opened template base.docx" describe reading a
        file and are true; the defect is claiming a desktop application
        launched. The first draft of this test flagged both and was wrong.
        """
        source = (ROOT / relpath).read_text(encoding="utf-8")
        lines = source.splitlines()
        claims = 0
        for i, line in enumerate(lines):
            if "progress.append" in line and ("default app" in line or "default application" in line):
                claims += 1
                window = "\n".join(lines[max(0, i - 5) : i])
                assert "and open_file(" in window, f"{relpath}:{i + 1} claims an open without checking"
        assert claims, f"{relpath} makes no such claim -- has the message been renamed?"
