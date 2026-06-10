#!/usr/bin/env bash
# Build and load a Docker image directly into the local daemon.
#
# Usage:
#   ./load.sh                    # auto-detect version from git
#   ./load.sh v0.1.0             # explicit version
#   PLATFORM=linux/arm64 ./load.sh  # specific platform
#
# Note: --load only supports a single platform at a time.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

VERSION="${1:-}"
IMAGE_NAME="${IMAGE_NAME:-lumberjack}"
DOCKERFILE="${DOCKERFILE:-${SCRIPT_DIR}/Dockerfile}"
PLATFORM="${PLATFORM:-}"
TAG="${TAG:-}"

# ── Version detection ──────────────────────────────────────
if [ -z "$VERSION" ]; then
    if git -C "${PROJECT_ROOT}" rev-parse --short HEAD >/dev/null 2>&1; then
        VERSION="$(git -C "${PROJECT_ROOT}" describe --tags --always 2>/dev/null || git -C "${PROJECT_ROOT}" rev-parse --short HEAD)"
    else
        VERSION="0.0.0"
    fi
fi

BUILD_VERSION="${VERSION#v}"

# ── Image naming ───────────────────────────────────────────
if [ -z "$TAG" ]; then
    TAG="${VERSION#v}"
fi

# ── Build platform flags ───────────────────────────────────
PLATFORM_FLAGS=()
if [ -n "$PLATFORM" ]; then
    PLATFORM_FLAGS=(--platform "${PLATFORM}")
fi

echo "──────────────────────────────────────────"
echo "  Dockerfile : ${DOCKERFILE}"
echo "  Image      : ${IMAGE_NAME}:${TAG}"
echo "  Version    : ${BUILD_VERSION}"
if [ -n "$PLATFORM" ]; then
    echo "  Platform   : ${PLATFORM}"
fi
echo "──────────────────────────────────────────"

docker buildx build \
    -f "${DOCKERFILE}" \
    "${PLATFORM_FLAGS[@]}" \
    --network=host \
    --build-arg VERSION="${BUILD_VERSION}" \
    -t "${IMAGE_NAME}:${TAG}" \
    --load \
    "${PROJECT_ROOT}"

echo "✅ Loaded → ${IMAGE_NAME}:${TAG}"
