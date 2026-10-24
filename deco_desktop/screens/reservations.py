"""Reservations screen: list / add / edit / remove DHCP reservations."""

import re

from . import Screen
from ..widgets import FormDialog, Table

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[-:]){5}[0-9A-Fa-f]{2}$")
_IP_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")


def _valid_ip(s):
    return bool(_IP_RE.match(s)) and all(0 <= int(o) <= 255 for o in s.split("."))


def _norm_mac(s):
    return s.strip().upper().replace(":", "-")


class ReservationsScreen(Screen):
    def __init__(self, window):
        super().__init__(window, "Reservations")
        self.add_action("Add…", self._add)
        self.add_action("Edit…", self._edit_selected)
        self.add_action("Remove", self._remove_selected)

        self.table = Table(columns=[
            ("MAC", lambda r: r.get("mac", ""), True),
            ("Reserved IP", lambda r: r.get("ip", ""), True),
        ])
        self.append(self.table.scroller)

    def refresh(self):
        self.run_call(lambda d: d.reservations(), self.table.set_rows, label="reservations")

    def on_disconnected(self):
        self.table.set_rows([])

    # ---- add ----
    def _add(self, prefill=None):
        if not self.window.connected:
            self.window.toast("Not connected.")
            return
        prefill = prefill or {}
        FormDialog(
            self.window, "Add reservation",
            [("mac", "MAC", prefill.get("mac", "")),
             ("ip", "IP", prefill.get("ip", ""))],
            on_submit=self._do_add, submit_label="Add",
        ).present()

    def _do_add(self, v):
        mac, ip = _norm_mac(v["mac"]), v["ip"].strip()
        if not _MAC_RE.match(mac):
            self.window.toast("Invalid MAC (expected AA-BB-CC-DD-EE-FF).")
            return
        if not _valid_ip(ip):
            self.window.toast("Invalid IP address.")
            return
        self.run_call(
            lambda d: d.add_reservation(ip, mac),
            lambda _r: (self.window.toast("Reservation added."), self.refresh()),
            label="add_res",
        )

    # ---- edit ----
    def _edit_selected(self):
        res = self.table.selected()
        if res is None:
            self.window.toast("Select a reservation first.")
            return
        orig_mac, orig_ip = res.get("mac"), res.get("ip")
        FormDialog(
            self.window, f"Edit reservation {orig_mac}",
            [("mac", "MAC", orig_mac), ("ip", "IP", orig_ip)],
            on_submit=lambda v: self._do_edit(orig_ip, orig_mac, v),
            submit_label="Save",
        ).present()

    def _do_edit(self, orig_ip, orig_mac, v):
        mac, ip = _norm_mac(v["mac"]), v["ip"].strip()
        if not _MAC_RE.match(mac) or not _valid_ip(ip):
            self.window.toast("Invalid MAC or IP.")
            return
        self.run_call(
            lambda d: d.modify_reservation(orig_ip, orig_mac, ip, mac),
            lambda _r: (self.window.toast("Reservation updated."), self.refresh()),
            label="edit_res",
        )

    # ---- remove ----
    def _remove_selected(self):
        res = self.table.selected()
        if res is None:
            self.window.toast("Select a reservation first.")
            return
        mac = res.get("mac")
        self.confirm(
            f"Remove reservation for {mac} ({res.get('ip')})?",
            lambda: self.run_call(
                lambda d: d.remove_reservations(mac),
                lambda _r: (self.window.toast("Reservation removed."), self.refresh()),
                label="rm_res",
            ),
            destructive_label="Remove",
        )
