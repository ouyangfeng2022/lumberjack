# syntax=docker/dockerfile:1

# Pass the project version for hatch-vcs, which otherwise needs a .git
# directory to detect the version.  Pass COMMIT to expose the deployed
# revision through /version.  On the host run:
#   docker compose build  (reads from git automatically via .env)
#   # or manually:
#   docker build --build-arg VERSION=$(git describe --tags --always) \
#                --build-arg COMMIT=$(git rev-parse --short HEAD) .
ARG VERSION=0.0.0
ARG COMMIT=""

# ──────────────────────────────────────────────
# Stage 1: Build frontend assets
# Uses the native build platform to avoid
# cross-architecture emulation issues.
# ──────────────────────────────────────────────
FROM --platform=$BUILDPLATFORM oven/bun:1 AS frontend-builder

WORKDIR /app

# Copy frontend source and lockfile
COPY lumberjack_webui/package.json lumberjack_webui/bun.lock ./lumberjack_webui/

# Install frontend dependencies
RUN --mount=type=cache,target=/root/.bun/install/cache \
    cd lumberjack_webui \
    && bun install --frozen-lockfile

# Copy remaining frontend source
COPY lumberjack_webui/ ./lumberjack_webui/

# Build frontend → outputs to /app/frontend-dist
RUN cd lumberjack_webui \
    && bun run build -- --outDir /app/frontend-dist

# ──────────────────────────────────────────────
# Stage 2: Python builder — resolve dependencies,
# build the wheel (with web assets inside), and
# install it NON-EDITABLE into a clean venv.
# ──────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

# Re-declare build args so they are visible in this build stage
ARG VERSION=0.0.0

ENV DEBIAN_FRONTEND=noninteractive
ENV UV_SYSTEM_PYTHON=1
ENV UV_COMPILE_BYTECODE=1
# Tell hatch-vcs / setuptools-scm the version so it doesn't need .git
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION}

WORKDIR /app

# Copy project metadata first for better layer caching
COPY pyproject.toml .
COPY uv.lock .

# Install all optional dependencies WITHOUT the project
# so the dependency layer is cached independently of source changes.
RUN --mount=type=cache,target=/root/.local/share/uv \
    uv sync --frozen --no-dev --extra all --no-install-project

# Copy project source and README (hatchling requires readme file for metadata)
COPY src/ ./src/
COPY README.md .
COPY schemas/ ./schemas/

COPY --from=frontend-builder /app/frontend-dist /app/frontend-dist

# Build the wheel and install it into the venv non-editable. The runtime
# image therefore contains an immutable installed package, not an editable
# link that would depend on the repository layout. The built frontend is
# copied into the installed package afterwards because hatchling respects
# .gitignore and web/static is not version controlled.
RUN --mount=type=cache,target=/root/.local/share/uv \
    uv build --wheel --out-dir /app/dist \
    && uv pip install --python /app/.venv/bin/python /app/dist/*.whl \
    && STATIC_DIR="$(/app/.venv/bin/python -c 'import lumberjack, pathlib; print(pathlib.Path(lumberjack.__file__).parent / "web" / "static")')" \
    && mkdir -p "${STATIC_DIR}" \
    && cp -r /app/frontend-dist/. "${STATIC_DIR}"/

# ──────────────────────────────────────────────
# Stage 3: Minimal runtime image — venv only,
# no build tools, no source tree.
# ──────────────────────────────────────────────
FROM python:3.13-slim AS runtime

ARG COMMIT=""

WORKDIR /app

# Copy the pre-built virtual environment with the installed package
COPY --from=builder /app/.venv /app/.venv

# Ensure venv binaries are on PATH
ENV PATH=/app/.venv/bin:$PATH

# Expose the deployed revision through GET /version
ENV LUMBERJACK_BUILD_COMMIT=${COMMIT}

# Pre-populate tokenizer caches so the offline server never needs network access.
RUN mkdir -p /app/.cache/tiktoken \
    && TIKTOKEN_CACHE_DIR=/app/.cache/tiktoken python -c "\
import tiktoken; \
[tiktoken.get_encoding(m) for m in ('cl100k_base','o200k_base','p50k_base','r50k_base')]" \
    || echo "⚠ tiktoken cache warm-up failed (non-fatal for offline use)"

RUN mkdir -p /app/.cache/huggingface \
    && HF_HOME=/app/.cache/huggingface python -c "\
from transformers import AutoTokenizer; \
AutoTokenizer.from_pretrained('bert-base-uncased', use_fast=True)" \
    || echo "⚠ transformers tokenizer cache warm-up failed (non-fatal for offline use)"

ENV TIKTOKEN_CACHE_DIR=/app/.cache/tiktoken
ENV HF_HOME=/app/.cache/huggingface

# Expose the default lumberjack-serve port
EXPOSE 9612

# Entrypoint is the binary only; default args live in CMD so docker-compose
# can override them cleanly (CMD is replaced, ENTRYPOINT is kept).
ENTRYPOINT ["lumberjack-serve"]
CMD ["--host", "0.0.0.0", "--port", "9612"]
