#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# MCP_Microsoft_Office — remote testing protocol (Cloudflare Quick Tunnel).
#
# Brings the local Docker deployment up and exposes each sub-server through
# an ephemeral *.trycloudflare.com URL — no account, no DNS, no config.
# Same pattern as azzindani/Folio's launch.sh, adapted for a docker-compose
# stack with N services instead of a single process.
#
# This makes the server reachable by ANY MCP-compatible harness or AI
# platform (Claude, ChatGPT custom connectors, LM Studio, etc.) without
# deploying to a VPS — useful for a quick remote smoke test.
#
# Usage:
#   ./launch_tunnel.sh              # docker compose up -d --build, then tunnel
#   SKIP_BUILD=1 ./launch_tunnel.sh # skip the build/up step, tunnel only
#   ./launch_tunnel.sh stop         # stop tunnels (leaves containers running)
#
# NOT for production. Quick Tunnels are unauthenticated at the transport
# level — set <PREFIX>_API_KEY / <PREFIX>_TOKENS_FILE in .env before running
# this so the exposed /mcp endpoint still requires a bearer token.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# name:host_port pairs — one per sub-server. Edit for this repo's services.
PORTS=(
  "docx-basic:8830"
  "docx-tables:8831"
  "docx-layout:8832"
  "docx-new:8833"
  "xlsx-basic:8834"
  "xlsx-formulas:8835"
  "xlsx-charts:8836"
  "xlsx-new:8837"
  "pptx-basic:8838"
  "pptx-design:8839"
  "pptx-new:8840"

)

LOG_DIR="/tmp/office-tunnels"
mkdir -p "$LOG_DIR"

if [ "${1:-}" = "stop" ]; then
  pkill -f "cloudflared tunnel --url http://localhost" 2>/dev/null && echo "tunnels stopped" || echo "no tunnels running"
  exit 0
fi

if ! command -v cloudflared &>/dev/null; then
  echo "[launch_tunnel] installing cloudflared..."
  curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o /usr/local/bin/cloudflared
  chmod +x /usr/local/bin/cloudflared
fi

if [ "${SKIP_BUILD:-0}" != "1" ]; then
  echo "[launch_tunnel] docker compose up -d --build"
  docker compose up -d --build
fi

pkill -f "cloudflared tunnel --url http://localhost" 2>/dev/null || true
sleep 1

echo "[launch_tunnel] waiting for services to report healthy..."
for entry in "${PORTS[@]}"; do
  port="${entry##*:}"
  for i in $(seq 1 30); do
    curl -fsS "http://localhost:${port}/health" >/dev/null 2>&1 && break
    sleep 1
  done
done

echo "[launch_tunnel] starting cloudflared quick tunnels..."
declare -A URLS
for entry in "${PORTS[@]}"; do
  name="${entry%%:*}"
  port="${entry##*:}"
  log="$LOG_DIR/${name}.log"
  : > "$log"
  nohup cloudflared tunnel --url "http://localhost:${port}" > "$log" 2>&1 &
done

echo "[launch_tunnel] waiting up to 30s per tunnel for a public URL..."
for entry in "${PORTS[@]}"; do
  name="${entry%%:*}"
  port="${entry##*:}"
  log="$LOG_DIR/${name}.log"
  url=""
  for i in $(seq 1 30); do
    url=$(grep -oP 'https://[a-z0-9\-]+\.trycloudflare\.com' "$log" 2>/dev/null | head -1)
    [ -n "$url" ] && break
    sleep 1
  done
  URLS[$name]="${url:-<not found, check $log>}"
done

echo ""
echo "  remote endpoints:"
for entry in "${PORTS[@]}"; do
  name="${entry%%:*}"
  port="${entry##*:}"
  echo "    ${name} (:${port})  ->  ${URLS[$name]}/mcp"
done
echo ""
echo "  health checks:"
for entry in "${PORTS[@]}"; do
  name="${entry%%:*}"
  echo "    ${URLS[$name]}/health"
done
echo ""
echo "  stop tunnels:  ./launch_tunnel.sh stop"
