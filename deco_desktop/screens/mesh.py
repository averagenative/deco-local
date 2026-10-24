"""Mesh screen: every Deco, with rename and reboot, and the LED settings."""

from gi.repository import GLib, Gtk

import deco_features

from . import Screen
from ..widgets import FormDialog, SettingsGroup, Table


def _backhaul(n):
    if n.get("role") == "master":
        return "gateway (wired WAN)"
    ct = n.get("connection_type")
    if not ct:
        return "wired" if n.get("group_status") == "connected" else "-"
    return " + ".join({"band5": "5 GHz", "band2_4": "2.4 GHz"}.get(b, b) for b in ct)


def _signal(n):
    sig = n.get("signal_level") or {}
    if n.get("role") == "master" or n.get("group_status") != "connected" or not (sig.get("band5") or sig.get("band2_4")):
        return "-"
    return f"5 GHz {sig.get('band5', '-')}, 2.4 GHz {sig.get('band2_4', '-')}"


class MeshScreen(Screen):
    def __init__(self, window):
        super().__init__(window, "Mesh")
        self.add_action("Rename…", self._rename)
        self.add_action("Reboot…", self._reboot)

        self.table = Table(columns=[
            ("Name", lambda n: n.get("name", ""), True),
            ("Model", lambda n: n.get("device_model", ""), True),
            ("Role", lambda n: "main" if n.get("role") == "master" else "satellite", True),
            ("Status", lambda n: "online" if n.get("group_status") == "connected" else "offline", True),
            ("IP", lambda n: n.get("ip") or "-", True),
            ("MAC", lambda n: n.get("mac") or "-", True),
            ("Backhaul", _backhaul, False),
            ("Signal", _signal, False),
            ("Firmware", lambda n: (n.get("software_ver") or "-").split(" Rel")[0], False),
        ], on_activate=lambda _n: self._rename(),
            widths={"Model": 60, "Role": 80, "Status": 72, "IP": 135, "MAC": 185, "Backhaul": 128, "Signal": 128, "Firmware": 120})
        self.append(self.table.scroller)

        self.led = SettingsGroup(
            "Deco LEDs", "The status lights on every Deco. Night mode turns them off between the two times.",
            [("enable", "toggle", "LEDs on"), ("enable_night_mode", "toggle", "Night mode"),
             ("time_begin", "time", "Lights off at"), ("time_end", "time", "Lights on at")],
            on_save=self._save_led)
        self.append(self.led.frame)

    def refresh(self):
        self.run_call(lambda d: (deco_features.devices(d), d.auto_led()), self._populate, label="mesh")

    def _populate(self, result):
        nodes, led = result
        self.table.set_rows(sorted(nodes, key=lambda n: (n.get("role") != "master",
                                                         n.get("group_status") != "connected", n.get("name", ""))))
        self.led.set_value(led)

    def _selected(self):
        n = self.table.selected()
        if n is None:
            self.window.toast("Select a Deco first.")
        return n

    def _rename(self):
        n = self._selected()
        if n is None:
            return
        FormDialog(self.window, f"Rename {n.get('name')}", [("name", "Name", n.get("name", ""))],
                   on_submit=lambda v: self._do_rename(n, v["name"])).present()

    def _do_rename(self, n, name):
        if not name:
            self.window.toast("Name cannot be empty.")
            return
        self.run_call(lambda d: d.set_device_nickname(n["device_id"], name),
                      lambda _r: (self.window.toast("Renamed."), self.refresh()), label="rename_node")

    def _reboot(self):
        n = self._selected()
        if n is None:
            return
        if n.get("group_status") != "connected":
            self.window.toast(f"{n.get('name')} is offline.")
            return
        main = n.get("role") == "master"
        self.confirm(
            "Reboot the main Deco? Your whole network and the internet go down for 3 to 5 minutes, and this app "
            "disconnects." if main else
            f"Reboot {n.get('name')}? It goes offline for 3 to 5 minutes. Devices near it move to another Deco or drop.",
            lambda: self.run_call(
                lambda d: d.reboot_devices(n["device_id"]),
                lambda _r: (self.window.toast(f"Rebooting {n.get('name')}. It comes back in 3 to 5 minutes."),
                            GLib.timeout_add_seconds(300, lambda: (self.refresh(), False)[1])),
                label="reboot"),
            destructive_label="Reboot")

    def _save_led(self, changes):
        self.run_call(lambda d: deco_features.write_setting(d, "led", changes),
                      lambda v: (self.led.set_value(v), self.window.toast("Saved: Deco LEDs.")), label="led")

    def on_disconnected(self):
        self.table.set_rows([])
        self.led.set_value(None)
