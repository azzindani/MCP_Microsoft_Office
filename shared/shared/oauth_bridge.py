"""OAuth 2.0 Authorization Code + PKCE bridge for claude.ai's Custom Connector.

Ports Folio's src/mcp/oauth.ts to Python. Bridges a standard OAuth surface to
the server's existing bearer-token registry: the access token issued by
/oauth/token is a fresh random string, but every MCP call presenting it is
treated as if the underlying principal (the API key typed at /oauth/authorize)
had sent that principal's own bearer token directly. Plain bearer tokens keep
working unchanged — this is additive, not a replacement.

Endpoints (mounted via mcp.custom_route in server.py):
    GET  /.well-known/oauth-authorization-server  — RFC 8414 metadata
    GET  /.well-known/oauth-protected-resource    — RFC 9728 metadata
    GET  /oauth/authorize                         — login form
    POST /oauth/authorize                         — form submit -> redirect w/ code
    POST /oauth/token                              — code/refresh_token -> access_token
    POST /oauth/register                           — RFC 7591 DCR (optional)

Access/refresh tokens are persisted to disk (state_dir) so a container
restart doesn't force claude.ai to reauthorize. Auth codes and DCR client
registrations are in-memory only (short TTL, this is a single-process deploy).
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import secrets
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlencode

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

AUTH_CODE_TTL_S = 10 * 60
ACCESS_TOKEN_TTL_S = 24 * 60 * 60
REFRESH_TOKEN_TTL_S = 30 * 24 * 60 * 60
REGISTERED_CLIENT_TTL_S = 7 * 24 * 60 * 60
REGISTERED_CLIENT_MAX = 256

LookupPrincipal = Callable[[str], "str | None"]


class OAuthBridge:
    """One instance per running server process. Call register_routes(mcp) to mount."""

    def __init__(self, prefix: str, lookup_principal: LookupPrincipal, state_dir: str | None = None) -> None:
        self._prefix = prefix
        self._lookup_principal = lookup_principal
        self._state_dir = Path(
            state_dir or os.environ.get(f"{prefix}_OAUTH_STATE_DIR", f"/tmp/{prefix.lower()}-oauth-state")
        )
        self._tokens_file = self._state_dir / "access-tokens.json"
        self._refresh_file = self._state_dir / "refresh-tokens.json"
        self._access_tokens: dict[str, dict] = self._load(self._tokens_file)
        self._refresh_tokens: dict[str, dict] = self._load(self._refresh_file)
        self._auth_codes: dict[str, dict] = {}
        self._clients: dict[str, dict] = {}

        static_id = os.environ.get(f"{prefix}_OAUTH_CLIENT_ID", "claude-ai")
        static_secret = os.environ.get(f"{prefix}_OAUTH_CLIENT_SECRET", "")
        self._static_client_id = static_id
        self._clients[static_id] = {
            "redirect_uris": ["*"],
            "client_secret": static_secret or None,
            "created_at": time.time(),
        }

    # ── persistence ──────────────────────────────────────────────────

    def _load(self, path: Path) -> dict[str, dict]:
        try:
            if not path.exists():
                return {}
            data = json.loads(path.read_text(encoding="utf-8"))
            now = time.time()
            return {k: v for k, v in data.items() if v.get("expires_at", 0) > now}
        except OSError, json.JSONDecodeError:
            return {}

    def _persist(self, tokens: dict[str, dict], path: Path) -> None:
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(tokens), encoding="utf-8")
        except OSError:
            pass

    def _reap(self) -> None:
        now = time.time()
        for k in [k for k, v in self._auth_codes.items() if v["expires_at"] < now]:
            del self._auth_codes[k]

        mutated = False
        for k in [k for k, v in self._access_tokens.items() if v["expires_at"] < now]:
            del self._access_tokens[k]
            mutated = True
        if mutated:
            self._persist(self._access_tokens, self._tokens_file)

        rmutated = False
        for k in [k for k, v in self._refresh_tokens.items() if v["expires_at"] < now]:
            del self._refresh_tokens[k]
            rmutated = True
        if rmutated:
            self._persist(self._refresh_tokens, self._refresh_file)

        for cid in [
            c
            for c in self._clients
            if c != self._static_client_id and now - self._clients[c]["created_at"] > REGISTERED_CLIENT_TTL_S
        ]:
            del self._clients[cid]
        if len(self._clients) > REGISTERED_CLIENT_MAX:
            ordered = sorted(
                (c for c in self._clients.items() if c[0] != self._static_client_id),
                key=lambda kv: kv[1]["created_at"],
            )
            while len(self._clients) > REGISTERED_CLIENT_MAX and ordered:
                cid, _ = ordered.pop(0)
                del self._clients[cid]

    def resolve_oauth_token(self, token: str) -> str | None:
        """Look up an OAuth-issued access token. Called from the TokenVerifier fallback path."""
        self._reap()
        rec = self._access_tokens.get(token)
        if not rec:
            return None
        if rec["expires_at"] < time.time():
            del self._access_tokens[token]
            return None
        return rec["principal"]

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _random_token(n: int = 32) -> str:
        return secrets.token_urlsafe(n)

    @staticmethod
    def _sha256_b64url(s: str) -> str:
        digest = hashlib.sha256(s.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    @staticmethod
    def _base_url(request: Request) -> str:
        """Scheme + host + the ASGI mount prefix, if any.

        When this bridge is mounted under a path (e.g. unified_server.py
        mounting a tier's app at /basic via Starlette's Mount()), Starlette
        sets scope["root_path"] to the consumed prefix. Every URL this class
        hands back to a client (metadata endpoints, the login form's own
        action) must include it, or the client ends up following a path that
        only exists at the unmounted root and 404s.
        """
        proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip() or request.url.scheme
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "localhost"
        root_path = request.scope.get("root_path", "")
        return f"{proto}://{host}{root_path}"

    def _issue_token_pair(self, principal: str, scope: str) -> dict:
        access_token = self._random_token()
        self._access_tokens[access_token] = {"principal": principal, "expires_at": time.time() + ACCESS_TOKEN_TTL_S}
        self._persist(self._access_tokens, self._tokens_file)

        refresh_token = self._random_token()
        self._refresh_tokens[refresh_token] = {"principal": principal, "expires_at": time.time() + REFRESH_TOKEN_TTL_S}
        self._persist(self._refresh_tokens, self._refresh_file)

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_TTL_S,
            "refresh_token": refresh_token,
            "scope": scope,
        }

    # ── route handlers ───────────────────────────────────────────────

    async def metadata(self, request: Request) -> JSONResponse:
        base = self._base_url(request)
        return JSONResponse(
            {
                "issuer": base,
                "authorization_endpoint": f"{base}/oauth/authorize",
                "token_endpoint": f"{base}/oauth/token",
                "registration_endpoint": f"{base}/oauth/register",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
                "scopes_supported": ["mcp"],
            }
        )

    async def protected_resource(self, request: Request) -> JSONResponse:
        base = self._base_url(request)
        return JSONResponse(
            {
                "resource": f"{base}/mcp",
                "authorization_servers": [base],
                "bearer_methods_supported": ["header"],
                "scopes_supported": ["mcp"],
            }
        )

    async def register(self, request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        redirect_uris = body.get("redirect_uris") if isinstance(body.get("redirect_uris"), list) else ["*"]
        client_id = f"{self._prefix.lower()}-{self._random_token(8)}"
        wants_secret = body.get("token_endpoint_auth_method") not in (None, "none")
        client_secret = self._random_token() if wants_secret else None
        self._clients[client_id] = {
            "redirect_uris": redirect_uris,
            "client_secret": client_secret,
            "created_at": time.time(),
        }
        resp = {
            "client_id": client_id,
            "redirect_uris": redirect_uris,
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post" if client_secret else "none",
        }
        if client_secret:
            resp["client_secret"] = client_secret
        return JSONResponse(resp, status_code=201)

    async def authorize_get(self, request: Request) -> Response:
        q = dict(request.query_params)
        for k in ("client_id", "redirect_uri", "response_type"):
            if not q.get(k):
                return HTMLResponse(
                    f"<h1>Bad request</h1><p>Missing <code>{html.escape(k)}</code>.</p>", status_code=400
                )
        if q.get("response_type") != "code":
            return HTMLResponse(
                "<h1>Bad request</h1><p>Only <code>response_type=code</code> is supported.</p>", status_code=400
            )

        hidden_fields = (
            "client_id",
            "redirect_uri",
            "response_type",
            "scope",
            "state",
            "code_challenge",
            "code_challenge_method",
        )
        hidden = "\n".join(
            f'<input type="hidden" name="{k}" value="{html.escape(q[k])}">'
            for k in hidden_fields
            if q.get(k) is not None
        )
        action = f"{self._base_url(request)}/oauth/authorize"
        return HTMLResponse(f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(self._prefix)} &middot; Authorize</title>
<style>
  body{{font-family:Inter,system-ui,sans-serif;background:#0e0e16;color:#e8e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
  .card{{background:#16182a;padding:32px;border-radius:12px;border:1px solid #2a2a4a;max-width:420px;width:100%}}
  h1{{margin:0 0 8px;font-size:20px;letter-spacing:-0.01em}}
  p{{color:#8892A4;font-size:14px;line-height:1.5;margin:0 0 16px}}
  label{{display:block;font-size:12px;text-transform:uppercase;letter-spacing:0.08em;color:#8892A4;margin-bottom:6px}}
  input{{width:100%;padding:10px 12px;background:#0e0e16;border:1px solid #2a2a4a;border-radius:6px;
    color:#e8e8f0;font:14px Inter,sans-serif;box-sizing:border-box}}
  button{{margin-top:16px;width:100%;padding:10px;background:#4C6FFF;color:white;border:0;border-radius:6px;font-weight:600;cursor:pointer}}
  code{{background:#0e0e16;padding:2px 6px;border-radius:4px;font-size:12px}}
</style></head>
<body><div class="card">
<h1>Authorize {html.escape(self._prefix)} access</h1>
<p>Client <code>{html.escape(q["client_id"])}</code> wants to use this MCP server. Paste your existing API key.</p>
<form method="POST" action="{html.escape(action)}">
{hidden}
<label for="api_key">API Key</label>
<input id="api_key" name="api_key" type="password" autocomplete="off" required>
<button type="submit">Authorize</button>
</form>
</div></body></html>""")

    async def authorize_post(self, request: Request) -> Response:
        form = await request.form()
        api_key = str(form.get("api_key", ""))
        principal = self._lookup_principal(api_key)
        if not principal:
            return HTMLResponse(
                '<h1>Invalid API key</h1><p><a href="javascript:history.back()">Go back</a></p>', status_code=401
            )

        client_id = str(form.get("client_id", ""))
        redirect_uri = str(form.get("redirect_uri", ""))
        client = self._clients.get(client_id)
        if not client:
            return HTMLResponse(
                "<h1>Unknown client_id</h1><p>Register first via <code>/oauth/register</code>.</p>", status_code=400
            )
        if "*" not in client["redirect_uris"] and redirect_uri not in client["redirect_uris"]:
            return HTMLResponse("<h1>Invalid redirect_uri</h1>", status_code=400)

        code = self._random_token()
        self._auth_codes[code] = {
            "principal": principal,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_challenge": form.get("code_challenge") or None,
            "code_challenge_method": form.get("code_challenge_method") or None,
            "scope": form.get("scope") or None,
            "expires_at": time.time() + AUTH_CODE_TTL_S,
        }

        params = {"code": code}
        if form.get("state"):
            params["state"] = str(form.get("state"))
        sep = "&" if "?" in redirect_uri else "?"
        return RedirectResponse(f"{redirect_uri}{sep}{urlencode(params)}", status_code=302)

    async def token(self, request: Request) -> JSONResponse:
        form = await request.form()
        grant = form.get("grant_type")

        if grant == "refresh_token":
            presented = str(form.get("refresh_token", ""))
            rec = self._refresh_tokens.get(presented)
            if not rec or rec["expires_at"] < time.time():
                self._refresh_tokens.pop(presented, None)
                self._persist(self._refresh_tokens, self._refresh_file)
                return JSONResponse(
                    {"error": "invalid_grant", "error_description": "Refresh token is missing, expired, or revoked."},
                    status_code=400,
                )
            del self._refresh_tokens[presented]
            return JSONResponse(self._issue_token_pair(rec["principal"], str(form.get("scope") or "mcp")))

        if grant != "authorization_code":
            return JSONResponse(
                {
                    "error": "unsupported_grant_type",
                    "error_description": "Supported grants: authorization_code, refresh_token.",
                },
                status_code=400,
            )

        code = str(form.get("code", ""))
        record = self._auth_codes.get(code)
        if not record or record["expires_at"] < time.time():
            self._auth_codes.pop(code, None)
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Auth code is missing, expired, or already used."},
                status_code=400,
            )
        del self._auth_codes[code]  # one-shot: delete on first read regardless of outcome

        if form.get("redirect_uri") != record["redirect_uri"]:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "redirect_uri mismatch."}, status_code=400
            )

        client = self._clients.get(record["client_id"])
        if client and client.get("client_secret"):
            if form.get("client_secret") != client["client_secret"]:
                return JSONResponse(
                    {"error": "invalid_client", "error_description": "client_secret mismatch."}, status_code=401
                )

        if record.get("code_challenge"):
            verifier = str(form.get("code_verifier", ""))
            method = record.get("code_challenge_method") or "plain"
            computed = self._sha256_b64url(verifier) if method == "S256" else verifier
            if computed != record["code_challenge"]:
                return JSONResponse(
                    {"error": "invalid_grant", "error_description": "PKCE code_verifier mismatch."}, status_code=400
                )

        return JSONResponse(self._issue_token_pair(record["principal"], record.get("scope") or "mcp"))

    def register_routes(self, mcp) -> None:
        """Mount all 6 OAuth endpoints via mcp.custom_route. Call once at server startup."""
        mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])(self.metadata)
        mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])(self.protected_resource)
        mcp.custom_route("/oauth/register", methods=["POST"])(self.register)
        mcp.custom_route("/oauth/authorize", methods=["GET"])(self.authorize_get)
        mcp.custom_route("/oauth/authorize", methods=["POST"])(self.authorize_post)
        mcp.custom_route("/oauth/token", methods=["POST"])(self.token)
