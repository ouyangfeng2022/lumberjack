#!/usr/bin/env bash
# Multi-architecture Docker image builder.
# Builds each platform as a separate tar file.
#
# Usage:
#   ./build.sh                    # auto-detect version from git
#   ./build.sh v0.1.0             # explicit version
#   PLATFORMS=linux/amd64 ./build.sh  # single platform
#
# Requires a buildx builder that supports multi-platform builds.
# Create one with:
#   docker buildx create --name multiarch --driver docker-container --use
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

VERSION="${1:-}"
IMAGE_NAME="${IMAGE_NAME:-lumberjack}"
DOCKERFILE="${DOCKERFILE:-${SCRIPT_DIR}/Dockerfile}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
TAG="${TAG:-}"
TAR_NAME="${TAR_NAME:-}"

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

# ── Build each platform ───────────────────────────────────
IFS=',' read -ra PLATFORM_LIST <<< "$PLATFORMS"

for platform in "${PLATFORM_LIST[@]}"; do
    arch="${platform##*/}"

    if [ -z "$TAR_NAME" ]; then
        this_tar="${IMAGE_NAME}-${TAG}-${arch}.tar"
    else
        this_tar="${TAR_NAME%.tar}-${arch}.tar"
    fi

    echo "──────────────────────────────────────────"
    echo "  Dockerfile : ${DOCKERFILE}"
    echo "  Platform   : ${platform}"
    echo "  Image      : ${IMAGE_NAME}:${TAG}"
    echo "  Tar        : ${this_tar}"
    echo "  Version    : ${BUILD_VERSION}"
    echo "──────────────────────────────────────────"

    docker buildx build \
        -f "${DOCKERFILE}" \
        --platform "${platform}" \
        --network=host \
        --build-arg VERSION="${BUILD_VERSION}" \
        -t "${IMAGE_NAME}:${TAG}" \
        --output type=docker,dest="${this_tar}" \
        "${PROJECT_ROOT}"

    echo "✅ ${platform} → ${this_tar}"
    echo ""
done

echo "✅ All platforms built successfully"
