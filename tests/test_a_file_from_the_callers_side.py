"""A file on the caller's side reaches this server, or the refusal says how it could.

Three ways a caller holding a file failed:

- It pasted a share link. Google Drive, Docs, Dropbox, GitHub and GitLab links
  as the browser shows them serve a web page, and that page was saved as
  data.csv and parsed as one.
- The link was not public, so even the right address served a sign-in page --
  written to the inbox as the file.
- It passed the only path it had: /mnt/user-data/uploads/x.csv from a claude.ai
  chat. The refusal named the rule ("outside the folders this server can use")
  and not the situation: the file is on the caller's side.

The local HTTP server binds 127.0.0.1 only; nothing here reaches the network.
"""

from __future__ import annotations

import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from shared import exchange  # type: ignore[reportMissingImports]
from shared.exchange import (  # type: ignore[reportMissingImports]
    client_side_path,
    client_side_refusal,
    direct_download_url,
    fetch_url,
    intake_routes,
)

PAGE = b"<!DOCTYPE html><html><head><title>Sign in</title></head><body>Sign in</body></html>"
CSV_BODY = b"a,b\n1,2\n"


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler API
        if self.path.startswith("/data.csv"):
            body, ctype = CSV_BODY, "text/csv"
        elif self.path.startswith("/report.html") or self.path.startswith("/article"):
            body, ctype = PAGE, "text/html"
        else:  # a sign-in page served where a file was asked for
            body, ctype = PAGE, "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        """Silence the access log."""


@pytest.fixture(scope="module")
def http_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def fetching(monkeypatch, tmp_path):
    exchange._fetch_cache.clear()
    monkeypatch.setenv("MCP_OUTPUT_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MCP_FETCH_URLS", "1")
    monkeypatch.setenv("MCP_FETCH_ALLOW_PRIVATE", "1")
    yield tmp_path / "data"
    exchange._fetch_cache.clear()


class TestAShareLinkIsReadAsTheFile:
    @pytest.mark.parametrize(
        ("link", "direct"),
        [
            (
                "https://drive.google.com/file/d/1AbC-dEf_9/view?usp=sharing",
                "https://drive.google.com/uc?export=download&id=1AbC-dEf_9",
            ),
            ("https://drive.google.com/open?id=1AbC", "https://drive.google.com/uc?export=download&id=1AbC"),
            (
                "https://docs.google.com/spreadsheets/d/1Sheet/edit#gid=42",
                "https://docs.google.com/spreadsheets/d/1Sheet/export?format=csv&gid=42",
            ),
            (
                "https://docs.google.com/spreadsheets/d/1Sheet/edit?usp=sharing",
                "https://docs.google.com/spreadsheets/d/1Sheet/export?format=csv",
            ),
            (
                "https://docs.google.com/document/d/1Doc/edit",
                "https://docs.google.com/document/d/1Doc/export?format=docx",
            ),
            (
                "https://docs.google.com/presentation/d/1Deck/edit",
                "https://docs.google.com/presentation/d/1Deck/export?format=pptx",
            ),
            (
                "https://www.dropbox.com/scl/fi/abc/sales.csv?rlkey=k1&dl=0",
                "https://www.dropbox.com/scl/fi/abc/sales.csv?rlkey=k1&dl=1",
            ),
            (
                "https://github.com/acme/data/blob/main/sets/sales.csv",
                "https://raw.githubusercontent.com/acme/data/main/sets/sales.csv",
            ),
            (
                "https://gitlab.com/acme/team/data/-/blob/main/sales.csv?ref_type=heads",
                "https://gitlab.com/acme/team/data/-/raw/main/sales.csv",
            ),
        ],
    )
    def test_the_link_is_rewritten_to_the_bytes(self, link, direct):
        assert direct_download_url(link) == direct

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/data.csv",
            "https://raw.githubusercontent.com/acme/data/main/sales.csv",
            "https://docs.google.com/spreadsheets/d/1Sheet/export?format=xlsx",
            "https://github.com/acme/data",
        ],
    )
    def test_any_other_address_is_left_alone(self, url):
        assert direct_download_url(url) == url

    def test_the_fetch_uses_the_rewritten_address(self, fetching, http_url, monkeypatch):
        asked = "https://drive.google.com/file/d/XYZ/view"
        monkeypatch.setattr(exchange, "direct_download_url", lambda u: f"{http_url}/data.csv" if u == asked else u)
        path = fetch_url(asked)
        assert path.read_bytes() == CSV_BODY


class TestAWebPageIsNotAFile:
    def test_a_page_served_for_a_csv_is_refused_and_not_written(self, fetching, http_url):
        with pytest.raises(ValueError, match="returned a web page, not the file"):
            fetch_url(f"{http_url}/sales.csv")
        inbox = fetching / "inbox"
        assert not inbox.exists() or not any(inbox.iterdir())

    def test_a_share_link_that_serves_a_page_says_it_is_not_public(self, fetching, http_url, monkeypatch):
        asked = "https://drive.google.com/file/d/XYZ/view"
        monkeypatch.setattr(exchange, "direct_download_url", lambda u: f"{http_url}/uc" if u == asked else u)
        with pytest.raises(ValueError) as caught:
            fetch_url(asked)
        message = str(caught.value)
        assert message.startswith(asked)
        assert "fetched as" in message and "anyone who has the link" in message

    def test_a_page_asked_for_by_name_is_still_a_page(self, fetching, http_url):
        assert fetch_url(f"{http_url}/report.html").read_bytes() == PAGE

    def test_a_page_with_no_name_is_still_a_page(self, fetching, http_url):
        assert fetch_url(f"{http_url}/article").read_bytes() == PAGE


class TestAPathOnTheCallersSide:
    @pytest.mark.parametrize(
        ("raw", "where"),
        [
            ("/mnt/user-data/uploads/Ad_Data.csv", "claude.ai"),
            ("/home/claude/work/sales.csv", "claude.ai"),
            ("/mnt/data/sales.csv", "ChatGPT"),
            pytest.param(
                "/Users/sam/Downloads/sales.csv",
                "own computer",
                marks=pytest.mark.skipif(sys.platform == "darwin", reason="a server on macOS has /Users itself"),
            ),
            pytest.param(
                "C:\\Users\\sam\\sales.csv",
                "Windows",
                marks=pytest.mark.skipif(os.name == "nt", reason="a server on Windows has drives itself"),
            ),
            pytest.param(
                "D:/exports/sales.csv",
                "Windows",
                marks=pytest.mark.skipif(os.name == "nt", reason="a server on Windows has drives itself"),
            ),
        ],
    )
    def test_it_is_recognised(self, raw, where):
        assert where in client_side_path(raw)

    def test_a_sandbox_path_anchored_to_a_windows_drive_is_still_one(self, monkeypatch):
        monkeypatch.setattr(exchange.os, "name", "nt")
        assert "claude.ai" in client_side_path("C:\\mnt\\user-data\\uploads\\Ad_Data.csv")

    def test_a_servers_own_system_paths_are_not_the_callers(self, monkeypatch):
        monkeypatch.setattr(exchange.sys, "platform", "darwin")
        assert client_side_path("/Users/sam/sales.csv") == ""
        monkeypatch.setattr(exchange.os, "name", "nt")
        assert client_side_path("C:\\Users\\sam\\sales.csv") == ""

    @pytest.mark.parametrize("raw", ["Ad_Data.csv", "/workspace/data/Ad_Data.csv", "/etc/hostname", "data/mnt/data/x"])
    def test_a_path_that_could_be_here_is_not(self, raw):
        assert client_side_path(raw) == ""
        assert client_side_refusal(raw) == ""

    def test_the_routes_offer_a_link_only_where_links_are_fetched(self, monkeypatch):
        monkeypatch.setenv("MCP_FETCH_URLS", "1")
        assert "link" in intake_routes()
        monkeypatch.setenv("MCP_FETCH_URLS", "0")
        assert "link" not in intake_routes()
        assert "data folder" in intake_routes()

    def test_the_refusal_names_the_situation_and_the_way_in(self, monkeypatch):
        monkeypatch.setenv("MCP_FETCH_URLS", "1")
        message = client_side_refusal("/mnt/user-data/uploads/Ad_Data.csv")
        assert "caller's side" in message
        assert "cannot see it" in message
        assert "link" in message
