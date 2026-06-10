# syntax=docker/dockerfile:1

# Pass the project version for hatch-vcs, which otherwise needs a .git
# directory to detect the version.  On the host run:
#   docker compose build  (reads from git automatically via .env)
#   # or manually:
#   docker build --build-arg VERSION=$(git describe --tags --always) .
ARG VERSION=0.0.0

# ──────────────────────────────────────────────
# Stage 1: Build frontend assets
# Uses the native build platform to avoid
# cross-architecture emulation issues.
# ──────────────────────────────────────────────
FROM --platform=$BUILDPLATFORM oven/bun:1 AS frontend-builder

WORKDIR /app

# Copy frontend source and lockfile
COPY lumberjack_webui/package.json lumberjack_webui/package-lock.json ./lumberjack_webui/

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
# Stage 2: Python builder — install dependencies
# and the project in EDITABLE mode so that
# volume-mounted source is picked up at runtime.
# ──────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

# Re-declare the global ARG so it's visible in this build stage
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

# Install all optional dependencies (web + tokenizers) WITHOUT the project
# so the dependency layer is cached independently of source changes.
RUN --mount=type=cache,target=/root/.local/share/uv \
    uv sync --frozen --no-dev --extra all --no-install-project

# Copy project source and README (hatchling requires readme file for metadata)
COPY src/ ./src/
COPY README.md .

# Install the project itself in EDITABLE mode.
# This creates a .pth link in the venv pointing to /app/src/lumberjack/,
# so any volume-mounted source at runtime is picked up immediately.
RUN --mount=type=cache,target=/root/.local/share/uv \
    uv sync --frozen --no-dev --extra all

# ──────────────────────────────────────────────
# Stage 3: Minimal runtime image
# ──────────────────────────────────────────────
FROM python:3.13-slim AS runtime

WORKDIR /app

# Install uv for potential runtime package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_SYSTEM_PYTHON=1

# Copy the pre-built virtual environment (contains editable .pth link)
COPY --from=builder /app/.venv /app/.venv
# Copy project metadata (needed by editable install resolution)
COPY --from=builder /app/src ./src
COPY pyproject.toml .
COPY uv.lock .

# Copy pre-built frontend assets into the web static directory
COPY --from=frontend-builder /app/frontend-dist ./src/lumberjack/web/static

# Ensure venv binaries are on PATH
ENV PATH=/app/.venv/bin:$PATH

# Pre-populate tiktoken cache so the offline server never needs network access.
RUN mkdir -p /app/.cache/tiktoken \
    && TIKTOKEN_CACHE_DIR=/app/.cache/tiktoken python -c "\
import tiktoken; \
[tiktoken.get_encoding(m) for m in ('cl100k_base','o200k_base','p50k_base','r50k_base')]" \
    || echo "⚠ tiktoken cache warm-up failed (non-fatal for offline use)"

ENV TIKTOKEN_CACHE_DIR=/app/.cache/tiktoken

# Expose the default lumberjack-serve port
EXPOSE 9612

# Entrypoint is the binary only; default args live in CMD so docker-compose
# can override them cleanly (CMD is replaced, ENTRYPOINT is kept).
ENTRYPOINT ["lumberjack-serve"]
CMD ["--host", "0.0.0.0", "--port", "9612"]
