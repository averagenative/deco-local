"""Port Forwarding screen: list / add / edit / delete rules, with the client each rule
forwards to."""

from . import Screen
from ..widgets import FormDialog, Table

_TYPE_IP = "Type an address below"
_PROTOCOLS = {"tcp": "TCP", "udp": "UDP", "all": "TCP + UDP"}


def _client_for(clients, ip):
    """The client at `ip`, preferring one that is online."""
    hits = [c for c in clients if c.get("ip") == ip]
    return next((c for c in hits if c.get("online")), hits[0] if hits else None)


class PortForwardScreen(Screen):
    def __init__(self, window):
        super().__init__(window, "Port Forwarding")
        self.add_action("Add…", self._add)
        self.add_action("Edit…", self._edit_selected)
        self.add_action("Delete", self._delete_selected)

        self.table = Table(columns=[
            ("Name", lambda r: r.get("service_name") or "(unnamed)", True),
            ("Protocol", lambda r: _PROTOCOLS.get(r.get("protocol"), r.get("protocol", "")), True),
            ("External", lambda r: r.get("external_port", ""), True, lambda r: int(r.get("external_port") or 0)),
            ("Forwards to", lambda r: f"{r.get('internal_ip')}:{r.get('internal_port')}", True),
            ("Client", self._client_label, True),
        ], on_activate=lambda _r: self._edit_selected())
        self.table.sort_by("External")
        self.append(self.table.scroller)
        self._clients = []
        self._rules = []

    def _client_label(self, r):
        c = _client_for(self._clients, r.get("internal_ip"))
        if c is None:
            return "unknown host"
        return f"{c.get('name') or c.get('mac')}{'' if c.get('online') else ' (offline)'}"

    def refresh(self):
        self.run_call(lambda d: (d.port_forwards(), d.clients()), self._populate, label="port_forwards")

    def _populate(self, result):
        self._rules, self._clients = result
        self.table.set_rows(self._rules)

    def on_disconnected(self):
        self._rules, self._clients = [], []
        self.table.set_rows([])

    def _ip_choices(self):
        """Drop-down labels for online clients with an address -> IP."""
        online = sorted((c for c in self._clients if c.get("online") and c.get("ip")),
                        key=lambda c: tuple(int(o) for o in c["ip"].split(".")))
        return {f"{c.get('name') or c['mac']}, {c['ip']}": c["ip"] for c in online}

    # ---- add ----
    def _add(self, rule=None):
        if not self.window.connected:
            self.window.toast("Not connected.")
            return
        r = rule or {}
        choices = self._ip_choices()
        FormDialog(
            self.window, "Edit port-forward rule" if rule else "Add port-forward rule",
            [
                ("name", "Name", r.get("service_name", "")),
                ("protocol", "Protocol", r.get("protocol", "tcp"), ["tcp", "udp", "all"]),
                ("external_port", "External port", r.get("external_port", "")),
                ("client", "Forward to client", _TYPE_IP, [_TYPE_IP, *choices]),
                ("internal_ip", "Internal IP", r.get("internal_ip", "")),
                ("internal_port", "Internal port (blank = same)", r.get("internal_port", "")),
            ],
            on_submit=lambda v: self._do_add({**v, "internal_ip": v["internal_ip"] or choices.get(v["client"], "")}, rule),
            submit_label="Save" if rule else "Add",
            note="Pick an online client, or type its address in Internal IP.",
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

        def clashes(x):
            if rule and x.get("port_forwarding_id") == rule.get("port_forwarding_id"):
                return False
            if int(x.get("external_port") or 0) != ext:
                return False
            return "all" in (x.get("protocol"), protocol) or x.get("protocol") == protocol

        clash = next((x for x in self._rules if clashes(x)), None)
        if clash:
            self.window.toast(f"External port {ext} is already forwarded by \"{clash.get('service_name') or clash.get('port_forwarding_id')}\".")
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
