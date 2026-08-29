"""Hybrid local/remote file exchange: shared output dir, public URLs, URL inputs.

A local stdio install and a self-hosted HTTP deployment run the same engine
code, but they differ in one way that matters for files: over HTTP the caller
shares no filesystem with this server, so a server-local output path in a
response is meaningless to it, and a local path in a request is something the
caller may not have in the first place.

Three environment variables bridge that gap. All are unset by default, so a
local install keeps its existing offline, ~/Downloads behaviour untouched:

  MCP_OUTPUT_DIR       Directory generated files default into. Bind-mount it in
                       a container deployment so outputs land somewhere the
                       operator (and any file server in front of it) can see.
  MCP_PUBLIC_BASE_URL  Public base URL that serves MCP_OUTPUT_DIR. When set,
                       produced files also come back as `public_url`.
  MCP_FETCH_URLS       "1" lets file path arguments be http(s) URLs, fetched
                       into MCP_OUTPUT_DIR/inbox before the tool runs.

Fetching is off by default and, when on, refuses hosts that resolve to
non-public addresses (loopback, link-local, private ranges, cloud metadata)
unless MCP_FETCH_ALLOW_PRIVATE=1 — an authenticated caller must not be able to
turn this server into a probe of the network it is deployed on. Redirects are
re-checked against the same rule so a public host cannot bounce the fetch
inward.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import tempfile
import time
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

# One tool call can resolve the same argument more than once; without this
# cache every one of those would re-download. The TTL is short so an updated
# file at the same URL is picked up by the next request instead of being
# pinned for the lifetime of a long-running server process.
_FETCH_CACHE_TTL_SECONDS = 300
_FETCH_TIMEOUT_SECONDS = 60
_DEFAULT_MAX_FETCH_MB = 100
_MAX_FILENAME_LEN = 120

_fetch_cache: dict[str, tuple[float, Path]] = {}

_TRUTHY = ("1", "true", "yes", "on")
_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_DISPOSITION_NAME = re.compile(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", re.IGNORECASE)

# Content-Type -> extension, used only when the URL gives no usable suffix
# (e.g. https://host/export?id=7). Without a suffix the downloaded file would
# be rejected downstream by tools that dispatch on extension.
_TYPE_SUFFIXES = {
    "text/csv": ".csv",
    "application/csv": ".csv",
    "application/json": ".json",
    "text/json": ".json",
    "text/html": ".html",
    "text/plain": ".txt",
    "application/pdf": ".pdf",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/octet-stream": "",
}


def _umask_default_mode() -> int:
    """Return the mode a plain open() would create: 0o666 masked by the umask.

    Read once at import, while the process is still single-threaded — reading
    a umask requires setting it, which is process-wide and would otherwise
    race any thread creating a file at that instant.
    """
    current = os.umask(0o022)
    os.umask(current)
    return 0o666 & ~current


# Temp-file helpers (mkstemp, NamedTemporaryFile) create 0600 by design, and a
# rename preserves it. That is wrong for anything written into a *shared*
# directory: the file server in front of it, and every sibling service, have
# to be able to read what lands there. Atomic writers apply this instead.
DEFAULT_FILE_MODE = _umask_default_mode()


def apply_default_mode(path: Path | str) -> None:
    """Relax a temp file's 0600 to what a plain open() would have produced."""
    try:
        os.chmod(path, DEFAULT_FILE_MODE)
    except OSError:
        pass


def _flag(name: str) -> bool:
    """Return True when an env var is set to a truthy string."""
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def get_output_dir() -> Path:
    """Return the directory generated files default into, creating it."""
    override = os.environ.get("MCP_OUTPUT_DIR", "").strip()
    out = Path(override) if override else Path.home() / "Downloads"
    out.mkdir(parents=True, exist_ok=True)
    return out


def get_inbox_dir() -> Path:
    """Return the directory fetched URL inputs land in, creating it."""
    inbox = get_output_dir() / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    return inbox


def public_url_for(path: Path | str) -> str:
    """Return the public URL of a path under MCP_OUTPUT_DIR, else empty string."""
    base = os.environ.get("MCP_PUBLIC_BASE_URL", "").strip().rstrip("/")
    root = os.environ.get("MCP_OUTPUT_DIR", "").strip()
    if not base or not root:
        return ""
    try:
        relative = Path(path).resolve().relative_to(Path(root).resolve())
    except OSError, ValueError:
        return ""
    return f"{base}/{quote(relative.as_posix())}"


