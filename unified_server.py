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
from servers.pptx_basic.pptx_basic.server import mcp as pptx_basic_mcp
from servers.pptx_design.pptx_design.server import mcp as pptx_design_mcp
from servers.pptx_new.pptx_new.server import mcp as pptx_new_mcp
from servers.xlsx_basic.xlsx_basic.server import mcp as xlsx_basic_mcp
from servers.xlsx_charts.xlsx_charts.server import mcp as xlsx_charts_mcp
from servers.xlsx_formulas.xlsx_formulas.server import mcp as xlsx_formulas_mcp
from servers.xlsx_new.xlsx_new.server import mcp as xlsx_new_mcp

_VERSION = "0.1.0"

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
for _sub_mcp in _SUB_SERVERS.values():
    _sub_mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

_sub_apps = {name: mcp.streamable_http_app() for name, mcp in _SUB_SERVERS.items()}


@asynccontextmanager
async def _combined_lifespan(app):
    async with AsyncExitStack() as stack:
        for sub_app in _sub_apps.values():
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


_discovery_redirects = [
    route
    for name in _SUB_SERVERS
    for route in (
        Route(
            f"/.well-known/oauth-protected-resource/{name}", _redirect(f"/{name}/.well-known/oauth-protected-resource")
        ),
        Route(
            f"/.well-known/oauth-authorization-server/{name}",
            _redirect(f"/{name}/.well-known/oauth-authorization-server"),
        ),
    )
]

app = Starlette(
    routes=[
        Route("/health", _root_health),
        Route("/version", _root_version),
        Route("/", _root),
        *_discovery_redirects,
        *(Mount(f"/{name}", app=sub_app) for name, sub_app in _sub_apps.items()),
    ],
    lifespan=_combined_lifespan,
)


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="MCP_Microsoft_Office unified server")
    parser.add_argument("--host", default=os.environ.get("OFFICE_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("OFFICE_PORT", "8830")))
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
