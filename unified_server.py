"""Combined HTTP entry point — all 11 sub-servers in ONE process, ONE port.

Each sub-server keeps its own server.py for stdio / individual-HTTP use
(LM Studio "add one sub-server" installs, local dev). This file is
Docker/remote-deployment-only: it imports each sub-server's already-built
FastMCP instance (raw MCP SDK, not the `fastmcp` package) and mounts its
HTTP app at its own path prefix inside one Starlette app, so
python-docx/openpyxl/python-pptx load ONCE instead of eleven times. Each
sub-server's own /health, /version, and /mcp routes (added via
@mcp.custom_route in its own server.py) come along for free under the
mount prefix — nothing sub-server-specific is duplicated here.

Lifespans do NOT propagate through Starlette's Mount() automatically, so
each sub-server's session-manager lifespan is entered explicitly via
AsyncExitStack. The raw MCP SDK's FastMCP.streamable_http_app() returns a
plain Starlette instance (unlike the `fastmcp` package's StarletteWithLifespan,
which exposes a convenience `.lifespan` attribute) — its lifespan is reached
via `app.router.lifespan_context`. Verified live against 2 real sub-servers
before wiring up all 11 (see MCP_Machine_Learning's unified_server.py for
the fastmcp-package version of the same pattern, prototyped first).
"""

from __future__ import annotations

import argparse
import os
from contextlib import AsyncExitStack, asynccontextmanager

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Mount, Route

from servers.docx_basic.docx_basic.server import mcp as docx_basic_mcp
from servers.docx_layout.docx_layout.server import mcp as docx_layout_mcp
from servers.docx_new.docx_new.server import mcp as docx_new_mcp
from servers.docx_tables.docx_tables.server import mcp as docx_tables_mcp
from servers.office_domain.office_domain.server import _oauth_bridge as _domain_bridge
from servers.office_domain.office_domain.server import mcp as domain_mcp
from servers.pptx_basic.pptx_basic.server import mcp as pptx_basic_mcp
from servers.pptx_design.pptx_design.server import mcp as pptx_design_mcp
from servers.pptx_new.pptx_new.server import mcp as pptx_new_mcp
from servers.xlsx_basic.xlsx_basic.server import mcp as xlsx_basic_mcp
from servers.xlsx_charts.xlsx_charts.server import mcp as xlsx_charts_mcp
from servers.xlsx_formulas.xlsx_formulas.server import mcp as xlsx_formulas_mcp
from servers.xlsx_new.xlsx_new.server import mcp as xlsx_new_mcp
from shared.exchange import upload_route

_VERSION = "0.2.0"

_SUB_SERVERS = {
    "docx-basic": docx_basic_mcp,
    "docx-tables": docx_tables_mcp,
    "docx-layout": docx_layout_mcp,
    "docx-new": docx_new_mcp,
    "xlsx-basic": xlsx_basic_mcp,
    "xlsx-formulas": xlsx_formulas_mcp,
    "xlsx-charts": xlsx_charts_mcp,
    "xlsx-new": xlsx_new_mcp,
    "pptx-basic": pptx_basic_mcp,
    "pptx-design": pptx_design_mcp,
    "pptx-new": pptx_new_mcp,
}
# Each sub-server's FastMCP defaults to host="127.0.0.1", which auto-enables
# DNS-rebinding Host-header validation restricted to 127.0.0.1/localhost. The
# unified server sits behind Caddy on a public hostname (e.g.
# office.casava.space) forwarded via `header_up Host {host}`, so that check
# rejects every real remote request with "Invalid Host header". Caddy is
# already the trust boundary here, so disable it for the mounted sub-apps.
for _sub_mcp in (*_SUB_SERVERS.values(), domain_mcp):
    _sub_mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

_sub_apps = {name: mcp.streamable_http_app() for name, mcp in _SUB_SERVERS.items()}
# The ten domain tools, served at the root: /mcp. Every tier above keeps its
# own endpoint; see servers/office_domain/office_domain/server.py.
_domain_app = domain_mcp.streamable_http_app()


@asynccontextmanager
async def _combined_lifespan(app):
    async with AsyncExitStack() as stack:
        for sub_app in (*_sub_apps.values(), _domain_app):
            await stack.enter_async_context(sub_app.router.lifespan_context(sub_app))
        yield


async def _root_health(request: Request) -> JSONResponse:
    """Aggregate liveness check. Unauthenticated."""
    return JSONResponse({"status": "ok", "version": _VERSION, "sub_servers": list(_SUB_SERVERS)})


async def _root_version(request: Request) -> JSONResponse:
    """Report running version. Unauthenticated."""
    return JSONResponse({"current": _VERSION})


