"""Wi-Fi screen: the main, guest, and IoT networks. Saving restarts the Wi-Fi radios."""

from gi.repository import GLib, Gtk

import deco_features

from . import Screen
from ..widgets import group_frame, kv_grid

NETWORKS = (
    ("host", "Main network", "The network your own devices use. The Deco uses one name on every band.", False),
    ("guest", "Guest network", "A separate network for visitors. Guests reach the internet but not your devices.", True),
    ("iot", "IoT network", "A separate network for smart-home devices.", True),
)


class WifiScreen(Screen):
    def __init__(self, window):
        super().__init__(window, "Wi-Fi")
        warn = Gtk.Label(xalign=0, wrap=True, label=(
            "Saving a change here restarts the Wi-Fi radios. Every Wi-Fi device disconnects for 10 to 30 "
            "seconds and then reconnects on its own. If you change the main network's name or password, "
            "you have to reconnect each device by hand."))
        warn.add_css_class("warning")
        self.append(warn)

        scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3,
                           column_spacing=12, row_spacing=12, homogeneous=True, valign=Gtk.Align.START)
        scroller.set_child(flow)
        self.append(scroller)

        self._forms = {}
        self._current = {}
        for net, title, desc, optional in NETWORKS:
            frame, box = group_frame(title, desc)
            form = {"title": title, "enable": Gtk.Switch(valign=Gtk.Align.CENTER) if optional else None,
                    "ssid": Gtk.Entry(hexpand=True), "secured": Gtk.Switch(valign=Gtk.Align.CENTER) if optional else None,
                    "password": Gtk.PasswordEntry(show_peek_icon=True, hexpand=True)}
            for key, label in (("enable", "On"), ("ssid", "Name (SSID)"), ("secured", "Password protected"), ("password", "Password")):
                if form[key] is None:
                    continue
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                row.append(Gtk.Label(label=label, xalign=0, hexpand=key in ("enable", "secured"), width_chars=12))
                row.append(form[key])
                box.append(row)
            save = Gtk.Button(label="Save…", halign=Gtk.Align.END)
            save.add_css_class("suggested-action")
            save.connect("clicked", lambda _b, n=net: self._save(n))
            box.append(save)
            frame.set_sensitive(False)
            form["frame"] = frame
            self._forms[net] = form
            flow.append(frame)

        self._radio_frame, self._radio_box = group_frame("Radios")
        flow.append(self._radio_frame)
        self._radio_grid = None

    def refresh(self):
        self.run_call(deco_features.wifi, self._populate, label="wifi")

    def _populate(self, w):
        bands = [(k, b) for k, b in w.items() if isinstance(b, dict) and b.get("radio")]
        for net, form in self._forms.items():
            cur = next((b[net] for _k, b in bands if isinstance(b.get(net), dict)), None)
            self._current[net] = cur
            form["frame"].set_sensitive(cur is not None)
            if cur is None:
                continue
            form["ssid"].set_text(cur.get("ssid") or "")
            form["password"].set_text(cur.get("password") or "")
            if form["enable"] is not None:
                form["enable"].set_active(bool(cur.get("enable")))
            if form["secured"] is not None:
                form["secured"].set_active(cur.get("encryption_mode") != "none")
        names = {"band2_4": "2.4 GHz", "band5_1": "5 GHz", "band5_2": "5 GHz (second)", "band6": "6 GHz"}
        pairs = []
        for k, b in bands:
            ch = b["radio"].get("channel")
            pairs += [(f"{names.get(k, k)} channel", "auto" if str(ch) == "0" else ch),
                      (f"{names.get(k, k)} width", b["radio"].get("htmode")),
                      (f"{names.get(k, k)} backhaul", (b.get("backhaul") or {}).get("channel"))]
        if self._radio_grid is not None:
            self._radio_box.remove(self._radio_grid)
        self._radio_grid = kv_grid(pairs)
        self._radio_box.append(self._radio_grid)

    def _save(self, net):
        form, cur = self._forms[net], self._current.get(net) or {}
        change = {}
        ssid, password = form["ssid"].get_text().strip(), form["password"].get_text()
        if ssid != (cur.get("ssid") or ""):
            change["ssid"] = ssid
        if password != (cur.get("password") or ""):
            change["password"] = password
        if form["enable"] is not None and form["enable"].get_active() != bool(cur.get("enable")):
            change["enable"] = form["enable"].get_active()
        if form["secured"] is not None and form["secured"].get_active() != (cur.get("encryption_mode") != "none"):
            change["secured"] = form["secured"].get_active()
            change["password"] = password
        if not change:
            self.window.toast("Nothing changed.")
            return
        if change.get("ssid") == "":
            self.window.toast("The network name cannot be empty.")
            return
        needs_pw = net == "host" or (form["secured"] is not None and form["secured"].get_active())
        if needs_pw and ("password" in change or change.get("secured")) and len(password) < 8:
            self.window.toast("Wi-Fi passwords need at least 8 characters.")
            return
        renames = net == "host" and ("ssid" in change or "password" in change)
        self.confirm(
            f"Apply the {form['title'].lower()} changes? "
            + ("Every Wi-Fi device disconnects and only reconnects after you enter the new name or password on it."
               if renames else "Every Wi-Fi device disconnects for 10 to 30 seconds and then reconnects on its own."),
            lambda: self.run_call(
                lambda d: deco_features.set_wifi_network(d, net, **change),
                lambda _r: (self.window.toast(f"{form['title']} updated. The Wi-Fi radios are restarting."),
                            GLib.timeout_add_seconds(25, lambda: (self.refresh(), False)[1])),
                label="wifi_set"),
            destructive_label="Apply")

    def on_disconnected(self):
        for form in self._forms.values():
            form["frame"].set_sensitive(False)
