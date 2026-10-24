#!/usr/bin/env bash
# Build the deco-local container for linux/amd64 and linux/arm64 and push it to GitHub
# Container Registry as ghcr.io/averagenative/deco-local:<version>, :<major.minor>, and :latest.
#
# There is no CI on purpose: run this from a clean, pushed checkout of deco-local after a
# release. Needs podman and `gh` logged in with the write:packages scope
# (`gh auth refresh -s write:packages` adds it).
#
# arm64 is built one of two ways:
#   ARM64_HOST=<ssh host> packaging/publish-image.sh
#       natively on a 64-bit ARM machine with Docker (a Raspberry Pi works). The host clones
#       this exact commit from GitHub, builds, and streams the image back over ssh; the
#       registry token never leaves this machine.
#   packaging/publish-image.sh
#       under qemu on this machine (needs qemu-user-static and no conflicting binfmt handler;
#       Waydroid's libhoudini registers one that breaks this).
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="${IMAGE:-ghcr.io/averagenative/deco-local}"
REPO_URL="${REPO_URL:-https://github.com/averagenative/deco-local.git}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' deco_desktop/__init__.py)"
MANIFEST="deco-local-publish"

if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    echo "Working tree has uncommitted changes; publish only from a clean checkout." >&2
    exit 1
fi
REV="$(git rev-parse HEAD)"

gh auth token | podman login ghcr.io -u "$(gh api user -q .login)" --password-stdin
podman manifest rm "$MANIFEST" >/dev/null 2>&1 || true
podman manifest create "$MANIFEST"

# --format docker keeps the HEALTHCHECK (the OCI format drops it).
if [ -n "${ARM64_HOST:-}" ]; then
    git fetch -q origin && git merge-base --is-ancestor "$REV" origin/HEAD || {
        echo "Push $REV first: $ARM64_HOST builds it from $REPO_URL." >&2; exit 1; }
    podman build --format docker --platform linux/amd64 --build-arg VERSION="$VERSION" -t localhost/deco-local:amd64 .
    echo "== building linux/arm64 on $ARM64_HOST"
    ssh "$ARM64_HOST" "set -e; d=\$(mktemp -d); git clone -q $REPO_URL \$d; cd \$d; git checkout -q $REV
        docker build -q --build-arg VERSION=$VERSION -t localhost/deco-local:arm64 . >&2
        docker save localhost/deco-local:arm64; cd /; rm -rf \$d; docker rmi localhost/deco-local:arm64 >/dev/null 2>&1" \
        | podman load
    podman manifest add "$MANIFEST" containers-storage:localhost/deco-local:amd64
    podman manifest add "$MANIFEST" containers-storage:localhost/deco-local:arm64
else
    podman build --format docker --platform linux/amd64,linux/arm64 --build-arg VERSION="$VERSION" --manifest "$MANIFEST" .
fi

for tag in "$VERSION" "${VERSION%.*}" latest; do
    podman manifest push --all --format v2s2 "$MANIFEST" "docker://$IMAGE:$tag"
done
echo "Pushed $IMAGE:{$VERSION,${VERSION%.*},latest} for linux/amd64 and linux/arm64"
