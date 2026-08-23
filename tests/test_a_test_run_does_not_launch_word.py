"""A test run must never ask the desktop shell to open a document.

Every write wrapper in these servers calls its engine with open_after=True --
it is not a schema parameter, so a caller cannot opt out and neither could a
test. Exercising the write surface therefore asked Windows to launch Word once
per call, and on the CI runner that reached the COM layer and killed the
interpreter part-way through the suite:

    Windows fatal exception: code 0x80010108        (RPC_E_DISCONNECTED)
    Thread 0x00000760 (most recent call first):
      File "shared/shared/platform_utils.py", line 175 in open_file
    Windows fatal exception: access violation

No failing test was named and no traceback was printed, because an access
violation is not an exception -- the `except Exception: pass` wrapped around
os.startfile() had never been able to catch it, and the job simply reported
exit code 1 after ~30% of the tests. It passed on ubuntu and macos, where the
same call is a subprocess that cannot touch this process.

Two changes: open_file() returns immediately when PYTEST_CURRENT_TEST is set,
and on Windows it spawns a child rather than calling os.startfile() in-process,
so a faulting shell handler costs the child instead of the server.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared import platform_utils  # noqa: E402


class TestOpenFileIsInertUnderPytest:
    def test_it_launches_nothing_while_a_test_is_running(self, tmp_path, monkeypatch):
        called: list = []
        monkeypatch.setattr(platform_utils.subprocess, "Popen", lambda *a, **k: called.append(a))
        # pytest sets this for the duration of every test; assert that rather
        # than trusting it, since the guard is worthless if the name changes.
        assert platform_utils.os.environ.get("PYTEST_CURRENT_TEST")
        platform_utils.open_file(tmp_path / "doc.docx")
        assert called == [], "a test run tried to launch the desktop handler"

    def test_outside_a_test_run_it_still_opens(self, tmp_path, monkeypatch):
        called: list = []
        monkeypatch.setattr(platform_utils.subprocess, "Popen", lambda *a, **k: called.append(a))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        platform_utils.open_file(tmp_path / "doc.docx")
        assert len(called) == 1, "the guard must not disable the feature itself"


class TestWindowsOpensOutOfProcess:
    def test_startfile_is_not_called_in_this_process(self, tmp_path, monkeypatch):
        # os.startfile exists only on Windows, so assert on the source: the
        # in-process call is what could take the interpreter down, and no
        # amount of exception handling around it helps.
        source = Path(platform_utils.__file__).read_text(encoding="utf-8")
        body = source.split("def open_file(")[1]
        code = [ln for ln in body.splitlines() if not ln.lstrip().startswith("#")]
        assert "startfile" not in "\n".join(code), "open_file still calls os.startfile in-process"

    def test_the_windows_branch_spawns_a_child(self, tmp_path, monkeypatch):
        called: list = []
        monkeypatch.setattr(platform_utils.subprocess, "Popen", lambda *a, **k: called.append(a[0]))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setattr(platform_utils, "is_windows", lambda: True)
        monkeypatch.setattr(platform_utils, "is_macos", lambda: False)
        platform_utils.open_file(tmp_path / "doc.docx")
        assert called and called[0][0] == "cmd", called
