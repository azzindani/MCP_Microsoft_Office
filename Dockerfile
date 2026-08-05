# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────────────────────
# mcp-microsoft-office — production container for all 11 Office MCP servers
# (docx/xlsx/pptx x basic/tables/layout/new/formulas/charts/design). True uv
# workspace — needs `uv sync --all-packages` (plain `uv sync` only installs
# the root project's own deps, which are empty; each member's runtime deps
# only land in the shared venv via --all-packages).
#
# One image, N containers: select which sub-server a given container runs via
# SERVER_MODULE (path to its server.py). See docker-compose.yml for the
# one-service-per-sub-server layout (each with its own port).
#
# Build:  docker build -t mcp-microsoft-office:latest .
# Run docx_basic:
#   docker run --rm -p 8830:8830 -e SERVER_MODULE=servers/docx_basic/docx_basic/server.py \
#     -e OFFICE_DOCX_BASIC_TRANSPORT=http -e OFFICE_DOCX_BASIC_HOST=0.0.0.0 \
#     mcp-microsoft-office:latest
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
COPY pyproject.toml ./

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1

USER app

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "\
import os, urllib.request; \
mod = os.environ.get('SERVER_MODULE', 'servers/docx_basic/docx_basic/server.py'); \
name = mod.split('/')[1]; \
prefix = 'OFFICE_' + name.upper(); \
port = os.environ[f'{prefix}_PORT']; \
urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3)" || exit 1

ENTRYPOINT ["sh", "-c", "exec python \"$SERVER_MODULE\""]
