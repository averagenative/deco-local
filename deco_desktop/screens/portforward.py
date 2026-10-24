"""Port Forwarding screen: list / add / delete rules."""

from . import Screen
from ..widgets import FormDialog, Table


class PortForwardScreen(Screen):
    def __init__(self, window):
        super().__init__(window, "Port Forwarding")
        self.add_action("Add…", self._add)
        self.add_action("Delete", self._delete_selected)

        self.table = Table(columns=[
            ("Name", lambda r: r.get("service_name", ""), True),
            ("Protocol", lambda r: r.get("protocol", ""), True),
            ("External", lambda r: r.get("external_port", ""), True),
            ("Internal IP", lambda r: r.get("internal_ip", ""), True),
            ("Internal Port", lambda r: r.get("internal_port", ""), True),
        ])
        self.append(self.table.scroller)

    def refresh(self):
        self.run_call(lambda d: d.port_forwards(), self.table.set_rows, label="port_forwards")

    def on_disconnected(self):
        self.table.set_rows([])

    # ---- add ----
    def _add(self):
        if not self.window.connected:
            self.window.toast("Not connected.")
            return
        FormDialog(
            self.window, "Add port-forward rule",
            [
                ("name", "Name", ""),
                ("external_port", "External port", ""),
                ("internal_ip", "Internal IP", ""),
                ("internal_port", "Internal port (blank = same)", ""),
                ("protocol", "Protocol (tcp/udp/all)", "tcp"),
            ],
            on_submit=self._do_add, submit_label="Add",
        ).present()

    def _do_add(self, v):
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
        self.run_call(
            lambda d: d.add_port_forward(ext, v["internal_ip"], internal_port,
                                         protocol=protocol, name=v["name"]),
            lambda _r: (self.window.toast("Rule added."), self.refresh()),
            label="add_pf",
        )

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
