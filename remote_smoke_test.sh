#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# MCP_Microsoft_Office — remote smoke test.
#
# NOT part of pytest / CI (see CLAUDE.md §15 "Remote smoke tests"). This
# script is the separate, manual/on-demand check that actually exercises the
# deployed HTTP endpoint: real auth enforcement + a real round trip through
# two different mounted sub-servers, producing a real .docx file, against
# the real public domain. This is exactly the kind of check that caught the
# "Invalid Host header" DNS-rebinding regression (see CLAUDE.md, Transport
# and Deployment) — a /health check alone would not have found it.
#
# Usage:
#   ./remote_smoke_test.sh                          # reads OFFICE_API_KEY from .env
#   OFFICE_API_KEY=sk-... ./remote_smoke_test.sh     # or pass it directly
#   DOMAIN=http://localhost:8830 ./remote_smoke_test.sh   # test a different target
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

DOMAIN="${DOMAIN:-https://office.casava.space}"
if [ -f .env ]; then
  set -a; source .env; set +a
fi
KEY="${OFFICE_API_KEY:?Set OFFICE_API_KEY (env var or .env file) before running}"
DOC_PATH="/tmp/remote-smoke-test/report.docx"

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; exit 1; }

echo "Target: $DOMAIN"
echo
echo "== auth enforcement =="

code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$DOMAIN/docx-new/mcp" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}')
[ "$code" = "401" ] && pass "no token -> 401" || fail "no token -> expected 401, got $code"

SID_NEW=$(curl -s -i -X POST "$DOMAIN/docx-new/mcp" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H "Authorization: Bearer $KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}' \
  | grep -i mcp-session-id | tr -d '\r' | awk '{print $2}')
[ -n "$SID_NEW" ] && pass "valid token -> session established on /docx-new" || fail "valid token -> no session id returned"

curl -s -X POST "$DOMAIN/docx-new/mcp" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H "Authorization: Bearer $KEY" -H "mcp-session-id: $SID_NEW" \
  -d '{"jsonrpc":"2.0","id":2,"method":"notifications/initialized"}' > /dev/null

echo
echo '== prompt: "create a doc titled Remote Smoke Test" -> create_from_text (/docx-new) =='
RESULT=$(curl -s -X POST "$DOMAIN/docx-new/mcp" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H "Authorization: Bearer $KEY" -H "mcp-session-id: $SID_NEW" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"create_from_text\",\"arguments\":{\"output_path\":\"$DOC_PATH\",\"paragraphs\":[{\"text\":\"Remote Smoke Test\",\"style\":\"Title\"},{\"text\":\"Created by remote_smoke_test.sh.\",\"style\":\"Normal\"}]}}}")
echo "$RESULT" | grep -q '"isError":false' && pass "create_from_text wrote a real .docx on the host" || fail "unexpected result: $RESULT"

echo
echo '== prompt: "read it back" -> read_document (/docx-basic, different sub-server) =='
SID_BASIC=$(curl -s -i -X POST "$DOMAIN/docx-basic/mcp" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H "Authorization: Bearer $KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}' \
  | grep -i mcp-session-id | tr -d '\r' | awk '{print $2}')
curl -s -X POST "$DOMAIN/docx-basic/mcp" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H "Authorization: Bearer $KEY" -H "mcp-session-id: $SID_BASIC" \
  -d '{"jsonrpc":"2.0","id":2,"method":"notifications/initialized"}' > /dev/null

RESULT=$(curl -s -X POST "$DOMAIN/docx-basic/mcp" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H "Authorization: Bearer $KEY" -H "mcp-session-id: $SID_BASIC" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"read_document\",\"arguments\":{\"file_path\":\"$DOC_PATH\"}}}")
echo "$RESULT" | grep -q 'Remote Smoke Test' && pass "read_document read the real file back — full round trip across two sub-servers in one process" || fail "unexpected result: $RESULT"

echo
echo "ALL CHECKS PASSED against $DOMAIN"
