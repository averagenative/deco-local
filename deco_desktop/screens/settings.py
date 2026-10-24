"""Network, Security, and System screens: groups of Deco settings plus a list each
(static routes, allowed websites) or read-only facts (DHCP, firmware, time zone)."""

import datetime
import ipaddress

from gi.repository import Gtk

import deco_features

from . import Screen
from ..widgets import FormDialog, SettingsGroup, Table, group_frame, kv_grid


def _qos_problem(v):
    if v.get("enable") and (int(v.get("downstream_bandwidth") or 0) < 5 * 1024 or int(v.get("upstream_bandwidth") or 0) < 1024):
        return "Those speeds look too low (under 5 Mbps down or 1 Mbps up). QoS would throttle your connection to them."
    return None


class SettingsScreen(Screen):
    """Base: GROUPS is a list of (key, title, description, fields[, validate]); subclasses add
    their own widgets in build_extra() and fill them in populate_extra()."""

    GROUPS = ()

    def __init__(self, window, title):
        super().__init__(window, title)
        scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        scroller.set_child(self.body)
        self.append(scroller)
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3,
                                column_spacing=12, row_spacing=12, homogeneous=True, valign=Gtk.Align.START)
        self.body.append(self.flow)
        self.groups = {}
        for key, title_, desc, fields, *validate in self.GROUPS:
            g = SettingsGroup(title_, desc, fields, on_save=lambda ch, k=key: self._save(k, ch),
                              validate=validate[0] if validate else None)
            self.groups[key] = g
            self.flow.append(g.frame)
        self.build_extra()

    def build_extra(self):
        pass

    def load_extra(self, d):
        return None

    def populate_extra(self, settings, extra):
        pass

    def refresh(self):
        self.run_call(lambda d: (deco_features.read_settings(d), self.load_extra(d)), self._populate,
                      label=self.__class__.__name__)

    def _populate(self, result):
        settings, extra = result
        for key, g in self.groups.items():
            g.set_value(settings.get(key))
        self.populate_extra(settings, extra)

    def _save(self, key, changes):
        title = next(t for k, t, *_ in self.GROUPS if k == key)
        self.run_call(lambda d: deco_features.write_setting(d, key, changes),
                      lambda v: (self.groups[key].set_value(v), self.window.toast(f"Saved: {title}.")), label=f"set_{key}")

    def on_disconnected(self):
        for g in self.groups.values():
            g.set_value(None)

    def info_frame(self, title):
        """A read-only frame added to the grid; returns a setter taking (key, value) pairs."""
        frame, box = group_frame(title)
        holder = {"grid": None}
        self.flow.append(frame)

        def set_pairs(pairs, note=None):
            if holder["grid"] is not None:
                box.remove(holder["grid"])
            grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            grid.append(kv_grid(pairs))
            if note:
                n = Gtk.Label(label=note, xalign=0, wrap=True, max_width_chars=34)
                n.add_css_class("dim-label")
                grid.append(n)
            holder["grid"] = grid
            box.append(grid)
        return set_pairs


