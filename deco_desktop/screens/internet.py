"""Internet & LAN screen: the WAN connection, the Deco's LAN address, and the DHCP pool.

UNTESTED on hardware: these send the same requests as the Deco app (worked out from its
code), but nobody has run them against a live Deco yet.
"""

from gi.repository import GLib, Gtk

import deco_features

from . import Screen
from ..widgets import group_frame

TYPES = (("dynamic_ip", "Dynamic IP"), ("static_ip", "Static IP"), ("pppoe", "PPPoE"))


def _row(box, label, widget):
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    row.append(Gtk.Label(label=label, xalign=0, hexpand=True))
    row.append(widget)
    box.append(row)
    return row


def _entry(width=16):
    return Gtk.Entry(width_chars=width)


def _save_button(handler):
    btn = Gtk.Button(label="Save…", halign=Gtk.Align.END)
    btn.add_css_class("suggested-action")
    btn.connect("clicked", lambda _b: handler())
    return btn


class InternetScreen(Screen):
    def __init__(self, window):
        super().__init__(window, "Internet & LAN")
        warn = Gtk.Label(xalign=0, wrap=True, label=(
            "Untested on hardware: these settings send the same requests as the Deco app, worked out from its "
            "code, but nobody has run them against a live Deco yet. A wrong internet setting can leave you "
            "offline until you fix it here; this app keeps working over your LAN."))
        warn.add_css_class("warning")
        self.append(warn)

        scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3,
                           column_spacing=12, row_spacing=12, homogeneous=True, valign=Gtk.Align.START)
        scroller.set_child(flow)
        self.append(scroller)
        self._wan, self._lan = {}, {}

        # ---- internet connection ----
        frame, box = group_frame("Internet connection (untested)", "How the Deco connects to your modem.")
        self._now = Gtk.Label(xalign=0, wrap=True)
        self._now.add_css_class("dim-label")
        box.append(self._now)
        self.type = Gtk.DropDown.new_from_strings([t[1] for t in TYPES])
        self.dns_mode = Gtk.DropDown.new_from_strings(["Automatic", "Manual"])
        self.w = {k: _entry() for k in ("ip", "mask", "gateway", "username", "dns1", "dns2")}
        self.w["password"] = Gtk.PasswordEntry(show_peek_icon=True, width_chars=16)
        self.w["mtu"] = _entry(6)
        _row(box, "Connection type", self.type)
        self.rows = {"dns": _row(box, "DNS", self.dns_mode)}
        for key, label in (("ip", "IP address"), ("mask", "Subnet mask"), ("gateway", "Gateway"),
                           ("username", "Username"), ("password", "Password"), ("dns1", "Primary DNS"),
                           ("dns2", "Secondary DNS"), ("mtu", "MTU")):
            self.rows[key] = _row(box, label, self.w[key])
        self.ping = Gtk.Switch(valign=Gtk.Align.CENTER)
        _row(box, "Answer pings from the internet", self.ping)
        ping_btn = Gtk.Button(label="Apply ping setting…", halign=Gtk.Align.END)
        ping_btn.connect("clicked", lambda _b: self._save_ping())
        box.append(ping_btn)
        box.append(_save_button(self._save_wan))
        self.type.connect("notify::selected", lambda *_: self._sync())
        self.dns_mode.connect("notify::selected", lambda *_: self._sync())
        flow.append(frame)
        self._wan_frame = frame

        # ---- Deco address ----
        frame, box = group_frame("Deco address, LAN (untested)",
                                 "The main Deco's own address, which is the gateway for every device on your network.")
        self.lan_ip, self.lan_mask = _entry(), _entry()
        _row(box, "Deco address", self.lan_ip)
        _row(box, "Subnet mask", self.lan_mask)
        box.append(_save_button(self._save_lan_ip))
        flow.append(frame)
        self._lan_frame = frame

        # ---- DHCP ----
        frame, box = group_frame("DHCP server (untested)", "Hands out addresses to your devices.")
        self._dhcp_note = Gtk.Label(xalign=0, wrap=True)
        self._dhcp_note.add_css_class("dim-label")
        box.append(self._dhcp_note)
        self.dhcp = {k: _entry() for k in ("start_ip", "end_ip", "dns1", "dns2")}
        for key, label in (("start_ip", "Pool start"), ("end_ip", "Pool end"), ("dns1", "Primary DNS"), ("dns2", "Secondary DNS")):
            _row(box, label, self.dhcp[key])
        box.append(_save_button(self._save_dhcp))
        flow.append(frame)
        self._dhcp_frame = frame
        for f in (self._wan_frame, self._lan_frame, self._dhcp_frame):
            f.set_sensitive(False)

    def _type(self):
        return TYPES[self.type.get_selected()][0]

    def _sync(self):
        t, manual = self._type(), self.dns_mode.get_selected() == 1
        self.rows["dns"].set_visible(t != "static_ip")
        for k in ("ip", "mask", "gateway"):
            self.rows[k].set_visible(t == "static_ip")
        for k in ("username", "password"):
            self.rows[k].set_visible(t == "pppoe")
        for k in ("dns1", "dns2"):
            self.rows[k].set_visible(t == "static_ip" or manual)

    def refresh(self):
        self.run_call(lambda d: (deco_features.wan_settings(d), deco_features.lan_settings(d)), self._populate, label="wan_lan")

    def _populate(self, result):
        self._wan, self._lan = result
        w = self._wan
        self._now.set_text(f"Now: {str(w.get('dial_type') or '?').replace('_', ' ')}"
                           f"{', ' + w['ip'] if w.get('ip') else ''}.")
        self.type.set_selected(next((i for i, t in enumerate(TYPES) if t[0] == w.get("dial_type")), 0))
        self.dns_mode.set_selected(0 if w.get("enable_auto_dns") else 1)
        static = w.get("dial_type") == "static_ip"
        for k in ("ip", "mask", "gateway"):
            self.w[k].set_text((w.get(k) or "") if static else ("255.255.255.0" if k == "mask" else ""))
        self.w["username"].set_text(w.get("username") or "")
        self.w["password"].set_text("")
        manual = static or not w.get("enable_auto_dns")
        self.w["dns1"].set_text((w.get("dns1") or "") if manual else "")
        self.w["dns2"].set_text((w.get("dns2") or "") if manual else "")
        self.w["mtu"].set_text(str(w.get("mtu_size") or ""))
        self.ping.set_active(bool(w.get("enable_ping")))
        self._sync()
        lan_ip = self._lan.get("lan_ip") or {}
        self.lan_ip.set_text(lan_ip.get("ip") or "")
        self.lan_mask.set_text(lan_ip.get("mask") or "")
        d = self._lan.get("dhcp") or {}
        for k, e in self.dhcp.items():
            e.set_text(d.get(k) or "")
        self._dhcp_note.set_text(f"{d.get('ip_amount_in_use', '?')} addresses in use; gateway {d.get('gateway') or '?'}.")
        for f in (self._wan_frame, self._lan_frame, self._dhcp_frame):
            f.set_sensitive(True)

    def _save_wan(self):
        t = self._type()
        form = {"dial_type": t, "enable_auto_dns": self.dns_mode.get_selected() == 0,
                "mtu_size": self.w["mtu"].get_text().strip() or None}
        if t == "static_ip" or not form["enable_auto_dns"]:
            form.update(dns1=self.w["dns1"].get_text().strip(), dns2=self.w["dns2"].get_text().strip())
        if t == "static_ip":
            form.update(ip=self.w["ip"].get_text().strip(), mask=self.w["mask"].get_text().strip(),
                        gateway=self.w["gateway"].get_text().strip())
        if t == "pppoe":
            form.update(username=self.w["username"].get_text().strip(), password=self.w["password"].get_text())
        switching = t != self._wan.get("dial_type")
        self.confirm(
            ("Change how the Deco connects to the internet? If the new type is wrong for your modem or ISP, you "
             "stay offline until you change it back here." if switching else
             "Apply the internet settings? The connection drops for a few seconds.") + " Untested on hardware.",
            lambda: self.run_call(lambda d: deco_features.set_wan(d, **form),
                                  lambda _r: (self.window.toast("Internet settings applied."),
                                              GLib.timeout_add_seconds(15, lambda: (self.refresh(), False)[1])),
                                  label="wan_set"),
            destructive_label="Apply")

    def _save_ping(self):
        enable = self.ping.get_active()
        self.confirm(
            f"{'Answer' if enable else 'Stop answering'} pings from the internet? The connection may drop for a "
            "few seconds. Untested on hardware.",
            lambda: self.run_call(lambda d: deco_features.set_wan_ping(d, enable),
                                  lambda _r: self.window.toast("Ping setting applied."), label="wan_ping"),
            destructive_label="Apply")

    def _save_lan_ip(self):
        ip, mask = self.lan_ip.get_text().strip(), self.lan_mask.get_text().strip()
        cur = self._lan.get("lan_ip") or {}
        if ip == cur.get("ip") and mask == cur.get("mask"):
            self.window.toast("Nothing changed.")
            return
        self.confirm(
            "Change the Deco's address? Every device has to get a new address (reconnect it or wait for its lease "
            "to renew). Reservations, port forwards, and anything else using the old addresses stop working until "
            "you update them; then check that the DHCP pool sits inside the new subnet. Untested on hardware.",
            lambda: self.run_call(lambda d: deco_features.set_lan_ip(d, ip, mask),
                                  lambda _r: self.window.toast(f"The Deco is moving to {ip}. Reconnect when it is back."),
                                  label="lan_ip"),
            destructive_label="Change address")

    def _save_dhcp(self):
        form = {k: e.get_text().strip() for k, e in self.dhcp.items()}
        self.confirm(
            "Apply the DHCP settings? Devices keep their current address until their lease renews, and address "
            "reservations must stay inside the new pool. Untested on hardware.",
            lambda: self.run_call(lambda d: deco_features.set_dhcp(d, **form),
                                  lambda _r: (self.window.toast("DHCP settings applied."), self.refresh()), label="dhcp"),
            destructive_label="Apply")

    def on_disconnected(self):
        for f in (self._wan_frame, self._lan_frame, self._dhcp_frame):
            f.set_sensitive(False)
