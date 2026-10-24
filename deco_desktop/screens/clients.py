"""Clients screen: fast live client list with sort, auto-refresh, and rename."""

from gi.repository import GLib, Gtk

from . import Screen
from ..widgets import FormDialog, Table

AUTO_REFRESH_SECONDS = 20


def _name(c):
    return c.get("name") or c.get("mac", "")


class ClientsScreen(Screen):
    def __init__(self, window):
        super().__init__(window, "Clients")

        self._auto = Gtk.CheckButton(label="Auto-refresh")
        self._auto.set_active(True)
        self._auto.connect("toggled", self._on_auto_toggled)
        self.toolbar.append(self._auto)
        self.add_action("Rename…", self._rename_selected)
        self.add_action("Reserve IP…", self._reserve_selected)

        self._count = Gtk.Label(xalign=0)
        self._count.add_css_class("dim-label")
        self.append(self._count)

        self.table = Table(
            columns=[
                ("Name", _name, True),
                ("IP", lambda c: c.get("ip", ""), True),
                ("MAC", lambda c: c.get("mac", ""), True),
                ("Type", lambda c: c.get("client_type", ""), True),
                ("Link", lambda c: c.get("wire_type", ""), True),
                ("Online", lambda c: "online" if c.get("online") else "offline", True),
            ],
            on_activate=lambda _row: self._rename_selected(),
        )
        self.append(self.table.scroller)

        self._timer = None

    # ---- data ----
    def refresh(self):
        self._sync_timer()
        self.run_call(lambda d: d.clients(), self._populate, label="clients")

    def _populate(self, clients):
        online = sum(1 for c in clients if c.get("online"))
        self.table.set_rows(clients)
        self._count.set_text(f"{online} online · {len(clients)} known")

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
        self.window.reserve_for_client(client.get("mac", ""), client.get("ip", ""))

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
            self.run_call(lambda d: d.clients(), self._populate, label="clients")
        return True  # keep the timer alive

    def on_disconnected(self):
        self.table.set_rows([])
        self._count.set_text("")
        self._sync_timer()