def attach_public_url(result: dict[str, Any], path: Path | str) -> dict[str, Any]:
    """Add `public_url` to a result dict when the file is publicly served."""
    url = public_url_for(path)
    if url:
        result["public_url"] = url
    return result


def is_url(raw: str) -> bool:
    """Return True when raw looks like an http(s) URL rather than a path."""
    return raw.strip().lower().startswith(("http://", "https://"))


def url_fetch_enabled() -> bool:
    """Return True when this server is allowed to download http(s) inputs."""
    return _flag("MCP_FETCH_URLS")


def _max_fetch_bytes() -> int:
    """Return the download size cap in bytes (MCP_MAX_FETCH_MB, default 100)."""
    raw = os.environ.get("MCP_MAX_FETCH_MB", "").strip()
    try:
        megabytes = int(raw) if raw else _DEFAULT_MAX_FETCH_MB
    except ValueError:
        megabytes = _DEFAULT_MAX_FETCH_MB
    return max(1, megabytes) * 1024 * 1024


def assert_fetchable(url: str) -> None:
    """Raise ValueError unless url is http(s) on a publicly routable host."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http and https URLs can be fetched, got {parsed.scheme or 'no'} scheme.")
    host = parsed.hostname
    if not host:
        raise ValueError(f"URL has no host: {url}")
    if _flag("MCP_FETCH_ALLOW_PRIVATE"):
        return
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve host '{host}': {exc}") from exc
    for info in infos:
        address = ipaddress.ip_address(str(info[4][0]).split("%")[0])
        if not address.is_global:
            raise ValueError(
                f"Refusing to fetch '{host}': it resolves to the non-public address {address}. "
                "Set MCP_FETCH_ALLOW_PRIVATE=1 on the server if it is meant to reach that host."
            )


class _GuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-check every redirect target so a public host can't bounce us inward."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        assert_fetchable(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _safe_filename(url: str, headers: Any) -> str:
    """Derive a safe local filename from Content-Disposition, URL, or type."""
    name = ""
    disposition = headers.get("Content-Disposition", "") if headers else ""
    match = _DISPOSITION_NAME.search(disposition or "")
    if match:
        name = unquote(match.group(1))
    if not name:
        name = unquote(Path(urlparse(url).path).name)
    name = _UNSAFE_NAME_CHARS.sub("_", name).strip("._")[:_MAX_FILENAME_LEN]
    if not name:
        name = "download"
    if not Path(name).suffix:
        content_type = (headers.get("Content-Type", "") if headers else "").split(";")[0].strip().lower()
        name += _TYPE_SUFFIXES.get(content_type, "")
    return name


def fetch_url(url: str, dest_dir: Path | None = None) -> Path:
    """Download an http(s) URL into the inbox dir and return the local path.

    Raises:
        ValueError: fetching disabled, non-public host, or response too large.
    """
    url = url.strip()
    if not url_fetch_enabled():
        raise ValueError(
            f"This server does not fetch URLs: {url}. "
            "Set MCP_FETCH_URLS=1 on the server to enable it, or pass a local file path."
        )

    cached = _fetch_cache.get(url)
    if cached and time.time() - cached[0] < _FETCH_CACHE_TTL_SECONDS and cached[1].exists():
        return cached[1]

    assert_fetchable(url)
    limit = _max_fetch_bytes()
    opener = urllib.request.build_opener(
        _GuardedRedirectHandler(),
        urllib.request.HTTPCookieProcessor(CookieJar()),
    )
    request = urllib.request.Request(url, headers={"User-Agent": "mcp-file-exchange/1.0"})
    try:
        with opener.open(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
            declared = response.headers.get("Content-Length", "")
            if declared.isdigit() and int(declared) > limit:
                raise ValueError(f"Download is larger than the {limit // (1024 * 1024)} MB limit: {url}")
            name = _safe_filename(url, response.headers)
            payload = response.read(limit + 1)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Could not download {url}: {exc}") from exc

    if len(payload) > limit:
        raise ValueError(f"Download is larger than the {limit // (1024 * 1024)} MB limit: {url}")

    target = (dest_dir or get_inbox_dir()) / name
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=str(target.parent))
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
        apply_default_mode(temp_name)
        os.replace(temp_name, target)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise

    _fetch_cache[url] = (time.time(), target)
    return target
