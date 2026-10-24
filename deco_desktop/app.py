"""GTK4 application shell: main window, sidebar navigation, connection status, toasts."""

import json
import os
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Gio  # noqa: E402

from . import backend as be  # noqa: E402
from .screens.clients import ClientsScreen  # noqa: E402
from .screens.internet import InternetScreen  # noqa: E402
from .screens.mesh import MeshScreen  # noqa: E402
from .screens.overview import OverviewScreen  # noqa: E402
from .screens.portforward import PortForwardScreen  # noqa: E402
from .screens.reservations import ReservationsScreen  # noqa: E402
from .screens.settings import NetworkScreen, SecurityScreen, SystemScreen  # noqa: E402
from .screens.wifi import WifiScreen  # noqa: E402
from .widgets import FormDialog  # noqa: E402

APP_ID = "io.github.averagenative.DecoDesktop"
SETTINGS = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "deco-desktop" / "settings.json"
THEMES = ("Dark", "Light")


def _load_settings():
    try:
        return json.loads(SETTINGS.read_text())
    except (OSError, ValueError):
        return {}


def _save_settings(settings):
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(settings))
    except OSError:
        pass


def _apply_theme(name):
    Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", name != "Light")

_STATE_TEXT = {
    be.DISCONNECTED: "Disconnected",
    be.CONNECTING: "Connecting…",
    be.CONNECTED: "Connected",
    be.LOCKED_OUT: "Locked out — wait and retry",
}


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Deco Desktop")
        self.set_default_size(1100, 720)
        self.backend = be.Backend(on_state_change=self._on_state_change)

        # --- header ---
        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        self._connect_btn = Gtk.Button(label="Connect")
        self._connect_btn.connect("clicked", self._on_connect_clicked)
        header.pack_start(self._connect_btn)
        signin = Gtk.Button(label="Account…", tooltip_text="TP-Link account used to sign in to the Deco")
        signin.connect("clicked", lambda _b: self.sign_in())
        header.pack_start(signin)

        theme = _load_settings().get("theme", "Dark")
        theme = theme if theme in THEMES else "Dark"
        _apply_theme(theme)
        self._theme = Gtk.DropDown.new_from_strings(list(THEMES))
        self._theme.set_tooltip_text("Theme")
        self._theme.set_selected(THEMES.index(theme))
        self._theme.connect("notify::selected", self._on_theme_changed)
        header.pack_end(self._theme)

        self._spinner = Gtk.Spinner()
        header.pack_end(self._spinner)
        self._status_lbl = Gtk.Label(label=_STATE_TEXT[be.DISCONNECTED])
        self._status_lbl.add_css_class("dim-label")
        header.pack_end(self._status_lbl)

        # --- screens ---
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.screens = []
        for title, name, screen in (
            ("Overview", "overview", OverviewScreen(self)),
            ("Clients", "clients", ClientsScreen(self)),
            ("Port Forwarding", "portforward", PortForwardScreen(self)),
            ("Reservations", "reservations", ReservationsScreen(self)),
            ("Wi-Fi", "wifi", WifiScreen(self)),
            ("Mesh", "mesh", MeshScreen(self)),
            ("Internet & LAN", "internet", InternetScreen(self)),
            ("Network", "network", NetworkScreen(self)),
            ("Security", "security", SecurityScreen(self)),
            ("System", "system", SystemScreen(self)),
        ):
            self.stack.add_titled(screen, name, title)
            self.screens.append(screen)
        self.stack.connect("notify::visible-child", self._on_screen_switched)

        sidebar = Gtk.StackSidebar()
        sidebar.set_stack(self.stack)

        split = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        split.append(sidebar)
        split.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        split.append(self.stack)

        # --- toast overlay ---
        self._overlay = Gtk.Overlay()
        self._overlay.set_child(split)
        self._toast = Gtk.Revealer(
            halign=Gtk.Align.CENTER, valign=Gtk.Align.END,
            transition_type=Gtk.RevealerTransitionType.SLIDE_UP,
        )
        toast_frame = Gtk.Frame()
        toast_frame.add_css_class("app-notification")
        self._toast_lbl = Gtk.Label()
        self._toast_lbl.set_margin_top(8)
        self._toast_lbl.set_margin_bottom(8)
        self._toast_lbl.set_margin_start(14)
        self._toast_lbl.set_margin_end(14)
        toast_frame.set_child(self._toast_lbl)
        self._toast.set_child(toast_frame)
        self._toast.set_margin_bottom(18)
        self._overlay.add_overlay(self._toast)
        self.set_child(self._overlay)

        self.connect("close-request", self._on_close)
        self._update_controls(be.DISCONNECTED)

    # ---- API used by screens ----
    @property
    def connected(self):
        return self.backend.state == be.CONNECTED

    def submit(self, fn, on_success=None, on_error=None, label=None):
        """Run a backend call; default error handler shows a toast."""
        self.backend.submit(fn, on_success=on_success,
                             on_error=on_error or self._default_error, label=label)

    def toast(self, text, timeout=4):
        self._toast_lbl.set_text(text)
        self._toast.set_reveal_child(True)
        if getattr(self, "_toast_source", None):
            GLib.source_remove(self._toast_source)
        self._toast_source = GLib.timeout_add_seconds(
            timeout, lambda: (self._toast.set_reveal_child(False), False)[1]
        )

    def _default_error(self, exc):
        self.toast(f"Error: {exc}")

    def reserve_for_client(self, mac, ip):
        """Jump to the Reservations screen and open Add prefilled from a client."""
        for screen in self.screens:
            if isinstance(screen, ReservationsScreen):
                self.stack.set_visible_child(screen)
                screen._add(prefill={"mac": mac, "ip": ip})
                return

    def _on_theme_changed(self, dropdown, _pspec):
        name = THEMES[dropdown.get_selected()]
        _apply_theme(name)
        _save_settings({**_load_settings(), "theme": name})

    def sign_in(self):
        """Ask for the TP-Link account (the Deco app login), save it, and connect."""
        FormDialog(
            self, "Sign in to your Deco",
            [("email", "Email", self.backend.saved_email()),
             ("password", "Password", "", True)],
            on_submit=self._do_sign_in, submit_label="Sign in",
            note="Use the TP-Link account that owns the Deco (the one the Deco phone app "
                 "uses). The Deco checks it locally; nothing goes to the cloud. It is saved "
                 "to ~/.tplink_cloud, readable only by you.",
        ).present()

    def _do_sign_in(self, values):
        if not values["email"] or not values["password"]:
            self.toast("Enter both the email and the password.")
            return
        try:
            self.backend.save_credentials(values["email"], values["password"])
        except OSError as e:
            self.toast(f"Could not save credentials: {e}")
            return
        self.backend.reconnect()

    # ---- state handling ----
    def _on_connect_clicked(self, _btn):
        if self.backend.state in (be.CONNECTED, be.CONNECTING):
            self.backend.disconnect()
        elif not self.backend.has_credentials():
            self.sign_in()
        else:
            self.backend.connect()

    def _on_state_change(self, state, info, error):
        self._update_controls(state, info)
        if error is not None and state in (be.DISCONNECTED, be.LOCKED_OUT):
            self.toast(str(error), timeout=6)
        if state == be.CONNECTED:
            self._refresh_visible()
        elif state in (be.DISCONNECTED, be.LOCKED_OUT):
            for s in self.screens:
                s.on_disconnected()
        return False

    def _update_controls(self, state, info=None):
        info = info or self.backend.info
        if state == be.CONNECTED and info:
            self._status_lbl.set_text(f"{info['model']} @ {info['ip']} · {info['nodes']} nodes")
        else:
            self._status_lbl.set_text(_STATE_TEXT.get(state, state))
        self._connect_btn.set_label(
            "Disconnect" if state in (be.CONNECTED, be.CONNECTING) else "Connect"
        )
        self._connect_btn.set_sensitive(state != be.CONNECTING)
        if state == be.CONNECTING:
            self._spinner.start()
        else:
            self._spinner.stop()

    def _on_screen_switched(self, *_):
        if self.connected:
            self._refresh_visible()

    def _refresh_visible(self):
        child = self.stack.get_visible_child()
        if child is not None:
            child.refresh()

    def _on_close(self, *_):
        self.backend.shutdown()
        return False


class DecoDesktopApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self._win = None

    def do_activate(self):
        if self._win is None:
            self._win = MainWindow(self)
        self._win.present()
        # Auto-connect on launch so the fast client list is there immediately;
        # on first run, ask for the account instead.
        if self._win.backend.has_credentials():
            self._win.backend.connect()
        else:
            self._win.sign_in()


def main(argv=None):
    app = DecoDesktopApp()
    return app.run(argv)
