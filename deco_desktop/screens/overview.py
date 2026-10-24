"""Overview screen: internet, home network, firmware, each Deco's load, and messages."""

import datetime

from gi.repository import GLib, Gtk

import deco_features

from . import Screen
from ..widgets import Table, group_frame, kv_grid

AUTO_REFRESH_SECONDS = 10


def speed(kb):
    """KB/s as the Deco reports it, scaled like the Deco app (1000 KB/s and up shows MB/s)."""
    if kb is None or kb < 0:
        return "-"
    return f"{kb} KB/s" if kb < 1000 else f"{kb / 1024:.1f} MB/s"


def _message_text(m):
    content = m.get("content") or {}
    if m.get("type") == "new_report_weekly":
        return f"Weekly report ready ({content.get('date_range', '').replace('-', ' to ')})"
    if m.get("type") == "new_report_v2":
        return f"Monthly report ready ({content.get('year', '')}-{str(content.get('month', '')).zfill(2)})"
    return str(m.get("type", "")).replace("_", " ")


class OverviewScreen(Screen):
    def __init__(self, window):
        super().__init__(window, "Overview")

        self._auto = Gtk.CheckButton(label="Auto-refresh")
        self._auto.set_active(True)
        self._auto.connect("toggled", lambda _b: self._sync_timer())
        self.toolbar.append(self._auto)
        self._timer = None

        scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        scroller.set_child(body)
        self.append(scroller)

        self._cards = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3,
                                  column_spacing=12, row_spacing=12, homogeneous=True)
        body.append(self._cards)

        heading = Gtk.Label(label="Decos", xalign=0)
        heading.add_css_class("heading")
        body.append(heading)
        self.nodes = Table(columns=[
            ("Name", lambda n: n.get("name", ""), True),
            ("Model", lambda n: f"{n.get('device_model', '')}{', main' if n.get('role') == 'master' else ''}", True),
            ("Status", lambda n: "online" if n.get("group_status") == "connected" else "offline", True),
            ("CPU %", lambda n: n.get("cpu_usage") if n.get("cpu_usage") is not None else "-", True),
            ("Memory %", lambda n: round(100 * n["memory_usage"] / n["memory_total"]) if n.get("memory_total") else "-", True),
            ("Down", lambda n: speed(n.get("down_speed")) if n.get("group_status") == "connected" else "-", False),
            ("Up", lambda n: speed(n.get("up_speed")) if n.get("group_status") == "connected" else "-", False),
        ])
        self.nodes.scroller.set_vexpand(False)
        self.nodes.scroller.set_min_content_height(230)
        body.append(self.nodes.scroller)

        heading = Gtk.Label(label="Messages", xalign=0)
        heading.add_css_class("heading")
        body.append(heading)
        self._messages = Gtk.Label(xalign=0, wrap=True, selectable=True)
        body.append(self._messages)

    def refresh(self):
        self._sync_timer()
        self.run_call(deco_features.overview, self._populate, label="overview")

    def _populate(self, o):
        wan = (o.get("wan") or {}).get("ip_info") or {}
        lan = o.get("lan") or {}
        dhcp = o.get("dhcp") or {}
        main = next((n for n in o.get("nodes", []) if n.get("role") == "master"), {})
        lan_ip = lan.get("lan_ip") or {}
        cards = [
            ("Internet", [("Status", main.get("inet_status", "unknown")),
                          ("Public IP", (lan.get("wan_ip") or [wan.get("ip")])[0]),
                          ("Connection", str((o.get("wan") or {}).get("dial_type", "")).replace("_", " ")),
                          ("Gateway", wan.get("gateway")), ("DNS", ", ".join(lan.get("dns_server_ip") or []))]),
            ("Home network", [("Deco address", f"{lan_ip.get('ip')} / {lan_ip.get('mask')}" if lan_ip else None),
                              ("DHCP range", f"{dhcp.get('start_ip')} to {dhcp.get('end_ip')}" if dhcp.get("start_ip") else None),
                              ("Addresses in use", dhcp.get("ip_amount_in_use")),
                              ("DNS handed out", ", ".join(x for x in (dhcp.get("dns1"), dhcp.get("dns2")) if x))]),
            ("Firmware", [(f.get("model") or f.get("name"),
                           f"{(f.get('version') or '?').split(' Rel')[0]}, {'update available' if f.get('need_to_upgrade') else 'up to date'}")
                          for f in o.get("firmware", [])]),
        ]
        self._cards.remove_all()
        for title, pairs in cards:
            frame, box = group_frame(title)
            box.append(kv_grid(pairs))
            self._cards.append(frame)
        self._set_nodes(o.get("nodes", []))
        msgs = sorted(o.get("messages", []), key=lambda m: -m.get("timestamp", 0))
        self._messages.set_text("\n".join(
            f"{datetime.date.fromtimestamp(m['timestamp']).isoformat()}  {_message_text(m)}" for m in msgs) or "No messages.")

    def _set_nodes(self, nodes):
        self.nodes.set_rows(sorted(nodes, key=lambda n: (n.get("role") != "master",
                                                         n.get("group_status") != "connected", n.get("name", ""))))

    # ---- auto-refresh: just the node stats, the cheap live part of the overview ----
    def _sync_timer(self):
        want = self._auto.get_active() and self.window.connected
        if want and self._timer is None:
            self._timer = GLib.timeout_add_seconds(AUTO_REFRESH_SECONDS, self._tick)
        elif not want and self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _tick(self):
        # Only poll when this screen is the visible one and we're connected.
        if self.window.connected and self.get_mapped():
            self.run_call(deco_features.node_stats, self._set_nodes, label="node stats")
        return True  # keep the timer alive

    def on_disconnected(self):
        self.nodes.set_rows([])
        self._cards.remove_all()
        self._messages.set_text("")
        self._sync_timer()
