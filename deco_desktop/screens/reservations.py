"""Reservations screen: list / add / edit / remove DHCP reservations, with each
reservation's client and whether it is using the reserved address now."""

import re

from . import Screen
from ..widgets import FormDialog, Table

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[-:]){5}[0-9A-Fa-f]{2}$")
_IP_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
_PICK = "Pick a client, or type the MAC below"


def _valid_ip(s):
    return bool(_IP_RE.match(s)) and all(0 <= int(o) <= 255 for o in s.split("."))


def _norm_mac(s):
    return s.strip().upper().replace(":", "-")


def _ip_num(ip):
    try:
        return int.from_bytes(bytes(int(o) for o in str(ip).split(".")), "big")
    except ValueError:
        return -1


def _now(r):
    c = r.get("_client")
    if not c:
        return "not seen"
    if not c.get("online"):
        return "offline"
    return "using it" if c.get("ip") == r.get("ip") else f"on {c.get('ip') or 'no IP'} (renews on reconnect)"


class ReservationsScreen(Screen):
    def __init__(self, window):
        super().__init__(window, "Reservations")
        self.add_action("Add…", self._add)
        self.add_action("Edit…", self._edit_selected)
        self.add_action("Remove", self._remove_selected)

        self.table = Table(columns=[
            ("Client", lambda r: (r.get("_client") or {}).get("name") or "", True),
            ("MAC", lambda r: r.get("mac", ""), True),
            ("Reserved IP", lambda r: r.get("ip", ""), True, lambda r: _ip_num(r.get("ip"))),
            ("Now", _now, True),
        ], on_activate=lambda _r: self._edit_selected())
        self.table.sort_by("Reserved IP")
        self.append(self.table.scroller)
        self._clients = []
        self._rows = []

    def refresh(self):
        self.run_call(lambda d: (d.reservations(), d.clients()), self._populate, label="reservations")

    def _populate(self, result):
        reservations, self._clients = result
        by_mac = {_norm_mac(c.get("mac", "")): c for c in self._clients}
        for r in reservations:
            r["_client"] = by_mac.get(_norm_mac(r.get("mac", "")))
        self._rows = reservations
        self.table.set_rows(reservations)

    def on_disconnected(self):
        self._rows, self._clients = [], []
        self.table.set_rows([])

    def _client_choices(self):
        """Drop-down labels for known clients (online first) -> client."""
        known = sorted((c for c in self._clients if c.get("mac")),
                       key=lambda c: (not c.get("online"), (c.get("name") or c["mac"]).lower()))
        return {f"{c.get('name') or c['mac']}{', ' + c['ip'] if c.get('ip') else ''}{'' if c.get('online') else ' (offline)'}  [{c['mac']}]": c
                for c in known}

    def _check(self, mac, ip, original=None):
        """Return an error message, or None if the reservation can be saved."""
        if not _MAC_RE.match(mac):
            return "Invalid MAC (expected AA-BB-CC-DD-EE-FF)."
        if not _valid_ip(ip):
            return "Invalid IP address."
        for r in self._rows:
            if original and _norm_mac(r["mac"]) == _norm_mac(original["mac"]):
                continue
            if _norm_mac(r["mac"]) == mac:
                return f"{mac} is already reserved at {r['ip']}. Edit that reservation instead."
            if r.get("ip") == ip:
                return f"{ip} is already reserved for {r['mac']}."
        return None

    # ---- add ----
    def _add(self, prefill=None):
        if not self.window.connected:
            self.window.toast("Not connected.")
            return
        prefill = prefill or {}
        choices = self._client_choices()
        picked = next((label for label, c in choices.items() if prefill.get("mac") and c["mac"] == prefill["mac"]), _PICK)
        FormDialog(
            self.window, "Add reservation",
            [("client", "Client", picked, [_PICK, *choices]),
             ("mac", "MAC", prefill.get("mac", "")),
             ("ip", "IP", prefill.get("ip", ""))],
            on_submit=lambda v: self._do_add(v, choices), submit_label="Reserve",
            note="The client keeps this address from its next DHCP renewal on.",
        ).present()

    def _do_add(self, v, choices):
        client = choices.get(v["client"])
        mac = _norm_mac(v["mac"] or (client or {}).get("mac", ""))
        ip = (v["ip"] or (client or {}).get("ip", "")).strip()
        problem = self._check(mac, ip)
        if problem:
            self.window.toast(problem)
            return
        self.run_call(
            lambda d: d.add_reservation(ip, mac),
            lambda _r: (self.window.toast(f"Reserved {ip} for {mac}."), self.refresh()),
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
            on_submit=lambda v: self._do_edit(res, v),
            submit_label="Save",
        ).present()

    def _do_edit(self, res, v):
        mac, ip = _norm_mac(v["mac"]), v["ip"].strip()
        if mac == _norm_mac(res["mac"]) and ip == res.get("ip"):
            return
        problem = self._check(mac, ip, original=res)
        if problem:
            self.window.toast(problem)
            return
        self.run_call(
            lambda d: d.modify_reservation(res["ip"], res["mac"], ip, mac),
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
        who = (res.get("_client") or {}).get("name")
        self.confirm(
            f"Remove the reservation for {who + ' (' + mac + ')' if who else mac}? It keeps {res.get('ip')} until its "
            "lease expires, then gets any free address.",
            lambda: self.run_call(
                lambda d: d.remove_reservations(mac),
                lambda _r: (self.window.toast("Reservation removed."), self.refresh()),
                label="rm_res",
            ),
            destructive_label="Remove",
        )