class NetworkScreen(SettingsScreen):
    GROUPS = (
        ("upnp", "UPnP", "Lets apps and game consoles open ports on their own. Turn it off to allow only your "
         "port-forwarding rules.", [("enable", "toggle", "On")]),
        ("sip_alg", "SIP ALG", "Helps VoIP phones work through NAT. If calls drop or have one-way audio, try turning it off.",
         [("enable", "toggle", "On")]),
        ("client_isolation", "Client isolation", "Keeps devices on your network from reaching each other.",
         [("enable", "toggle", "On")]),
        ("qos", "QoS (bandwidth)", "Shares your connection fairly and lets you give clients priority. Set the speeds to "
         "about 90% of what your plan really delivers: too low, and QoS slows your whole connection.",
         [("enable", "toggle", "On"), ("downstream_bandwidth", "mbps", "Download (Mbps)"),
          ("upstream_bandwidth", "mbps", "Upload (Mbps)")], _qos_problem),
    )

    def __init__(self, window):
        super().__init__(window, "Network")
        self.add_action("Add route…", lambda: self._route_dialog(None))
        self.add_action("Edit route…", self._edit_route)
        self.add_action("Delete route", self._delete_route)

    def build_extra(self):
        self.dhcp_info = self.info_frame("DHCP server")
        self.ddns_info = self.info_frame("Dynamic DNS")
        heading = Gtk.Label(label="Static routes", xalign=0)
        heading.add_css_class("heading")
        self.body.append(heading)
        self.routes = Table(columns=[
            ("Name", lambda r: r.get("name") or "(unnamed)", True),
            ("Network", lambda r: f"{r.get('ip')} / {r.get('mask')}", True),
            ("Gateway", lambda r: r.get("gateway", ""), True),
            ("Interface", lambda r: str(r.get("interface", "")).upper(), True),
            ("State", lambda r: "on" if r.get("enable") else "off", True),
        ], on_activate=lambda _r: self._edit_route())
        self.routes.scroller.set_vexpand(False)
        self.routes.scroller.set_min_content_height(160)
        self.body.append(self.routes.scroller)

    def load_extra(self, d):
        return deco_features.static_routes(d)

    def populate_extra(self, settings, routes):
        dhcp, ddns = settings.get("dhcp") or {}, settings.get("ddns") or {}
        self.dhcp_info([("Range", f"{dhcp.get('start_ip')} to {dhcp.get('end_ip')}" if dhcp.get("start_ip") else None),
                        ("Gateway", dhcp.get("gateway")),
                        ("DNS", ", ".join(x for x in (dhcp.get("dns1"), dhcp.get("dns2")) if x)),
                        ("Addresses in use", dhcp.get("ip_amount_in_use"))])
        self.ddns_info([("Status", "on" if ddns.get("ddns_enable") else "off"),
                        ("Connection", ((ddns.get("ddns_info") or {}).get("connection_status") or "").replace("_", " "))],
                       note="Read only here: setting up DDNS needs a TP-Link DDNS account.")
        self.routes.set_rows((routes or {}).get("route_static_list", []))

    def _edit_route(self):
        r = self.routes.selected()
        if r is None:
            self.window.toast("Select a route first.")
            return
        self._route_dialog(r)

    def _route_dialog(self, r):
        editing = r is not None
        FormDialog(self.window, "Edit static route" if editing else "Add static route", [
            ("name", "Name", r.get("name", "") if editing else ""),
            ("ip", "Destination network", r.get("ip", "") if editing else ""),
            ("mask", "Netmask", r.get("mask", "") if editing else "255.255.255.0"),
            ("gateway", "Gateway", r.get("gateway", "") if editing else ""),
            ("interface", "Interface", (r.get("interface") if editing else "lan"), ["lan", "wan"]),
            ("enable", "State", ("on" if not editing or r.get("enable") else "off"), ["on", "off"]),
        ], on_submit=lambda v: self._save_route(r, v), submit_label="Save" if editing else "Add").present()

    def _save_route(self, r, v):
        try:
            for k in ("ip", "mask", "gateway"):
                ipaddress.IPv4Address(v[k])
        except ValueError:
            self.window.toast("Destination, netmask, and gateway must be IPv4 addresses.")
            return
        args = (v["ip"], v["mask"], v["gateway"], v["interface"], v["name"], v["enable"] == "on")
        if r is None:
            fn = lambda d: d.add_static_route(*args)
        else:
            fn = lambda d: d.modify_static_route(r["id"], *args)
        self.run_call(fn, lambda _r: (self.window.toast("Route saved."), self.refresh()), label="route")

    def _delete_route(self):
        r = self.routes.selected()
        if r is None:
            self.window.toast("Select a route first.")
            return
        self.confirm(f"Delete the route to {r.get('ip')} / {r.get('mask')}?",
                     lambda: self.run_call(lambda d: d.remove_static_routes(r["id"]),
                                           lambda _r: (self.window.toast("Route deleted."), self.refresh()), label="route_rm"))

    def on_disconnected(self):
        super().on_disconnected()
        self.routes.set_rows([])


