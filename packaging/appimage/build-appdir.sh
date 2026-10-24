#!/usr/bin/env bash
# Runs inside the deco-desktop-appimage-builder container. Assembles a self-contained AppDir
# with Python, PyGObject, GTK 4, and paramiko (plus its crypto libraries), then writes
# /out/DecoDesktop-<version>-x86_64.AppImage.
set -euo pipefail
cd /src

APP_ID=io.github.averagenative.DecoDesktop
VERSION="$(python3 -c 'import deco_desktop; print(deco_desktop.__version__)')"
PYVER="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
ARCHLIB=/usr/lib/x86_64-linux-gnu
APPDIR=/tmp/AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR"/usr/{bin,lib,share} "$APPDIR/usr/lib/deco-desktop" "$APPDIR/usr/lib/python3/dist-packages" \
    "$APPDIR/usr/share/deco-desktop" "$APPDIR/usr/share/icons/Adwaita"

echo "== Python $PYVER"
cp "/usr/bin/python$PYVER" "$APPDIR/usr/bin/python3"
cp -a "/usr/lib/python$PYVER" "$APPDIR/usr/lib/"
rm -rf "$APPDIR/usr/lib/python$PYVER"/{test,idlelib,tkinter,turtledemo,ensurepip,pydoc_data,lib2to3,config-*}
rm -f "$APPDIR/usr/lib/python$PYVER"/lib-dynload/{_test*,xxlimited*,xxsubtype*,_xxtestfuzz*,_tkinter*}

echo "== Python packages: the dist-packages the app actually imports"
# Import everything the app and paramiko's SSH handshake load, then copy each top-level
# dist-packages entry those modules came from (PyGObject, pycairo, paramiko, cryptography,
# bcrypt, PyNaCl, cffi's backend, ...).
python3 - > /tmp/dist-packages.txt <<'PY'
import sys
sys.path.insert(0, "/src")
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GLib, GObject, Gdk, Pango  # noqa: F401
import cairo  # noqa: F401
import deco_api  # noqa: F401  (imports paramiko)
import paramiko.client, paramiko.transport, paramiko.ed25519key, paramiko.ecdsakey  # noqa: F401,E401
import paramiko.rsakey, paramiko.kex_curve25519, paramiko.kex_ecdh_nist, paramiko.kex_group14  # noqa: F401,E401
import paramiko.kex_group16, paramiko.kex_gex  # noqa: F401,E401
from cryptography.hazmat.backends import default_backend
default_backend()
roots = set()
for m in list(sys.modules.values()):
    f = getattr(m, "__file__", None) or ""
    if "/dist-packages/" in f:
        roots.add(f.split("/dist-packages/", 1)[1].split("/", 1)[0])
print("\n".join(sorted(roots)))
PY
while read -r entry; do
    cp -a "/usr/lib/python3/dist-packages/$entry" "$APPDIR/usr/lib/python3/dist-packages/"
done < /tmp/dist-packages.txt
tr '\n' ' ' < /tmp/dist-packages.txt; echo

echo "== The app"
cp -a deco_desktop deco_api.py deco_demo.py deco_log.py deco-opcodes.json "$APPDIR/usr/lib/deco-desktop/"
cp packaging/install.sh "$APPDIR/usr/share/deco-desktop/install.sh"
find "$APPDIR/usr/lib" -name __pycache__ -prune -exec rm -rf {} +

echo "== OpenSSL provider modules"
# The bundled libcrypto looks for its providers at Debian's path, which other distributions
# do not have; AppRun points OPENSSL_MODULES here instead.
cp -a "$ARCHLIB/ossl-modules" "$APPDIR/usr/lib/ossl-modules"

echo "== GObject type data"
mkdir -p "$APPDIR/usr/lib/girepository-1.0"
cp "$ARCHLIB"/girepository-1.0/*.typelib "$APPDIR/usr/lib/girepository-1.0/"

echo "== Icons, desktop entry"
cp -a /usr/share/icons/Adwaita/{index.theme,symbolic,scalable} "$APPDIR/usr/share/icons/Adwaita/"
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps" "$APPDIR/usr/share/icons/hicolor/256x256/apps" \
    "$APPDIR/usr/share/applications" "$APPDIR/usr/share/mime"
cp /usr/share/icons/hicolor/index.theme "$APPDIR/usr/share/icons/hicolor/"
# gdk-pixbuf picks an image loader by MIME type through GIO, so SVG icons need the compiled
# shared-mime-info database. Hosts nearly always have one; this covers those that don't.
cp /usr/share/mime/{mime.cache,globs,globs2,magic,aliases,subclasses,types,icons,generic-icons,XMLnamespaces,treemagic,version} \
    "$APPDIR/usr/share/mime/"
cp "data/$APP_ID.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/"
rsvg-convert -w 256 -h 256 "data/$APP_ID.svg" -o "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_ID.png"
cp "data/$APP_ID.svg" "$APPDIR/$APP_ID.svg"
cat > "$APPDIR/$APP_ID.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Deco Desktop
GenericName=Mesh Wi-Fi Manager
Comment=Manage a TP-Link Deco mesh over the LAN: clients, port forwarding, IP reservations
Exec=deco-desktop
Icon=$APP_ID
Terminal=false
Categories=Network;
Keywords=deco;tp-link;router;mesh;wifi;port forwarding;dhcp;reservation;
StartupWMClass=$APP_ID
X-AppImage-Version=$VERSION
DESKTOP
cp "$APPDIR/$APP_ID.desktop" "$APPDIR/usr/share/applications/"
desktop-file-validate "$APPDIR/$APP_ID.desktop"

echo "== linuxdeploy: shared libraries, GTK modules, pixbuf loaders, schemas"
export DEPLOY_GTK_VERSION=4
cp /opt/tools/linuxdeploy-plugin-gtk.sh /tmp/
ARGS=()
for lib in libgtk-4.so.1 libgraphene-1.0.so.0 libpangocairo-1.0.so.0 libgdk_pixbuf-2.0.so.0 librsvg-2.so.2 \
           libgirepository-1.0.so.1 libgirepository-2.0.so.0; do
    [ -e "$ARCHLIB/$lib" ] && ARGS+=(--library "$ARCHLIB/$lib")
done
for dir in "usr/lib/python$PYVER/lib-dynload" usr/lib/python3/dist-packages; do
    ARGS+=(--deploy-deps-only "$APPDIR/$dir")
done
PATH=/tmp:$PATH linuxdeploy --appdir "$APPDIR" --plugin gtk --executable "$APPDIR/usr/bin/python3" "${ARGS[@]}" \
    --custom-apprun packaging/appimage/AppRun > /out/linuxdeploy.log 2>&1 || { tail -40 /out/linuxdeploy.log; exit 1; }

cp "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_ID.png" "$APPDIR/.DirIcon"
chmod 755 "$APPDIR/AppRun"
du -sh "$APPDIR"

echo "== appimagetool"
OUT="/out/DecoDesktop-$VERSION-x86_64.AppImage"
rm -f "$OUT"
ARCH=x86_64 appimagetool --no-appstream "$APPDIR" "$OUT" 2>&1 | grep -E "^Success|rror" || true
ls -la "$OUT"
