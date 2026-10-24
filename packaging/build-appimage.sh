#!/usr/bin/env bash
# Build dist/DecoDesktop-<version>-x86_64.AppImage: Python, PyGObject, GTK 4, and paramiko
# bundled. The build runs in a Debian 13 container (podman, or docker), so the result runs on
# any distribution with glibc 2.41 or later. The builder image is rebuilt only when
# packaging/appimage/Containerfile changes.
set -euo pipefail
cd "$(dirname "$0")/.."

ENGINE="$(command -v podman || command -v docker || true)"
[ -n "$ENGINE" ] || { echo "Need podman or docker." >&2; exit 1; }
IMAGE=deco-desktop-appimage-builder
STAMP="$(sha256sum packaging/appimage/Containerfile | cut -c1-12)"
if ! "$ENGINE" image inspect "$IMAGE:$STAMP" >/dev/null 2>&1; then
    "$ENGINE" build -t "$IMAGE:$STAMP" packaging/appimage
fi
mkdir -p dist
# Mount only what the build reads (a relabel of the whole checkout trips over files it
# does not own, and keeps the context small).
SRC="$(mktemp -d)"
trap 'rm -rf "$SRC"' EXIT
cp -a deco_desktop deco_api.py deco_demo.py deco_features.py deco_log.py deco-opcodes.json data packaging "$SRC/"
find "$SRC" -name __pycache__ -prune -exec rm -rf {} +
"$ENGINE" run --rm -v "$SRC:/src:ro,z" -v "$PWD/dist:/out:z" "$IMAGE:$STAMP" bash /src/packaging/appimage/build-appdir.sh
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' deco_desktop/__init__.py)"
(cd dist && sha256sum "DecoDesktop-$VERSION-x86_64.AppImage" | tee "DecoDesktop-$VERSION-x86_64.AppImage.sha256")
