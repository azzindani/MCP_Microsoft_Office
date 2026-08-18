"""Tests for shared/exchange.py — the hybrid local/remote file exchange layer.

Every env var this module reads is unset by default, so each test establishes
the exact environment it needs via monkeypatch. The one HTTP server used here
binds to 127.0.0.1 — no external network.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from shared import exchange
from shared.exchange import (
    assert_fetchable,
    attach_public_url,
    fetch_url,
    get_inbox_dir,
    get_output_dir,
    is_url,
    public_url_for,
    url_fetch_enabled,
)
from shared.file_utils import _downloads_dir, embed_content, resolve_path
from shared.platform_utils import get_downloads_dir, resolve_output_path

DOCX_BODY = b"PK\x03\x04 pretend docx"


class _Handler(BaseHTTPRequestHandler):
    """Serves a .docx at /doc.docx, a no-extension export, and a big payload."""

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler API
        if self.path.startswith("/doc.docx"):
            body, ctype = DOCX_BODY, "application/octet-stream"
        elif self.path.startswith("/export"):
            body = DOCX_BODY
            ctype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif self.path.startswith("/big"):
            body, ctype = b"x" * (3 * 1024 * 1024), "application/octet-stream"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        """Silence the default stderr access log."""


class _QuietServer(ThreadingHTTPServer):
    """Silences the traceback the size-cap test provokes by hanging up early."""

    def handle_error(self, request: object, client_address: object) -> None:
        """Expected mid-body disconnect — nothing to report."""


@pytest.fixture(scope="module")
def http_url():
    server = _QuietServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def clear_fetch_cache():
    exchange._fetch_cache.clear()
    yield
    exchange._fetch_cache.clear()


@pytest.fixture
def remote_mode(monkeypatch, tmp_path):
    """Server configured the way a container deployment configures it."""
    monkeypatch.setenv("MCP_OUTPUT_DIR", str(tmp_path / "shared"))
    monkeypatch.setenv("MCP_PUBLIC_BASE_URL", "https://files.example.test/data")
    monkeypatch.setenv("MCP_FETCH_URLS", "1")
    monkeypatch.setenv("MCP_FETCH_ALLOW_PRIVATE", "1")
    return tmp_path / "shared"


# ---------------------------------------------------------------------------
# output directory
# ---------------------------------------------------------------------------


def test_output_dir_defaults_to_downloads(monkeypatch):
    monkeypatch.delenv("MCP_OUTPUT_DIR", raising=False)
    assert get_output_dir() == Path.home() / "Downloads"


def test_output_dir_honours_env_and_creates_it(monkeypatch, tmp_path):
    target = tmp_path / "not-yet-there"
    monkeypatch.setenv("MCP_OUTPUT_DIR", str(target))
    assert get_output_dir() == target
    assert target.is_dir()


def test_downloads_dir_helpers_follow_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_OUTPUT_DIR", str(tmp_path / "shared"))
    assert get_downloads_dir() == tmp_path / "shared"
    assert _downloads_dir() == tmp_path / "shared"


def test_downloads_dir_helpers_fall_back_when_env_unset(monkeypatch):
    monkeypatch.delenv("MCP_OUTPUT_DIR", raising=False)
    assert get_downloads_dir().name == "Downloads"
    assert _downloads_dir().name == "Downloads"


def test_new_document_defaults_into_shared_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_OUTPUT_DIR", str(tmp_path / "shared"))
    assert resolve_output_path("", "report.docx") == tmp_path / "shared" / "report.docx"
    assert resolve_output_path("quarterly.docx", "report.docx") == tmp_path / "shared" / "quarterly.docx"


def test_explicit_output_path_still_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_OUTPUT_DIR", str(tmp_path / "shared"))
    explicit = tmp_path / "elsewhere" / "report.docx"
    assert resolve_output_path(str(explicit), "report.docx") == explicit


# ---------------------------------------------------------------------------
# public URLs
# ---------------------------------------------------------------------------


def test_public_url_for_file_under_output_dir(remote_mode):
    remote_mode.mkdir(parents=True, exist_ok=True)
    doc = remote_mode / "report.docx"
    doc.write_bytes(DOCX_BODY)
    assert public_url_for(doc) == "https://files.example.test/data/report.docx"


def test_public_url_encodes_and_keeps_subdirectories(remote_mode):
    nested = remote_mode / "inbox" / "my report.docx"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(DOCX_BODY)
    assert public_url_for(nested) == "https://files.example.test/data/inbox/my%20report.docx"


def test_public_url_empty_for_file_outside_output_dir(remote_mode, tmp_path):
    outside = tmp_path / "private.docx"
    outside.write_bytes(DOCX_BODY)
    assert public_url_for(outside) == ""


def test_public_url_empty_when_not_configured(monkeypatch, tmp_path):
    monkeypatch.delenv("MCP_PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("MCP_OUTPUT_DIR", str(tmp_path))
    assert public_url_for(tmp_path / "x.docx") == ""


def test_attach_public_url_only_sets_key_when_resolvable(remote_mode, tmp_path):
    remote_mode.mkdir(parents=True, exist_ok=True)
    inside = remote_mode / "a.docx"
    inside.write_bytes(DOCX_BODY)
    assert attach_public_url({"success": True}, inside)["public_url"].endswith("/a.docx")
    assert "public_url" not in attach_public_url({"success": True}, tmp_path / "b.docx")


def test_embed_content_attaches_public_url_without_return_content(remote_mode):
    remote_mode.mkdir(parents=True, exist_ok=True)
    doc = remote_mode / "c.docx"
    doc.write_bytes(DOCX_BODY)
    result = embed_content({"success": True, "op": "create_document"}, doc, False)
    assert result["public_url"] == "https://files.example.test/data/c.docx"
    assert "content_base64" not in result


def test_embed_content_still_embeds_bytes_and_mime(remote_mode):
    remote_mode.mkdir(parents=True, exist_ok=True)
    doc = remote_mode / "d.docx"
    doc.write_bytes(DOCX_BODY)
    result = embed_content({"success": True}, doc, True)
    assert result["public_url"].endswith("/d.docx")
    assert result["content_mime_type"].endswith("wordprocessingml.document")


def test_embed_content_skips_failed_results(remote_mode):
    remote_mode.mkdir(parents=True, exist_ok=True)
    doc = remote_mode / "e.docx"
    doc.write_bytes(DOCX_BODY)
    assert "public_url" not in embed_content({"success": False}, doc, True)


# ---------------------------------------------------------------------------
# URL detection and the fetch gate
# ---------------------------------------------------------------------------


def test_is_url_only_matches_http_schemes():
    assert is_url("https://example.test/a.docx")
    assert is_url("  HTTP://example.test/a.docx ")
    assert not is_url("/home/app/a.docx")
    assert not is_url("workspace:demo/report")
    assert not is_url("file:///etc/passwd")


def test_fetch_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MCP_FETCH_URLS", raising=False)
    assert not url_fetch_enabled()
    with pytest.raises(ValueError, match="MCP_FETCH_URLS=1"):
        fetch_url("https://example.test/a.docx")


def test_resolve_path_rejects_url_when_fetching_disabled(monkeypatch):
    monkeypatch.delenv("MCP_FETCH_URLS", raising=False)
    with pytest.raises(ValueError, match="does not fetch URLs"):
        resolve_path("https://example.test/a.docx")


# ---------------------------------------------------------------------------
# SSRF guard
# ---------------------------------------------------------------------------


def test_assert_fetchable_rejects_non_http_scheme(monkeypatch):
    monkeypatch.delenv("MCP_FETCH_ALLOW_PRIVATE", raising=False)
    with pytest.raises(ValueError, match="Only http and https"):
        assert_fetchable("file:///etc/passwd")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8830/docx-new/health",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/internal",
        "http://[::1]:8000/x",
    ],
)
def test_assert_fetchable_rejects_non_public_addresses(monkeypatch, url):
    monkeypatch.delenv("MCP_FETCH_ALLOW_PRIVATE", raising=False)
    with pytest.raises(ValueError, match="non-public address"):
        assert_fetchable(url)


def test_assert_fetchable_allows_private_when_opted_in(monkeypatch):
    monkeypatch.setenv("MCP_FETCH_ALLOW_PRIVATE", "1")
    assert_fetchable("http://127.0.0.1:8830/health")


def test_assert_fetchable_reports_unresolvable_host(monkeypatch):
    monkeypatch.delenv("MCP_FETCH_ALLOW_PRIVATE", raising=False)
    with pytest.raises(ValueError, match="Cannot resolve host"):
        assert_fetchable("https://no-such-host.invalid/a.docx")


# ---------------------------------------------------------------------------
# real downloads
# ---------------------------------------------------------------------------


def test_fetch_url_downloads_real_bytes_into_inbox(remote_mode, http_url):
    path = fetch_url(f"{http_url}/doc.docx")
    assert path.read_bytes() == DOCX_BODY
    assert path == get_inbox_dir() / "doc.docx"
    assert public_url_for(path) == "https://files.example.test/data/inbox/doc.docx"


def test_fetch_url_adds_suffix_from_content_type(remote_mode, http_url):
    path = fetch_url(f"{http_url}/export?id=7")
    assert path.suffix == ".docx"
    assert path.read_bytes() == DOCX_BODY


def test_fetch_url_is_cached_within_the_ttl(remote_mode, http_url):
    first = fetch_url(f"{http_url}/doc.docx")
    first.write_bytes(b"sentinel")
    assert fetch_url(f"{http_url}/doc.docx").read_bytes() == b"sentinel"


def test_fetch_url_refetches_when_cached_file_is_gone(remote_mode, http_url):
    first = fetch_url(f"{http_url}/doc.docx")
    first.unlink()
    assert fetch_url(f"{http_url}/doc.docx").read_bytes() == DOCX_BODY


def test_fetch_url_enforces_the_size_cap(remote_mode, http_url, monkeypatch):
    monkeypatch.setenv("MCP_MAX_FETCH_MB", "1")
    with pytest.raises(ValueError, match="larger than the 1 MB limit"):
        fetch_url(f"{http_url}/big")


def test_fetch_url_reports_http_errors_as_value_error(remote_mode, http_url):
    with pytest.raises(ValueError, match="Could not download"):
        fetch_url(f"{http_url}/missing.docx")


def test_resolve_path_downloads_url_and_returns_local_path(remote_mode, http_url):
    path = resolve_path(f"{http_url}/doc.docx")
    assert path.is_file()
    assert path.read_bytes() == DOCX_BODY
