"""A file on the caller's side reaches this server in one request: an upload URL.

Inline bytes pass through the model's own output -- fine for a small file,
slow and costly for a big one. When a caller passes a path from its sandbox
(/mnt/user-data/uploads/...), the refusal can instead carry a URL minted for
that file: the sandbox sends the bytes with one curl, and the answer is a path
every tool here takes. That URL is a public address that writes without the
API key, so:

- it is off unless the operator sets MCP_UPLOAD_URLS=1 and MCP_UPLOAD_BASE_URL;
- its token is signed, fixes the one file name it writes, and expires in 15 minutes;
- it writes once, into the inbox only, up to MCP_MAX_UPLOAD_MB;
- a forged, re-signed, expired or spent token writes nothing.
"""

from __future__ import annotations

import base64
import json
import re
import time

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from shared import exchange  # type: ignore[reportMissingImports]
from shared.exchange import client_side_refusal, mint_upload_url, uploads_enabled  # type: ignore[reportMissingImports]

SANDBOX = "/mnt/user-data/uploads/Ad Data.csv"
BASE = "https://files.example.test"
URL = re.compile(r"https://files\.example\.test/upload/[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


def _client() -> TestClient:
    app = Starlette(routes=[Route("/upload/{token}", exchange.upload_route, methods=["PUT", "POST"])])
    return TestClient(app)


def _path(url: str) -> str:
    return url[len(BASE) :]


def _claims(url: str) -> dict:
    body = url.rsplit("/", 1)[1].split(".", 1)[0]
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))


def _inbox_files(root) -> list:
    inbox = root / "inbox"
    return sorted(p.name for p in inbox.iterdir()) if inbox.is_dir() else []


