"""Port Forwarding screen: list / add / delete rules."""

from . import Screen
from ..widgets import FormDialog, Table


class PortForwardScreen(Screen):
    def __init__(self, window):
        super().__init__(window, "Port Forwarding")
        self.add_action("Add…", self._add)
        self.add_action("Edit…", self._edit_selected)
        self.add_action("Delete", self._delete_selected)

        self.table = Table(columns=[
            ("Name", lambda r: r.get("service_name", ""), True),
            ("Protocol", lambda r: r.get("protocol", ""), True),
            ("External", lambda r: r.get("external_port", ""), True),
            ("Internal IP", lambda r: r.get("internal_ip", ""), True),
            ("Internal Port", lambda r: r.get("internal_port", ""), True),
        ], on_activate=lambda _r: self._edit_selected())
        self.append(self.table.scroller)

    def refresh(self):
        self.run_call(lambda d: d.port_forwards(), self.table.set_rows, label="port_forwards")

    def on_disconnected(self):
        self.table.set_rows([])

    # ---- add ----
    def _add(self, rule=None):
        if not self.window.connected:
            self.window.toast("Not connected.")
            return
        r = rule or {}
        FormDialog(
            self.window, "Edit port-forward rule" if rule else "Add port-forward rule",
            [
                ("name", "Name", r.get("service_name", "")),
                ("external_port", "External port", r.get("external_port", "")),
                ("internal_ip", "Internal IP", r.get("internal_ip", "")),
                ("internal_port", "Internal port (blank = same)", r.get("internal_port", "")),
                ("protocol", "Protocol", r.get("protocol", "tcp"), ["tcp", "udp", "all"]),
            ],
            on_submit=lambda v: self._do_add(v, rule), submit_label="Save" if rule else "Add",
        ).present()

    def _edit_selected(self):
        rule = self.table.selected()
        if rule is None:
            self.window.toast("Select a rule first.")
            return
        self._add(rule)

    def _do_add(self, v, rule=None):
        try:
            ext = int(v["external_port"])
            internal_port = int(v["internal_port"]) if v["internal_port"] else None
        except ValueError:
            self.window.toast("Ports must be numbers.")
            return
        if not v["internal_ip"]:
            self.window.toast("Internal IP is required.")
            return
        protocol = (v["protocol"] or "tcp").lower()
        if protocol not in ("tcp", "udp", "all"):
            self.window.toast("Protocol must be tcp, udp, or all.")
            return
        if rule:
            fn = lambda d: d.modify_port_forward(rule["port_forwarding_id"], ext, v["internal_ip"], internal_port,
                                                 protocol=protocol, name=v["name"])
        else:
            fn = lambda d: d.add_port_forward(ext, v["internal_ip"], internal_port, protocol=protocol, name=v["name"])
        self.run_call(fn, lambda _r: (self.window.toast("Rule saved." if rule else "Rule added."), self.refresh()),
                      label="add_pf")

    # ---- delete ----
    def _delete_selected(self):
        rule = self.table.selected()
        if rule is None:
            self.window.toast("Select a rule first.")
            return
        pid = rule.get("port_forwarding_id")
        name = rule.get("service_name") or pid
        self.confirm(
            f"Delete port-forward rule “{name}”?",
            lambda: self.run_call(
                lambda d: d.delete_port_forward(pid),
                lambda _r: (self.window.toast("Rule deleted."), self.refresh()),
                label="del_pf",
            ),
        )
