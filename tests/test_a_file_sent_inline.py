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


class TestAFileSentInParts:
    """A file too big for one call arrives in parts; the tool runs once it is whole."""

    WHOLE = b"id,value\n" + b"".join(f"{i},{i * i}\n".encode() for i in range(300))

    def _parts(self, n: int = 3, name: str = "big.csv", whole: bytes | None = None, digest: str = ""):
        import hashlib

        whole = self.WHOLE if whole is None else whole
        digest = digest or hashlib.sha256(whole).hexdigest()
        size = -(-len(whole) // n)
        chunks = [whole[i * size : (i + 1) * size] for i in range(n)]
        return [
            f"data:text/csv;name={name};part={i + 1}/{n};sha256={digest};base64,{base64.b64encode(c).decode()}"
            for i, c in enumerate(chunks)
        ]

    def _tool(self):
        ran = []

        def read_it(file_path: str) -> dict:
            ran.append(file_path)
            return {"success": True, "file_path": file_path}

        tool = SimpleNamespace(name="read_it", fn=read_it)
        accept_inline_files(SimpleNamespace(_tool_manager=SimpleNamespace(_tools={"read_it": tool})))
        return tool.fn, ran

    def test_the_tool_runs_once_on_the_whole_file(self, inbox):
        call, ran = self._tool()
        first, second, third = self._parts()
        pending = call(file_path=first)
        assert pending["success"] is True and pending["tool_ran"] is False
        assert pending["upload"] == {"name": "big.csv", "parts": 3, "received": [1], "missing": [2, 3]}
        assert "read_it runs on big.csv" in pending["hint"]
        call(file_path=second)
        assert ran == []
        done = call(file_path=third)
        assert done["success"] is True and ran == [str(inbox / "big.csv")]
        assert (inbox / "big.csv").read_bytes() == self.WHOLE
        assert not any((inbox / ".parts").iterdir())

    def test_parts_arrive_in_any_order_and_a_resent_part_replaces_itself(self, inbox):
        call, ran = self._tool()
        first, second, third = self._parts()
        call(file_path=third)
        call(file_path=first)
        call(file_path=first)
        assert call(file_path=second)["success"] is True
        assert (inbox / "big.csv").read_bytes() == self.WHOLE

    def test_parts_that_do_not_add_up_are_refused_and_dropped(self, inbox):
        call, ran = self._tool()
        parts = self._parts(digest="0" * 64)
        call(file_path=parts[0])
        call(file_path=parts[1])
        refused = call(file_path=parts[2])
        assert refused["success"] is False and "do not add up" in refused["error"]
        assert ran == [] and not (inbox / "big.csv").exists()
        assert not any((inbox / ".parts").iterdir())

    def test_a_part_numbered_out_of_another_total_is_refused(self, inbox):
        call, _ = self._tool()
        call(file_path=self._parts(3)[0])
        other = self._parts(4)[1]
        assert "disagrees" in call(file_path=other)["error"]

    def test_the_whole_file_is_capped(self, inbox, monkeypatch):
        monkeypatch.setenv("MCP_MAX_UPLOAD_MB", "0.002")
        call, ran = self._tool()
        parts = self._parts(3)
        results = [call(file_path=p) for p in parts]
        assert any(r["success"] is False and "larger than" in r.get("error", "") for r in results)
        assert ran == []

    @pytest.mark.parametrize(
        ("header", "says"),
        [
            ("part=2;sha256=" + "a" * 64, "part=<this part>/<all parts>"),
            ("part=4/3;sha256=" + "a" * 64, "not one of"),
            ("part=1/2", "SHA-256"),
        ],
    )
    def test_a_malformed_part_is_refused_by_name(self, inbox, header, says):
        call, _ = self._tool()
        result = call(file_path=f"data:text/csv;name=x.csv;{header};base64,{base64.b64encode(b'a').decode()}")
        assert result["success"] is False and says in result["error"]

    def test_an_abandoned_upload_is_forgotten_after_an_hour(self, inbox):
        import os
        import time

        call, _ = self._tool()
        call(file_path=self._parts(3, name="old.csv", whole=b"x" * 30)[0])
        stale = next((inbox / ".parts").iterdir())
        hour_ago = time.time() - 3700
        os.utime(stale, (hour_ago, hour_ago))
        call(file_path=self._parts(3)[0])
        assert not stale.exists()

    def test_the_routes_say_how_to_send_parts(self):
        assert "part=<i>/<n>;sha256=" in intake_routes()
