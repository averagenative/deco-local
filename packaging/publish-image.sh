#!/usr/bin/env bash
# Build the deco-local container for linux/amd64 and linux/arm64 and push it to GitHub
# Container Registry as ghcr.io/averagenative/deco-local:<version>, :<major.minor>, and :latest.
#
# There is no CI on purpose: run this from a clean checkout of deco-local after a release.
# Needs podman, qemu-user-static (to build arm64 on x86), and `gh` logged in with the
# write:packages scope (`gh auth refresh -s write:packages` adds it).
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="${IMAGE:-ghcr.io/averagenative/deco-local}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' deco_desktop/__init__.py)"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
MANIFEST="deco-local-publish"

if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    echo "Working tree has uncommitted changes; publish only from a clean checkout." >&2
    exit 1
fi

gh auth token | podman login ghcr.io -u "$(gh api user -q .login)" --password-stdin
podman manifest rm "$MANIFEST" >/dev/null 2>&1 || true
podman manifest create "$MANIFEST"
# --format docker keeps the HEALTHCHECK (the OCI format drops it).
podman build --format docker --platform "$PLATFORMS" --build-arg VERSION="$VERSION" --manifest "$MANIFEST" .
for tag in "$VERSION" "${VERSION%.*}" latest; do
    podman manifest push --all --format v2s2 "$MANIFEST" "docker://$IMAGE:$tag"
done
echo "Pushed $IMAGE:{$VERSION,${VERSION%.*},latest} for $PLATFORMS"