class SecurityScreen(SettingsScreen):
    GROUPS = (
        ("homeshield", "HomeShield protection", "Some protections need a HomeShield Pro subscription. Without one, "
         "the Deco rejects the change.",
         [("web_protection", "toggle", "Block malicious websites"), ("iot_protection", "toggle", "Protect IoT devices"),
          ("intrusion_prevention", "toggle", "Intrusion prevention")]),
    )

    def __init__(self, window):
        super().__init__(window, "Security")
        self.add_action("Allow website…", self._add_site)
        self.add_action("Remove website", self._remove_site)

    def build_extra(self):
        heading = Gtk.Label(label="Allowed websites (HomeShield never blocks these)", xalign=0)
        heading.add_css_class("heading")
        self.body.append(heading)
        self.sites = Table(columns=[("Domain", lambda s: s, True)])
        self.sites.scroller.set_vexpand(False)
        self.sites.scroller.set_min_content_height(160)
        self.body.append(self.sites.scroller)

    def load_extra(self, d):
        return d.allowed_websites()

    def populate_extra(self, settings, sites):
        self.sites.set_rows((sites or {}).get("website_list", []))

    def _add_site(self):
        FormDialog(self.window, "Allow a website", [("domain", "Domain", "")],
                   on_submit=self._do_add_site, submit_label="Allow").present()

    def _do_add_site(self, v):
        domain = v["domain"].lower().removeprefix("https://").removeprefix("http://").split("/")[0]
        if "." not in domain:
            self.window.toast("Enter a domain such as example.com.")
            return
        self.run_call(lambda d: d.allow_website(domain),
                      lambda _r: (self.window.toast(f"Allowed {domain}."), self.refresh()), label="site_add")

    def _remove_site(self):
        domain = self.sites.selected()
        if domain is None:
            self.window.toast("Select a website first.")
            return
        self.run_call(lambda d: d.disallow_website(domain),
                      lambda _r: (self.window.toast(f"Removed {domain}."), self.refresh()), label="site_rm")

    def on_disconnected(self):
        super().on_disconnected()
        self.sites.set_rows([])


class SystemScreen(SettingsScreen):
    GROUPS = (
        ("fw_auto_update", "Automatic firmware updates", "Lets the Deco install updates overnight.",
         [("enable_auto_update", "toggle", "On"), ("time_begin", "time", "Window opens"), ("time_end", "time", "Window closes")]),
        ("reboot_schedule", "Scheduled reboot", "Restarts every Deco at a set time each day.",
         [("enable", "toggle", "On"), ("setting.time", "time", "Reboot at")]),
        ("wifi_schedule", "Wi-Fi schedule", "Turns Wi-Fi off on every Deco between two times, for example overnight.",
         [("enable", "toggle", "On"), ("time_begin", "time", "Wi-Fi off from"), ("time_end", "time", "Back on at")]),
        ("eco_mode", "Eco mode", "Saves power at the cost of Wi-Fi range and speed.", [("enable", "toggle", "On")]),
        ("monthly_report", "Network reports", "The weekly and monthly reports shown on the Overview screen.",
         [("enable", "toggle", "On")]),
    )

    def __init__(self, window):
        super().__init__(window, "System")

    def build_extra(self):
        self.fw_info = self.info_frame("Firmware")
        self.tz_info = self.info_frame("Time zone")

    def load_extra(self, d):
        return deco_features.firmware(d)

    def populate_extra(self, settings, fw):
        fw = fw or {}
        self.fw_info([(f.get("model"), f"{(f.get('version') or '?').split(' Rel')[0]}, "
                                       f"{'update available' if f.get('need_to_upgrade') else 'up to date'}")
                      for f in fw.get("firmware", [])] + [("Update status", (fw.get("progress") or {}).get("status"))],
                     note="Updates install automatically in the window set here. To update right away, use the Deco app.")
        tz = settings.get("system_time") or {}
        self.tz_info([("Region", tz.get("tz_region")),
                      ("Deco time", datetime.datetime.fromtimestamp(tz["time"]).strftime("%Y-%m-%d %H:%M") if tz.get("time") else None)])
