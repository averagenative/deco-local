"""deco_demo — an in-memory stand-in for `deco_api.DecoLocal`.

Lets you try the web UI, the REST API, and the desktop app without a Deco (and makes
screenshots that show no real network). Enable it with DECO_DEMO=1. Changes you make
(rules, reservations, names) live in memory until the process exits.
"""

import base64
import copy
import itertools


def _b64(text):
    return base64.b64encode(text.encode()).decode()


def _mac(n):
    return f"02-DE-C0-00-00-{n:02X}"


_CLIENTS = [
    # name, brand, n, ip, type, link, network, online
    ("nas", "Synology", 1, "192.168.68.10", "pc", "wired", "main", True),
    ("printer", "Brother", 2, "192.168.68.20", "pc", "wireless", "main", True),
    ("front-door-cam", "Reolink", 3, "192.168.68.30", "camera", "wireless", "main", True),
    ("Living Room TV", "Roku", 4, "192.168.68.51", "iot_device", "wireless", "main", True),
    ("alex-laptop", "Framework", 5, "192.168.68.52", "pc", "wireless", "main", True),
    ("pixel-8", "Google", 6, "192.168.68.53", "phone", "wireless", "main", True),
    ("iPad", "Apple", 7, "192.168.68.54", "tablet", "wireless", "main", True),
    ("thermostat", "ecobee", 8, "192.168.68.55", "iot_device", "wireless", "main", True),
    ("game-console", "Nintendo", 9, "192.168.68.56", "game_console", "wireless", "main", True),
    ("guest-phone", "Samsung", 10, "192.168.68.120", "phone", "wireless", "guest", True),
    ("old-laptop", "Lenovo", 11, "", "pc", "unknown", "main", False),
    ("smart-plug", "Kasa", 12, "", "iot_device", "unknown", "main", False),
]

_DEVICES = [
    {"role": "master", "nickname": "living_room", "custom_nickname": None, "device_model": "X60",
     "hardware_ver": "4.0", "ip": "192.168.68.1", "mac": "02-DE-C0-00-01-01", "group_status": "connected",
     "inet_status": "online", "connection_type": [], "signal_level": {"band5": "0", "band2_4": "0"},
     "software_ver": "1.7.1 Build 25080612 Rel. 70421"},
    {"role": "slave", "nickname": "custom", "custom_nickname": _b64("Office"), "device_model": "X60",
     "hardware_ver": "4.0", "ip": "192.168.68.2", "mac": "02-DE-C0-00-01-02", "group_status": "connected",
     "inet_status": "online", "connection_type": ["band2_4", "band5"], "signal_level": {"band5": "3", "band2_4": "2"},
     "software_ver": "1.7.1 Build 25080612 Rel. 70421"},
    {"role": "slave", "nickname": "garage", "custom_nickname": None, "device_model": "X55",
     "hardware_ver": "1.0", "ip": None, "mac": "02-DE-C0-00-01-03", "group_status": "disconnected",
     "inet_status": "offline", "connection_type": None, "signal_level": {"band5": 0, "band2_4": 0},
     "software_ver": None},
]


class DemoDeco:
    """Implements the DecoLocal methods the UIs and the REST API use."""

    def __init__(self, *_args, **_kwargs):
        self.master = {"device_model": "X60", "ip": "192.168.68.1"}
        self.nodes = [d for d in _DEVICES if d["group_status"] == "connected"]
        self._clients = [
            {"name": name, "brand": brand, "mac": _mac(n), "ip": ip, "client_type": ctype,
             "wire_type": link, "interface": net, "online": online}
            for name, brand, n, ip, ctype, link, net, online in _CLIENTS
        ]
        self._pf = [
            {"port_forwarding_id": "1", "service_name": "plex", "protocol": "tcp",
             "external_port": "32400", "internal_ip": "192.168.68.10", "internal_port": "32400"},
            {"port_forwarding_id": "2", "service_name": "ssh", "protocol": "tcp",
             "external_port": "2222", "internal_ip": "192.168.68.10", "internal_port": "22"},
            {"port_forwarding_id": "3", "service_name": "wireguard", "protocol": "udp",
             "external_port": "51820", "internal_ip": "192.168.68.10", "internal_port": "51820"},
        ]
        self._res = [{"mac": _mac(1), "ip": "192.168.68.10"}, {"mac": _mac(2), "ip": "192.168.68.20"},
                     {"mac": _mac(3), "ip": "192.168.68.30"}, {"mac": _mac(11), "ip": "192.168.68.40"}]
        self._ids = itertools.count(4)

    def connect(self):
        return self

    def close(self):
        pass

    # ---- reads ----
    def devices(self):
        return copy.deepcopy(_DEVICES)

    def clients(self, decode_names=True):
        return copy.deepcopy(self._clients)

    def port_forwards(self, decode_names=True):
        return copy.deepcopy(self._pf)

    def reservations(self):
        return copy.deepcopy(self._res)

    # ---- writes ----
    def set_client(self, mac, **changes):
        for c in self._clients:
            if c["mac"] == mac and "name" in changes:
                c["name"] = changes["name"]
        return {"error_code": 0}

    def add_port_forward(self, external_port, internal_ip, internal_port=None, protocol="tcp", name="",
                         service_type="custom"):
        pid = str(next(self._ids))
        self._pf.append({"port_forwarding_id": pid, "service_name": name, "protocol": protocol,
                         "external_port": str(external_port), "internal_ip": internal_ip,
                         "internal_port": str(internal_port if internal_port is not None else external_port)})
        return pid

    def delete_port_forward(self, port_forwarding_id):
        self._pf = [r for r in self._pf if r["port_forwarding_id"] != str(port_forwarding_id)]
        return {"error_code": 0}

    def add_reservation(self, ip, mac):
        self._res.append({"mac": mac, "ip": ip})
        return {"error_code": 0}

    def remove_reservations(self, macs):
        macs = {macs} if isinstance(macs, str) else set(macs)
        self._res = [r for r in self._res if r["mac"] not in macs]
        return {"error_code": 0}

    def modify_reservation(self, original_ip, original_mac, ip, mac):
        for r in self._res:
            if r["mac"] == original_mac and r["ip"] == original_ip:
                r.update(mac=mac, ip=ip)
        return {"error_code": 0}
