#!/bin/sh
# Install Deco Desktop for the current user: copy the AppImage to ~/Applications and
# register a desktop entry and icon so it shows up in the app menu (GNOME, KDE, ...).
#
#   packaging/install.sh [path/to/DecoDesktop-*-x86_64.AppImage]
#       default: the newest AppImage in ./dist, then next to this script, then the cwd
#   packaging/install.sh --uninstall
#
# The AppImage runs this same script for `--install` / `--uninstall`, so either works.
# Your saved login (~/.tplink_cloud) is left alone by --uninstall.
set -eu

APP_ID=io.github.averagenative.DecoDesktop
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
TARGET="$HOME/Applications/DecoDesktop-x86_64.AppImage"
DESKTOP="$DATA/applications/$APP_ID.desktop"
ICON_SVG="$DATA/icons/hicolor/scalable/apps/$APP_ID.svg"
ICON_PNG="$DATA/icons/hicolor/256x256/apps/$APP_ID.png"

refresh() {
    update-desktop-database "$DATA/applications" >/dev/null 2>&1 || true
    gtk-update-icon-cache -q -t "$DATA/icons/hicolor" >/dev/null 2>&1 || true
}

if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$DESKTOP" "$ICON_SVG" "$ICON_PNG" "$TARGET"
    refresh
    echo "Removed Deco Desktop (your login in ~/.tplink_cloud was kept)."
    exit 0
fi

# Outside the AppImage: find one and let it install itself (it carries the icons).
if [ -z "${APPDIR:-}" ]; then
    appimage="${1:-}"
    if [ -z "$appimage" ] || [ "$appimage" = "--install" ]; then
        here="$(cd "$(dirname "$0")" && pwd)"
        appimage="$(ls -t "$here/../dist"/DecoDesktop-*-x86_64.AppImage "$here"/DecoDesktop-*-x86_64.AppImage \
                         ./DecoDesktop-*-x86_64.AppImage 2>/dev/null | head -n 1 || true)"
    fi
    if [ -z "$appimage" ] || [ ! -f "$appimage" ]; then
        echo "No AppImage found. Build one (packaging/build-appimage.sh) or pass its path." >&2
        exit 1
    fi
    chmod +x "$appimage"
    exec "$appimage" --install
fi

# Inside the AppImage ($APPDIR and $APPIMAGE are set by the runtime).
: "${APPIMAGE:?run --install from the AppImage}"
mkdir -p "$(dirname "$TARGET")" "$(dirname "$DESKTOP")" "$(dirname "$ICON_SVG")" "$(dirname "$ICON_PNG")"
if [ "$(readlink -f "$APPIMAGE")" != "$(readlink -f "$TARGET" 2>/dev/null || echo none)" ]; then
    cp -f "$APPIMAGE" "$TARGET.new" && mv -f "$TARGET.new" "$TARGET"
fi
chmod 755 "$TARGET"
cp -f "$APPDIR/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg" "$ICON_SVG"
cp -f "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_ID.png" "$ICON_PNG"
cat > "$DESKTOP" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Deco Desktop
GenericName=Mesh Wi-Fi Manager
Comment=Manage a TP-Link Deco mesh over the LAN: clients, port forwarding, IP reservations
Exec="$TARGET"
TryExec=$TARGET
Icon=$APP_ID
Terminal=false
Categories=Network;
Keywords=deco;tp-link;router;mesh;wifi;port forwarding;dhcp;reservation;
StartupWMClass=$APP_ID
StartupNotify=true
DESKTOP
refresh
echo "Installed Deco Desktop: $TARGET"
echo "Desktop entry: $DESKTOP (search for \"Deco\" in your app menu)"
