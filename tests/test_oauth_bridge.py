"""Tests for the claude.ai Custom Connector OAuth 2.0 bridge (oauth_bridge.py)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.testclient import TestClient

from shared.oauth_bridge import OAuthBridge

DEFAULT_TOKENS = {"test-secret-123": "default"}
REDIRECT_URI = "https://claude.ai/cb"


def _make_client(tmp_path, tokens: dict[str, str] | None = None) -> tuple[TestClient, OAuthBridge]:
    by_token = tokens if tokens is not None else DEFAULT_TOKENS

    def lookup_principal(presented: str) -> str | None:
        return by_token.get(presented)

    bridge = OAuthBridge("TEST", lookup_principal, state_dir=str(tmp_path))
    routes = [
        Route("/.well-known/oauth-authorization-server", bridge.metadata, methods=["GET"]),
        Route("/.well-known/oauth-protected-resource", bridge.protected_resource, methods=["GET"]),
        Route("/oauth/register", bridge.register, methods=["POST"]),
        Route("/oauth/authorize", bridge.authorize_get, methods=["GET"]),
        Route("/oauth/authorize", bridge.authorize_post, methods=["POST"]),
        Route("/oauth/token", bridge.token, methods=["POST"]),
    ]
    app = Starlette(routes=routes)
    return TestClient(app, base_url="http://testserver"), bridge


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _register_client(client: TestClient) -> str:
    resp = client.post("/oauth/register", json={"redirect_uris": [REDIRECT_URI]})
    assert resp.status_code == 201
    return resp.json()["client_id"]


def _get_code(
    client: TestClient,
    client_id: str,
    api_key: str = "test-secret-123",
    redirect_uri: str = REDIRECT_URI,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
) -> str:
    data = {"api_key": api_key, "client_id": client_id, "redirect_uri": redirect_uri}
    if code_challenge:
        data["code_challenge"] = code_challenge
        data["code_challenge_method"] = code_challenge_method
    resp = client.post("/oauth/authorize", data=data, follow_redirects=False)
    assert resp.status_code == 302
    return parse_qs(urlparse(resp.headers["location"]).query)["code"][0]


def _exchange_code(client: TestClient, code: str, redirect_uri: str = REDIRECT_URI, **extra) -> dict:
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, **extra}
    resp = client.post("/oauth/token", data=data)
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestMetadata:
    def test_authorization_server_metadata(self, tmp_path):
        client, _ = _make_client(tmp_path)
        resp = client.get("/.well-known/oauth-authorization-server")
        assert resp.status_code == 200
        body = resp.json()
        assert body["authorization_endpoint"].endswith("/oauth/authorize")
        assert body["token_endpoint"].endswith("/oauth/token")
        assert "S256" in body["code_challenge_methods_supported"]
        assert "authorization_code" in body["grant_types_supported"]
        assert "refresh_token" in body["grant_types_supported"]

    def test_protected_resource_metadata(self, tmp_path):
        client, _ = _make_client(tmp_path)
        resp = client.get("/.well-known/oauth-protected-resource")
        assert resp.status_code == 200
        assert resp.json()["resource"].endswith("/mcp")

    def test_metadata_includes_mount_prefix(self, tmp_path):
        """Regression: unified_server.py-style deployments mount each tier's
        app under a path (e.g. /basic via Starlette's Mount()). Advertised
        endpoints that omit that prefix send the client to a 404 -- caught by
        an actual live test against MCP_Machine_Learning's unified_server.py
        before this test was written to lock in the fix."""
        bridge = OAuthBridge("TEST", lambda t: None, state_dir=str(tmp_path))
        mounted = Starlette(
            routes=[
                Mount(
                    "/basic",
                    routes=[
                        Route("/.well-known/oauth-authorization-server", bridge.metadata, methods=["GET"]),
                        Route("/.well-known/oauth-protected-resource", bridge.protected_resource, methods=["GET"]),
                        Route("/oauth/authorize", bridge.authorize_get, methods=["GET"]),
                    ],
                )
            ]
        )
        client = TestClient(mounted, base_url="http://testserver")

        meta = client.get("/basic/.well-known/oauth-authorization-server").json()
        assert meta["authorization_endpoint"] == "http://testserver/basic/oauth/authorize"
        assert meta["token_endpoint"] == "http://testserver/basic/oauth/token"
        assert meta["issuer"] == "http://testserver/basic"

        resource = client.get("/basic/.well-known/oauth-protected-resource").json()
        assert resource["resource"] == "http://testserver/basic/mcp"
        assert resource["authorization_servers"] == ["http://testserver/basic"]

        # The login form's own action must point back into the mount, not the
        # unmounted root, or submitting it 404s.
        form_resp = client.get(
            "/basic/oauth/authorize",
            params={"client_id": "x", "redirect_uri": "https://claude.ai/cb", "response_type": "code"},
        )
        assert 'action="http://testserver/basic/oauth/authorize"' in form_resp.text


class TestDynamicClientRegistration:
    def test_register_returns_client_id(self, tmp_path):
        client, _ = _make_client(tmp_path)
        assert _register_client(client).startswith("test-")

    def test_register_public_client_has_no_secret(self, tmp_path):
        client, _ = _make_client(tmp_path)
        resp = client.post("/oauth/register", json={"redirect_uris": [REDIRECT_URI]})
        assert "client_secret" not in resp.json()
        assert resp.json()["token_endpoint_auth_method"] == "none"

    def test_register_confidential_client_gets_secret(self, tmp_path):
        client, _ = _make_client(tmp_path)
        resp = client.post(
            "/oauth/register",
            json={"redirect_uris": [REDIRECT_URI], "token_endpoint_auth_method": "client_secret_post"},
        )
        assert "client_secret" in resp.json()

    def test_register_with_no_body_defaults_to_wildcard_redirect(self, tmp_path):
        client, _ = _make_client(tmp_path)
        resp = client.post("/oauth/register", content=b"")
        assert resp.status_code == 201
        assert resp.json()["redirect_uris"] == ["*"]


class TestAuthorize:
    def test_get_missing_params_rejected(self, tmp_path):
        client, _ = _make_client(tmp_path)
        assert client.get("/oauth/authorize").status_code == 400

    def test_get_non_code_response_type_rejected(self, tmp_path):
        client, _ = _make_client(tmp_path)
        resp = client.get(
            "/oauth/authorize",
            params={"client_id": "x", "redirect_uri": REDIRECT_URI, "response_type": "token"},
        )
        assert resp.status_code == 400

    def test_get_renders_login_form(self, tmp_path):
        client, _ = _make_client(tmp_path)
        client_id = _register_client(client)
        resp = client.get(
            "/oauth/authorize",
            params={"client_id": client_id, "redirect_uri": REDIRECT_URI, "response_type": "code"},
        )
        assert resp.status_code == 200
        assert "api_key" in resp.text
        assert client_id in resp.text

    def test_post_wrong_key_rejected(self, tmp_path):
        client, _ = _make_client(tmp_path)
        client_id = _register_client(client)
        resp = client.post(
            "/oauth/authorize", data={"api_key": "wrong", "client_id": client_id, "redirect_uri": REDIRECT_URI}
        )
        assert resp.status_code == 401

    def test_post_correct_key_redirects_with_code_and_state(self, tmp_path):
        client, _ = _make_client(tmp_path)
        client_id = _register_client(client)
        resp = client.post(
            "/oauth/authorize",
            data={"api_key": "test-secret-123", "client_id": client_id, "redirect_uri": REDIRECT_URI, "state": "xyz"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "code=" in resp.headers["location"]
        assert "state=xyz" in resp.headers["location"]

    def test_post_unknown_client_id_rejected(self, tmp_path):
        client, _ = _make_client(tmp_path)
        resp = client.post(
            "/oauth/authorize",
            data={"api_key": "test-secret-123", "client_id": "nonexistent", "redirect_uri": REDIRECT_URI},
        )
        assert resp.status_code == 400

    def test_post_unregistered_redirect_uri_rejected(self, tmp_path):
        client, _ = _make_client(tmp_path)
        client_id = _register_client(client)
        resp = client.post(
            "/oauth/authorize",
            data={"api_key": "test-secret-123", "client_id": client_id, "redirect_uri": "https://evil.example/cb"},
        )
        assert resp.status_code == 400

    def test_static_seeded_client_allows_any_redirect_uri(self, tmp_path):
        client, bridge = _make_client(tmp_path)
        resp = client.post(
            "/oauth/authorize",
            data={
                "api_key": "test-secret-123",
                "client_id": bridge._static_client_id,
                "redirect_uri": "https://anything.example/cb",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302


class TestTokenExchange:
    def test_authorization_code_grant_issues_tokens(self, tmp_path):
        client, _ = _make_client(tmp_path)
        client_id = _register_client(client)
        code = _get_code(client, client_id)
        body = _exchange_code(client, code)
        assert body["token_type"] == "Bearer"
        assert body["expires_in"] == 86400
        assert "access_token" in body and "refresh_token" in body

    def test_pkce_mismatch_rejected(self, tmp_path):
        client, _ = _make_client(tmp_path)
        client_id = _register_client(client)
        _, challenge = _pkce_pair()
        code = _get_code(client, client_id, code_challenge=challenge, code_challenge_method="S256")
        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": "wrong-verifier",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_grant"

    def test_pkce_correct_verifier_succeeds(self, tmp_path):
        client, _ = _make_client(tmp_path)
        client_id = _register_client(client)
        verifier, challenge = _pkce_pair()
        code = _get_code(client, client_id, code_challenge=challenge, code_challenge_method="S256")
        body = _exchange_code(client, code, code_verifier=verifier)
        assert "access_token" in body

    def test_code_is_one_shot(self, tmp_path):
        client, _ = _make_client(tmp_path)
        client_id = _register_client(client)
        code = _get_code(client, client_id)
        _exchange_code(client, code)
        second = client.post(
            "/oauth/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI}
        )
        assert second.status_code == 400

    def test_code_one_shot_even_on_failed_pkce(self, tmp_path):
        """A failed PKCE check still burns the code, so it can't be brute-forced."""
        client, _ = _make_client(tmp_path)
        client_id = _register_client(client)
        _, challenge = _pkce_pair()
        code = _get_code(client, client_id, code_challenge=challenge, code_challenge_method="S256")
        client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": "wrong",
            },
        )
        retry = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": "wrong-again",
            },
        )
        assert retry.status_code == 400
        assert retry.json()["error_description"].startswith("Auth code")

    def test_redirect_uri_mismatch_rejected(self, tmp_path):
        client, _ = _make_client(tmp_path)
        client_id = _register_client(client)
        code = _get_code(client, client_id)
        resp = client.post(
            "/oauth/token",
            data={"grant_type": "authorization_code", "code": code, "redirect_uri": "https://different.example/cb"},
        )
        assert resp.status_code == 400

    def test_unsupported_grant_type_rejected(self, tmp_path):
        client, _ = _make_client(tmp_path)
        resp = client.post("/oauth/token", data={"grant_type": "password"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "unsupported_grant_type"

    def test_garbage_code_rejected(self, tmp_path):
        client, _ = _make_client(tmp_path)
        resp = client.post(
            "/oauth/token", data={"grant_type": "authorization_code", "code": "garbage", "redirect_uri": REDIRECT_URI}
        )
        assert resp.status_code == 400

    def test_expired_code_rejected(self, tmp_path):
        client, bridge = _make_client(tmp_path)
        client_id = _register_client(client)
        code = _get_code(client, client_id)
        bridge._auth_codes[code]["expires_at"] = 0
        resp = client.post(
            "/oauth/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI}
        )
        assert resp.status_code == 400

    def test_refresh_token_rotates_and_old_one_dies(self, tmp_path):
        client, _ = _make_client(tmp_path)
        client_id = _register_client(client)
        code = _get_code(client, client_id)
        first = _exchange_code(client, code)

        refreshed = client.post(
            "/oauth/token", data={"grant_type": "refresh_token", "refresh_token": first["refresh_token"]}
        )
        assert refreshed.status_code == 200
        assert refreshed.json()["access_token"] != first["access_token"]

        reused = client.post(
            "/oauth/token", data={"grant_type": "refresh_token", "refresh_token": first["refresh_token"]}
        )
        assert reused.status_code == 400
        assert reused.json()["error"] == "invalid_grant"

    def test_garbage_refresh_token_rejected(self, tmp_path):
        client, _ = _make_client(tmp_path)
        resp = client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": "garbage"})
        assert resp.status_code == 400


class TestResolveOAuthToken:
    def test_issued_token_resolves_to_principal(self, tmp_path):
        client, bridge = _make_client(tmp_path)
        client_id = _register_client(client)
        code = _get_code(client, client_id)
        tokens = _exchange_code(client, code)
        assert bridge.resolve_oauth_token(tokens["access_token"]) == "default"

    def test_unknown_token_resolves_to_none(self, tmp_path):
        _, bridge = _make_client(tmp_path)
        assert bridge.resolve_oauth_token("garbage") is None

    def test_expired_token_resolves_to_none(self, tmp_path):
        client, bridge = _make_client(tmp_path)
        client_id = _register_client(client)
        code = _get_code(client, client_id)
        tokens = _exchange_code(client, code)
        bridge._access_tokens[tokens["access_token"]]["expires_at"] = 0
        assert bridge.resolve_oauth_token(tokens["access_token"]) is None


class TestPersistence:
    def test_access_tokens_survive_bridge_recreation(self, tmp_path):
        """Simulates a container restart: a fresh OAuthBridge reading the same state_dir."""
        client, _ = _make_client(tmp_path)
        client_id = _register_client(client)
        code = _get_code(client, client_id)
        tokens = _exchange_code(client, code)

        fresh = OAuthBridge("TEST", lambda t: DEFAULT_TOKENS.get(t), state_dir=str(tmp_path))
        assert fresh.resolve_oauth_token(tokens["access_token"]) == "default"

    def test_dcr_clients_do_not_persist_across_restart(self, tmp_path):
        """DCR registrations are in-memory only by design (matches Folio)."""
        client, bridge = _make_client(tmp_path)
        client_id = _register_client(client)
        assert client_id in bridge._clients

        fresh = OAuthBridge("TEST", lambda t: None, state_dir=str(tmp_path))
        assert client_id not in fresh._clients

    def test_static_client_id_configurable_via_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TEST_OAUTH_CLIENT_ID", "custom-id")
        monkeypatch.setenv("TEST_OAUTH_CLIENT_SECRET", "shh")
        bridge = OAuthBridge("TEST", lambda t: None, state_dir=str(tmp_path))
        assert "custom-id" in bridge._clients
        assert bridge._clients["custom-id"]["client_secret"] == "shh"


class TestRegisterRoutes:
    def test_mounts_all_six_endpoints(self, tmp_path):
        calls = []

        class _FakeMCP:
            def custom_route(self, path, methods):
                calls.append((path, tuple(methods)))
                return lambda fn: fn

        bridge = OAuthBridge("TEST", lambda t: None, state_dir=str(tmp_path))
        bridge.register_routes(_FakeMCP())
        paths = {c[0] for c in calls}
        assert paths == {
            "/.well-known/oauth-authorization-server",
            "/.well-known/oauth-protected-resource",
            "/oauth/register",
            "/oauth/authorize",
            "/oauth/token",
        }
        assert len(calls) == 6  # /oauth/authorize registered twice: GET + POST


class TestDeployAuthIntegration:
    def test_dynamic_verifier_falls_back_to_oauth_bridge(self, monkeypatch):
        monkeypatch.setenv("TEST4_API_KEY", "static-secret")
        from shared.deploy_auth import build_auth, build_oauth_bridge

        bridge = build_oauth_bridge("TEST4")
        assert bridge is not None
        verifier, auth_settings = build_auth("TEST4", "127.0.0.1", 19999, bridge)
        assert verifier is not None
        assert auth_settings is not None

        # static bearer token still works unchanged
        assert asyncio.run(verifier.verify_token("static-secret")).client_id == "default"
        # a token minted directly on the bridge (simulating a real OAuth exchange) also works
        access_token = bridge._issue_token_pair("default", "mcp")["access_token"]
        result = asyncio.run(verifier.verify_token(access_token))
        assert result is not None
        assert result.client_id == "default"
        # unknown token still rejected
        assert asyncio.run(verifier.verify_token("nope")) is None

    def test_build_oauth_bridge_none_in_open_mode(self, monkeypatch):
        monkeypatch.delenv("TEST5_TOKENS_FILE", raising=False)
        monkeypatch.delenv("TEST5_TOKENS", raising=False)
        monkeypatch.delenv("TEST5_API_KEY", raising=False)
        from shared.deploy_auth import build_oauth_bridge

        assert build_oauth_bridge("TEST5") is None

    def test_build_auth_open_mode_still_none(self, monkeypatch):
        monkeypatch.delenv("TEST6_TOKENS_FILE", raising=False)
        monkeypatch.delenv("TEST6_TOKENS", raising=False)
        monkeypatch.delenv("TEST6_API_KEY", raising=False)
        from shared.deploy_auth import build_auth

        verifier, auth_settings = build_auth("TEST6", "127.0.0.1", 19999)
        assert verifier is None
        assert auth_settings is None
