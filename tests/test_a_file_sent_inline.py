"""A file's bytes, sent where a path goes, become a file every tool can read.

A caller whose file is on its own side -- a claude.ai upload -- has no path
this server can see and, when its sandbox has no network, no link either. The
bytes are the one thing it can send: `data:text/csv;name=sales.csv;base64,...`
in place of the path. The wrapper saves them to the inbox before the tool
runs, so the tool sees a path and never echoes the file back.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from shared import exchange  # type: ignore[reportMissingImports]
from shared.exchange import (  # type: ignore[reportMissingImports]
    accept_inline_files,
    inline_bytes,
    intake_routes,
    is_inline,
    save_inline,
)

CSV = b"a,b\n1,2\n3,4\n"


def _uri(payload: bytes = CSV, name: str = "sales.csv", media: str = "text/csv") -> str:
    head = f"data:{media};name={name};base64," if name else f"data:{media};base64,"
    return head + base64.b64encode(payload).decode()


@pytest.fixture
def inbox(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_OUTPUT_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("MCP_MAX_INLINE_MB", raising=False)
    return tmp_path / "data" / "inbox"


class TestTheBytesAreRead:
    def test_base64_with_a_name(self):
        assert inline_bytes(_uri()) == ("sales.csv", CSV)

    def test_percent_encoded_text(self):
        assert inline_bytes("data:text/csv;name=t.csv,a%2Cb%0A1%2C2%0A") == ("t.csv", b"a,b\n1,2\n")

    def test_the_type_names_a_file_sent_without_a_name(self):
        assert inline_bytes(_uri(name=""))[0] == "inline.csv"

    def test_a_name_cannot_climb_out_of_the_inbox(self):
        # No suffix of its own, so the declared type supplies one.
        assert inline_bytes(_uri(name="..%2F..%2Fetc%2Fpasswd"))[0] == "passwd.csv"
        assert inline_bytes(_uri(name="C:%5Cx%5Cevil.csv"))[0] == "evil.csv"

    @pytest.mark.parametrize(
        ("raw", "says"),
        [
            ("data:text/csv;name=x.csv;base64,", "empty"),
            ("data:text/csv;name=x.csv;base64,***", "does not decode"),
            ("data:text/csv;name=x.csv;base64", "comma"),
        ],
    )
    def test_a_broken_one_is_refused_by_name(self, raw, says):
        with pytest.raises(ValueError, match=says):
            inline_bytes(raw)

    def test_the_size_is_capped_before_decoding(self, monkeypatch):
        monkeypatch.setenv("MCP_MAX_INLINE_MB", "0.001")
        with pytest.raises(ValueError, match="larger than the"):
            inline_bytes(_uri(b"x" * 5000))

    def test_only_a_data_uri_is_inline(self):
        assert is_inline(_uri()) and is_inline("DATA:text/plain,hi")
        assert not is_inline("sales.csv") and not is_inline("https://x/data.csv") and not is_inline(3)


class TestItLandsInTheInbox:
    def test_written_there_under_its_name(self, inbox):
        path = save_inline(_uri())
        assert path == inbox / "sales.csv"
        assert path.read_bytes() == CSV

    def test_sent_twice_it_is_the_same_file(self, inbox):
        assert save_inline(_uri()) == save_inline(_uri())
        assert len(list(inbox.iterdir())) == 1

    def test_other_bytes_under_a_taken_name_never_overwrite(self, inbox):
        first = save_inline(_uri())
        second = save_inline(_uri(b"a,b\n9,9\n"))
        assert first != second
        assert first.read_bytes() == CSV
        assert second.name.startswith("sales_") and second.suffix == ".csv"


class TestEveryToolTakesIt:
    def _registered(self, fn):
        tool = SimpleNamespace(name=fn.__name__, fn=fn)
        accept_inline_files(SimpleNamespace(_tool_manager=SimpleNamespace(_tools={tool.name: tool})))
        return tool.fn

    def test_the_tool_sees_a_path_and_never_the_bytes(self, inbox):
        seen = {}

        def read_it(file_path: str, files: list[str] | None = None) -> dict:
            seen.update(file_path=file_path, files=files)
            return {"success": True, "file_path": file_path}

        result = self._registered(read_it)(file_path=_uri(), files=[_uri(name="b.csv"), "plain.csv"])
        assert seen["file_path"] == str(inbox / "sales.csv")
        assert seen["files"] == [str(inbox / "b.csv"), "plain.csv"]
        assert "base64" not in str(result)

    def test_a_refused_one_is_an_answer_and_the_tool_never_runs(self, inbox, monkeypatch):
        monkeypatch.setenv("MCP_MAX_INLINE_MB", "0.001")
        ran = []

        def read_it(file_path: str) -> dict:
            ran.append(file_path)
            return {"success": True}

        result = self._registered(read_it)(file_path=_uri(b"x" * 5000))
        assert result["success"] is False
        assert result["op"] == "read_it"
        assert "data:" in result["hint"]
        assert ran == []

    def test_a_call_with_no_inline_file_is_untouched(self, inbox):
        def read_it(file_path: str) -> dict:
            return {"success": True, "file_path": file_path}

        assert self._registered(read_it)(file_path="sales.csv") == {"success": True, "file_path": "sales.csv"}
        assert not inbox.exists()


def test_the_routes_name_the_inline_form_and_its_cap(monkeypatch):
    monkeypatch.setenv("MCP_MAX_INLINE_MB", "2")
    routes = intake_routes()
    assert "data:<type>;name=<file name>;base64,<bytes>" in routes
    assert "2 MB" in routes
    assert intake_routes("write it with fs_write").startswith("write it with fs_write")
    assert exchange.client_side_refusal("/mnt/user-data/uploads/x.csv").count("data:") == 1
