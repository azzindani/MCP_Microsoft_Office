"""A tier's 401 names a metadata URL, and that URL answers.

A client that meets a 401 on https://host/<tier>/mcp reads the
`resource_metadata` URL in WWW-Authenticate and fetches it; failing that, it
derives /.well-known/oauth-protected-resource/<tier>/mcp from the URL it
connected to (RFC 9728). The SDK builds the first from the tier's resource
URL, which has no /mcp, so the two differ -- and the unified server redirected
only one of them to the tier's metadata. The other was a 404, found live on
every tier of the fleet's four mounted repos. Both must reach the same
metadata, whose resource is the URL the client connected to.

Run in a fresh interpreter: the OAuth bridge exists only when a key is
configured at import time.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    "docx-basic",
    "docx-tables",
    "docx-layout",
    "docx-new",
    "xlsx-basic",
    "xlsx-formulas",
    "xlsx-charts",
    "xlsx-new",
    "pptx-basic",
    "pptx-design",
    "pptx-new",
)
PUBLIC = "https://office.example.test"

PROBE = """
import json
import os
from starlette.testclient import TestClient
import unified_server

out = {}
with TestClient(unified_server.app, base_url=os.environ["OFFICE_PUBLIC_URL"]) as c:
    for name in unified_server._SUB_SERVERS:
        r = c.post(f"/{name}/mcp", json={}, headers={"Accept": "application/json, text/event-stream"})
        hint = r.headers.get("www-authenticate", "")
        named = hint.split('resource_metadata="', 1)[1].split('"', 1)[0] if 'resource_metadata="' in hint else ""
        path = "/" + named.split("://", 1)[-1].split("/", 1)[-1] if named else ""
        seen = {"status": r.status_code, "named": named}
        for key, url in (("at_named", path), ("at_derived", f"/.well-known/oauth-protected-resource/{name}/mcp")):
            got = c.get(url) if url else None
            seen[key] = got.json() if got is not None and got.status_code == 200 else getattr(got, "status_code", None)
        out[name] = seen
print(json.dumps(out))
"""


@pytest.fixture(scope="module")
def discovery(tmp_path_factory) -> dict:
    state = tmp_path_factory.mktemp("oauth-state")
    env = {**os.environ, "OFFICE_API_KEY": "test-key-not-a-secret", "OFFICE_PUBLIC_URL": PUBLIC}
    for name in (*NAMES, "domain"):
        env[f"OFFICE_{name.upper().replace('-', '_')}_OAUTH_STATE_DIR"] = str(state / name)
    done = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_every_tier_was_probed(discovery):
    assert sorted(discovery) == sorted(NAMES)


@pytest.mark.parametrize("name", NAMES)
def test_the_url_a_tiers_401_names_answers_with_its_metadata(discovery, name):
    seen = discovery[name]
    assert seen["status"] == 401
    assert seen["named"] == f"{PUBLIC}/.well-known/oauth-protected-resource/{name}"
    assert isinstance(seen["at_named"], dict), f"{seen['named']} answered {seen['at_named']}"
    assert seen["at_named"]["resource"] == f"{PUBLIC}/{name}/mcp"


@pytest.mark.parametrize("name", NAMES)
def test_the_url_a_client_derives_answers_the_same(discovery, name):
    seen = discovery[name]
    assert isinstance(seen["at_derived"], dict), f"derived path answered {seen['at_derived']}"
    assert seen["at_derived"] == seen["at_named"]
