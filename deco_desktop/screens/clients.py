"""Clients screen: live client list with search, an online-only filter, traffic, and
rename / reserve / block actions."""

from gi.repository import GLib, Gtk

import deco_api
import deco_features

from . import Screen
from .overview import speed
from ..widgets import FormDialog, Table

AUTO_REFRESH_SECONDS = 20


def _name(c):
    return c.get("name") or c.get("mac", "")


def _type(c):
    t = c.get("custom_client_type") if c.get("has_set_client_type") and c.get("custom_client_type") else c.get("client_type")
    return str(t or "").replace("_", " ")


def _link(c):
    link = str(c.get("wire_type") or "").replace("_", " ")
    net = c.get("interface")
    return f"{link}, {net} network" if net and net != "main" else link


def _ip_num(c):
    try:
        return int.from_bytes(bytes(int(o) for o in c.get("ip", "").split(".")), "big")
    except ValueError:
        return -1


class ClientsScreen(Screen):
    def __init__(self, window):
        super().__init__(window, "Clients")

        self._auto = Gtk.CheckButton(label="Auto-refresh")
        self._auto.set_active(True)
        self._auto.connect("toggled", self._on_auto_toggled)
        self.toolbar.append(self._auto)
        self.add_action("Rename…", self._rename_selected)
        self.add_action("Reserve IP…", self._reserve_selected)
        self.add_action("Block…", self._block_selected)
        self.add_action("Blocked…", self._show_blocked)

        filters = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self._search = Gtk.SearchEntry(placeholder_text="Filter by name, IP, MAC, or brand", hexpand=True)
        self._search.connect("search-changed", lambda _e: self._apply_filter())
        filters.append(self._search)
        self._online_only = Gtk.CheckButton(label="Online only", active=True)
        self._online_only.connect("toggled", lambda _b: self._apply_filter())
        filters.append(self._online_only)
        self._count = Gtk.Label(xalign=1)
        self._count.add_css_class("dim-label")
        filters.append(self._count)
        self.append(filters)

        self.table = Table(
            columns=[
                ("Name", lambda c: f"{_name(c)} ({c['brand']})" if c.get("brand") and c["brand"] != "unknown" else _name(c),
                 True, lambda c: _name(c).lower()),
                ("IP", lambda c: f"{c.get('ip', '')}{' · reserved' if c.get('_reserved') else ''}", True, _ip_num),
                ("MAC", lambda c: c.get("mac", ""), True),
                ("Type", _type, True),
                ("Link", _link, True),
                ("Status", lambda c: "online" if c.get("online") else "offline", True),
                ("Down", lambda c: speed(c.get("_down")) if c.get("online") else "-", True, lambda c: c.get("_down", -1)),
                ("Up", lambda c: speed(c.get("_up")) if c.get("online") else "-", True, lambda c: c.get("_up", -1)),
            ],
            on_activate=lambda _row: self._rename_selected(),
            widths={"IP": 200, "MAC": 185, "Type": 95, "Link": 100, "Status": 75, "Down": 82, "Up": 82},
        )
        self.table.sort_by("Status", descending=True)
        self.append(self.table.scroller)

        self._all = []
        self._timer = None
        self._apply_filter()

    # ---- data ----
    def refresh(self):
        self._sync_timer()
        self.run_call(self._fetch, self._populate, label="clients")

    @staticmethod
    def _fetch(d):
        """Clients plus their live throughput (KB/s) and reserved address, merged per MAC."""
        clients = d.clients()
        try:
            speeds = d.client_list_speeds()
        except deco_api.DecoError:
            speeds = {}
        try:
            reserved = {r["mac"]: r["ip"] for r in d.reservations()}
        except deco_api.DecoError:
            reserved = {}
        for c in clients:
            if c.get("online") and c.get("mac") in speeds:
                c["_down"], c["_up"] = speeds[c["mac"]]
            c["_reserved"] = reserved.get(c.get("mac"), "")
        return clients

    def _populate(self, clients):
        self._all = clients
        self.table.set_rows(clients)
        self._apply_filter()

    def _apply_filter(self):
        q = self._search.get_text().strip().lower()
        online_only = self._online_only.get_active()

        def keep(c):
            if online_only and not c.get("online"):
                return False
            return not q or any(q in str(c.get(k) or "").lower() for k in ("name", "ip", "mac", "brand", "client_type"))

        self.table.set_filter(keep)
        online = sum(1 for c in self._all if c.get("online"))
        shown = self.table.visible_count()
        self._count.set_text(f"{online} online · {len(self._all)} known" + (f" · {shown} shown" if q else "")
                             if self._all else "")

    # ---- rename ----
    def _rename_selected(self):
        client = self.table.selected()
        if client is None:
            self.window.toast("Select a client first.")
            return
        mac = client.get("mac")
        FormDialog(
            self.window, f"Rename {mac}",
            [("name", "Name", client.get("name", ""))],
            on_submit=lambda v: self._do_rename(mac, v["name"]),
        ).present()

    def _do_rename(self, mac, name):
        if not name:
            self.window.toast("Name cannot be empty.")
            return
        self.run_call(
            lambda d: d.set_client(mac, name=name),
            lambda _r: (self.window.toast("Renamed."), self.refresh()),
            label="rename",
        )

    def _reserve_selected(self):
        client = self.table.selected()
        if client is None:
            self.window.toast("Select a client first.")
            return
        if client.get("_reserved"):
            self.window.toast(f"{_name(client)} is already reserved at {client['_reserved']}.")
            return
        self.window.reserve_for_client(client.get("mac", ""), client.get("ip", ""))

    # ---- block ----
    def _block_selected(self):
        client = self.table.selected()
        if client is None:
            self.window.toast("Select a client first.")
            return
        mac = client.get("mac")
        self.confirm(
            f"Block {_name(client)} ({mac})? It loses its network connection until you unblock it.",
            lambda: self.run_call(lambda d: deco_features.block_macs(d, [mac]),
                                  lambda _r: (self.window.toast(f"Blocked {_name(client)}."), self.refresh()), label="block"),
            destructive_label="Block")

    def _show_blocked(self):
        self.run_call(deco_features.blocked_clients, self._blocked_dialog, label="blocked")

    def _blocked_dialog(self, blocked):
        win = Gtk.Window(title="Blocked clients", transient_for=self.window, modal=True, default_width=420)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(14)
        clients = blocked.get("client_list", [])
        if not clients:
            box.append(Gtk.Label(label="No blocked clients.", xalign=0))
        for b in clients:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.append(Gtk.Label(label=f"{b.get('name') or b.get('mac')}  ({b.get('mac')})", xalign=0, hexpand=True))
            btn = Gtk.Button(label="Unblock")
            btn.connect("clicked", lambda _b, m=b["mac"]: (win.close(), self.run_call(
                lambda d: d.unblock_clients(m), lambda _r: (self.window.toast("Unblocked."), self.refresh()), label="unblock")))
            row.append(btn)
            box.append(row)
        close = Gtk.Button(label="Close", halign=Gtk.Align.END)
        close.connect("clicked", lambda _b: win.close())
        box.append(close)
        win.set_child(box)
        win.present()

    # ---- auto-refresh ----
    def _on_auto_toggled(self, _btn):
        self._sync_timer()

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
            self.run_call(self._fetch, self._populate, label="clients")
        return True  # keep the timer alive

    def on_disconnected(self):
        self._all = []
        self.table.set_rows([])
        self._apply_filter()
        self._sync_timer()
