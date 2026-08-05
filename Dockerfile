# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────────────────────
# mcp-microsoft-office — production container, ONE process for all 11
# sub-servers (docx/xlsx/pptx x basic/tables/layout/new/formulas/charts/
# design). True uv workspace — needs `uv sync --all-packages` (plain
# `uv sync` only installs the root project's own deps, which are empty;
# each member's runtime deps only land in the shared venv via --all-packages).
#
# unified_server.py mounts each sub-server as a separate MCP endpoint
# (/docx-basic/mcp, /xlsx-basic/mcp, ...) inside one Starlette app on one
# port, so python-docx/openpyxl/python-pptx load once instead of eleven
# times — was previously 11 containers (~650 MiB idle combined), now 1
# (~90 MiB idle). Each sub-server's own /health, /version, /mcp routes
# (defined via @mcp.custom_route in its own server.py) come along for free
# under its mount prefix. Per-sub-server stdio/individual-HTTP servers
# (servers/*/*/server.py) are untouched — still usable directly for local
# LM Studio installs.
#
# Build:  docker build -t mcp-microsoft-office:latest .
# Run:    docker run --rm -p 8830:8830 -e OFFICE_TRANSPORT=http mcp-microsoft-office:latest
# ─────────────────────────────────────────────────────────────────────────────

ARG PYTHON_VERSION=3.12-slim

FROM python:${PYTHON_VERSION} AS builder
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
COPY pyproject.toml uv.lock ./
COPY shared ./shared
COPY servers ./servers
RUN uv sync --frozen --all-packages

FROM python:${PYTHON_VERSION} AS runtime
RUN groupadd -r app && useradd -r -g app app
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/shared /app/shared
COPY --from=builder /app/servers /app/servers
COPY pyproject.toml unified_server.py ./

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    OFFICE_HOST=0.0.0.0 \
    OFFICE_PORT=8830

USER app
EXPOSE 8830

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"OFFICE_PORT\"]}/health', timeout=3)" || exit 1

ENTRYPOINT ["python", "unified_server.py"]