async def _root(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "server": "MCP_Microsoft_Office",
            "mcp": "/mcp",
            "sub_servers": {name: f"/{name}/mcp" for name in _SUB_SERVERS},
        }
    )


def _redirect(target: str):
    """308 redirect to a sub-server's real well-known route.

    RFC 8414/9728 clients build discovery URLs by inserting
    `/.well-known/...` between the origin and the resource/issuer path
    (e.g. `/.well-known/oauth-protected-resource/docx-basic`), landing at
    the OUTER app's root. But Mount() nests each sub-server's real
    well-known routes under its own prefix (`/docx-basic/.well-known/...`)
    instead, so the client's computed URL 404s without this redirect —
    confirmed live against a real unauthenticated claude.ai connector
    attempt. Unlike the fastmcp-package sibling repos, the raw SDK's
    resource URL has no /mcp suffix, so the protected-resource source path
    doesn't get one either.
    """

    async def _handler(request: Request) -> RedirectResponse:
        return RedirectResponse(target, status_code=308)

    return _handler


# Both protected-resource paths lead to the sub-server's metadata. The 401
# names .../oauth-protected-resource/<name> (the SDK's resource URL has no
# /mcp), and a client derives .../oauth-protected-resource/<name>/mcp from the
# URL it connects to (RFC 9728) -- the resource that metadata itself declares.
# Only the first was redirected, so the second was a 404.
_discovery_redirects = [
    route
    for name in _SUB_SERVERS
    for route in (
        Route(
            f"/.well-known/oauth-protected-resource/{name}", _redirect(f"/{name}/.well-known/oauth-protected-resource")
        ),
        Route(
            f"/.well-known/oauth-protected-resource/{name}/mcp",
            _redirect(f"/{name}/.well-known/oauth-protected-resource"),
        ),
        Route(
            f"/.well-known/oauth-authorization-server/{name}",
            _redirect(f"/{name}/.well-known/oauth-authorization-server"),
        ),
    )
]

# Discovery for /mcp. A client connecting https://host/mcp asks, per RFC 9728,
# for /.well-known/oauth-protected-resource/mcp, and the 401 names the bare
# /.well-known/oauth-protected-resource. Mounted at the root, the SDK's own
# metadata route would answer the second with the origin as the resource (not
# .../mcp), and nothing would answer the first -- found live on
# MCP_Data_Analyst. The bridge's metadata is the one consistent with its
# authorization server at the root, so both paths go to it.
_domain_discovery = (
    []
    if _domain_bridge is None
    else [
        Route("/.well-known/oauth-protected-resource/mcp", _domain_bridge.protected_resource),
        Route("/.well-known/oauth-protected-resource", _domain_bridge.protected_resource),
    ]
)

app = Starlette(
    routes=[
        Route("/health", _root_health),
        Route("/version", _root_version),
        Route("/", _root),
        # Off unless MCP_UPLOAD_URLS=1 and MCP_UPLOAD_BASE_URL are set, and then
        # outside the tiers' bearer auth: the signed, single-use token in the
        # path is the credential (shared/exchange.py, upload URLs).
        Route("/upload/{token}", upload_route, methods=["PUT", "POST"]),
        *_discovery_redirects,
        *_domain_discovery,
        *(Mount(f"/{name}", app=sub_app) for name, sub_app in _sub_apps.items()),
        # Last, so every route above wins: /mcp and the domain server's own
        # OAuth routes answer at the root.
        Mount("", app=_domain_app),
    ],
    lifespan=_combined_lifespan,
)


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="MCP_Microsoft_Office unified server")
    parser.add_argument("--host", default=os.environ.get("OFFICE_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("OFFICE_PORT", "8830")))
    args = parser.parse_args()
    # timeout_keep_alive must exceed the reverse proxy's idle-connection pool,
    # or the proxy reuses a connection this server has already closed. uvicorn's
    # default is 5s and Caddy pools for 2 minutes, so every connection idle
    # between the two was dead here and live there. Reusing one gave Caddy
    # "aborting with incomplete response ... use of closed network connection",
    # which it turned into a 200 with zero bytes: the tool call had run, and the
    # caller hung until its own timeout believing it had failed. Measured
    # against the deployment: idle 2s reused fine, idle 7s closed.
    keepalive = int(os.environ.get("MCP_KEEPALIVE_SECONDS", "300"))
    # Serving over HTTP means the caller is remote: paths are held to the data
    # folder and workspaces, and a caller's path is never expanded against this
    # server's environment. On by default here as well as in docker-compose.yml,
    # so a deployment started any other way is confined too.
    os.environ.setdefault("MCP_CONFINE_PATHS", "1")
    uvicorn.run(app, host=args.host, port=args.port, timeout_keep_alive=keepalive)


if __name__ == "__main__":
    main()
