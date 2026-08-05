"""Bearer-token auth for HTTP transport (raw `mcp` SDK). No OAuth server.

Every servers/<name> package depends on `shared` already, so this lives here
rather than being duplicated 11x — unlike engine.py, shared/ has no
"zero MCP imports" restriction in this repo's CLAUDE.md (that rule is
engine.py-specific), so this is a safe home for it.
"""

from __future__ import annotations

import json
import os

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl


class _StaticTokenVerifier(TokenVerifier):
    def __init__(self, named_tokens: dict[str, str]) -> None:
        self._by_token = {token: name for name, token in named_tokens.items()}

    async def verify_token(self, token: str) -> AccessToken | None:
        name = self._by_token.get(token)
        if name is None:
            return None
        return AccessToken(token=token, client_id=name, scopes=[])


def _named_tokens_from_file(path: str) -> dict[str, str]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {str(name): str(token) for name, token in data.items()}


def _named_tokens_from_inline(spec: str) -> dict[str, str]:
    pairs = [p for p in spec.split(",") if p.strip()]
    return {name.strip(): token.strip() for name, token in (p.split(":", 1) for p in pairs)}


def build_auth(prefix: str, host: str, port: int) -> tuple[TokenVerifier, AuthSettings] | tuple[None, None]:
    """Build (token_verifier, auth_settings) from env vars, Folio-style priority.

    <PREFIX>_TOKENS_FILE (named tokens, JSON {name: token})
      > <PREFIX>_TOKENS (inline "name:token,name2:token2")
      > <PREFIX>_API_KEY (single shared token)
      > (None, None) (open mode — no auth, for localhost/private-network use only).
    """
    tokens_file = os.environ.get(f"{prefix}_TOKENS_FILE", "").strip()
    if tokens_file:
        named = _named_tokens_from_file(tokens_file)
    else:
        inline = os.environ.get(f"{prefix}_TOKENS", "").strip()
        if inline:
            named = _named_tokens_from_inline(inline)
        else:
            api_key = os.environ.get(f"{prefix}_API_KEY", "").strip()
            named = {"default": api_key} if api_key else {}

    if not named:
        return None, None

    base_url = AnyHttpUrl(f"http://{host}:{port}")
    return _StaticTokenVerifier(named), AuthSettings(issuer_url=base_url, resource_server_url=base_url)