@pytest.fixture
def off(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_OUTPUT_DIR", str(tmp_path))
    for name in ("MCP_UPLOAD_URLS", "MCP_UPLOAD_BASE_URL", "MCP_UPLOAD_SECRET"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


@pytest.fixture
def on(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("MCP_UPLOAD_URLS", "1")
    monkeypatch.setenv("MCP_UPLOAD_BASE_URL", BASE + "/")
    monkeypatch.setenv("MCP_UPLOAD_SECRET", "test-secret-not-a-secret")
    monkeypatch.delenv("MCP_MAX_UPLOAD_MB", raising=False)
    monkeypatch.setattr(exchange, "_used_upload_tokens", {})
    return tmp_path


class TestOffByDefault:
    def test_nothing_is_minted(self, off):
        assert uploads_enabled() is False
        assert mint_upload_url("x.csv") == ""

    def test_the_flag_alone_is_not_enough(self, off, monkeypatch):
        monkeypatch.setenv("MCP_UPLOAD_URLS", "1")
        assert uploads_enabled() is False and mint_upload_url("x.csv") == ""

    def test_the_refusal_offers_no_upload(self, off):
        refusal = client_side_refusal(SANDBOX)
        assert refusal and "curl" not in refusal and not URL.search(refusal)

    def test_the_route_answers_404_and_writes_nothing(self, off):
        reply = _client().put("/upload/anything.at-all", content=b"a,b\n1,2\n")
        assert reply.status_code == 404 and reply.json()["success"] is False
        assert _inbox_files(off) == []


class TestTheRefusalCarriesAUrl:
    def test_it_is_minted_for_that_file(self, on):
        refusal = client_side_refusal(SANDBOX)
        found = URL.search(refusal)
        assert found, refusal
        assert _claims(found.group(0))["n"] == "Ad_Data.csv"
        assert "curl -T" in refusal and "15 minutes" in refusal and "100 MB" in refusal

    def test_the_other_routes_are_still_named(self, on):
        assert "data:" in client_side_refusal(SANDBOX)


class TestOneRequestWritesTheFile:
    @pytest.mark.parametrize("method", ["put", "post"])
    def test_into_the_inbox_under_the_minted_name(self, on, method):
        url = mint_upload_url(SANDBOX)
        reply = getattr(_client(), method)(_path(url), content=b"a,b\n1,2\n")
        assert reply.status_code == 200, reply.text
        answer = reply.json()
        assert answer["success"] is True and answer["bytes"] == 8
        assert answer["path"] == str(on / "inbox" / "Ad_Data.csv")
        assert (on / "inbox" / "Ad_Data.csv").read_bytes() == b"a,b\n1,2\n"
        assert answer["path"] in answer["hint"]

    def test_a_name_cannot_climb_out_of_the_inbox(self, on):
        reply = _client().put(_path(mint_upload_url("../../etc/passwd")), content=b"x")
        assert reply.json()["path"] == str(on / "inbox" / "passwd")

    def test_a_different_file_of_that_name_is_kept(self, on):
        (on / "inbox").mkdir()
        (on / "inbox" / "Ad_Data.csv").write_bytes(b"theirs")
        reply = _client().put(_path(mint_upload_url(SANDBOX)), content=b"mine")
        assert reply.json()["path"] != str(on / "inbox" / "Ad_Data.csv")
        assert (on / "inbox" / "Ad_Data.csv").read_bytes() == b"theirs"

    def test_a_get_is_not_an_upload(self, on):
        assert _client().get(_path(mint_upload_url(SANDBOX))).status_code == 405


class TestATokenWritesOnceAndOnlyAsSigned:
    def test_a_second_upload_is_refused(self, on):
        url = mint_upload_url(SANDBOX)
        assert _client().put(_path(url), content=b"first").status_code == 200
        again = _client().put(_path(url), content=b"second")
        assert again.status_code == 403 and "already used" in again.json()["error"]
        assert (on / "inbox" / "Ad_Data.csv").read_bytes() == b"first"

    def test_a_changed_signature_is_refused(self, on):
        url = mint_upload_url(SANDBOX)
        forged = url[:-2] + ("AA" if not url.endswith("AA") else "BB")
        reply = _client().put(_path(forged), content=b"x")
        assert reply.status_code == 403 and "not one this server issued" in reply.json()["error"]
        assert _inbox_files(on) == []

    def test_a_changed_name_is_refused(self, on):
        url = mint_upload_url(SANDBOX)
        claims = {**_claims(url), "n": "../../evil.sh"}
        body = base64.urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode()).decode().rstrip("=")
        signature = url.rsplit(".", 1)[1]
        reply = _client().put(f"/upload/{body}.{signature}", content=b"x")
        assert reply.status_code == 403 and _inbox_files(on) == []

    @pytest.mark.parametrize("token", ["abc.%C3%A9", "%C3%A9.abc", "e30.", ".abc", "no-dot-at-all"])
    def test_a_malformed_token_is_a_refusal_not_a_crash(self, on, token):
        reply = TestClient(_client().app, raise_server_exceptions=False).put(f"/upload/{token}", content=b"x")
        assert reply.status_code == 403 and reply.json()["success"] is False
        assert _inbox_files(on) == []

    def test_a_url_from_another_secret_is_refused(self, on, monkeypatch):
        url = mint_upload_url(SANDBOX)
        monkeypatch.setenv("MCP_UPLOAD_SECRET", "a-different-secret")
        assert _client().put(_path(url), content=b"x").status_code == 403
        assert _inbox_files(on) == []

    def test_an_expired_url_is_refused(self, on, monkeypatch):
        url = mint_upload_url(SANDBOX)
        later = time.time() + 16 * 60
        monkeypatch.setattr(exchange.time, "time", lambda: later)
        reply = _client().put(_path(url), content=b"x")
        assert reply.status_code == 403 and "expired" in reply.json()["error"]
        assert _inbox_files(on) == []


class TestASizeCap:
    def test_a_file_over_the_cap_writes_nothing_and_the_url_still_works(self, on, monkeypatch):
        monkeypatch.setenv("MCP_MAX_UPLOAD_MB", "0.001")
        url = mint_upload_url(SANDBOX)
        big = _client().put(_path(url), content=b"x" * 5000)
        assert big.status_code == 413 and "upload limit" in big.json()["error"]
        assert _inbox_files(on) == []
        assert _client().put(_path(url), content=b"small").status_code == 200

    def test_a_body_with_no_declared_length_is_capped_as_it_streams(self, on, monkeypatch):
        monkeypatch.setenv("MCP_MAX_UPLOAD_MB", "0.001")
        url = mint_upload_url(SANDBOX)
        big = _client().put(_path(url), content=iter([b"x" * 700, b"x" * 700]))
        assert big.status_code == 413 and _inbox_files(on) == []
        assert _client().put(_path(url), content=b"small").status_code == 200

    def test_an_empty_upload_writes_nothing_and_can_be_retried(self, on):
        url = mint_upload_url(SANDBOX)
        empty = _client().put(_path(url), content=b"")
        assert empty.status_code == 400 and _inbox_files(on) == []
        assert _client().put(_path(url), content=b"a").status_code == 200


def test_the_unified_server_mounts_the_route_and_it_is_off(off):
    import unified_server  # type: ignore[reportMissingImports]

    reply = TestClient(unified_server.app).put("/upload/anything.at-all", content=b"x")
    assert reply.status_code == 404 and reply.json() == {"success": False, "error": "Uploads are off on this server."}
    assert _inbox_files(off) == []
