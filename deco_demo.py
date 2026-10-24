"""deco_demo — an in-memory stand-in for `deco_api.DecoLocal`.

Lets you try the web UI, the REST API, and the desktop app without a Deco (and makes
screenshots that show no real network). Enable it with DECO_DEMO=1. Changes you make
(rules, reservations, names) live in memory until the process exits.
"""

import base64
import copy
import itertools
import time

from deco_api import DecoError


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
    {"device_id": "demo-1", "role": "master", "nickname": "living_room", "custom_nickname": None, "device_model": "X60",
     "hardware_ver": "4.0", "ip": "192.168.68.1", "mac": "02-DE-C0-00-01-01", "group_status": "connected",
     "inet_status": "online", "connection_type": [], "signal_level": {"band5": "0", "band2_4": "0"},
     "software_ver": "1.7.1 Build 25080612 Rel. 70421"},
    {"device_id": "demo-2", "role": "slave", "nickname": "custom", "custom_nickname": _b64("Office"), "device_model": "X60",
     "hardware_ver": "4.0", "ip": "192.168.68.2", "mac": "02-DE-C0-00-01-02", "group_status": "connected",
     "inet_status": "online", "connection_type": ["band2_4", "band5"], "signal_level": {"band5": "3", "band2_4": "2"},
     "software_ver": "1.7.1 Build 25080612 Rel. 70421"},
    {"device_id": "demo-3", "role": "slave", "nickname": "garage", "custom_nickname": None, "device_model": "X55",
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
        self._blocked = [{"mac": _mac(12), "name": _b64("smart-plug"), "client_type": "iot_device"}]
        self._routes = [{"id": "1", "ip": "10.20.0.0", "mask": "255.255.255.0", "gateway": "192.168.68.10",
                         "interface": "lan", "name": _b64("lab network"), "enable": True}]
        self._sites = ["intranet.example.com"]
        self._settings = {
            "upnp": {"enable": True}, "sip_alg": {"enable": True}, "client_isolation": {"enable": False},
            "monthly_report": {"enable": True},
            "led": {"enable": True, "enable_night_mode": True, "time_begin": 1320, "time_end": 420,
                    "led_individual_control": False, "schedule": []},
            "reboot_schedule": {"enable": False, "setting": {"time": 180, "mode": "every_day"}},
            "fw_auto_update": {"enable_auto_update": True, "time_begin": "180", "time_end": "300"},
            "wifi_schedule": {"enable": False, "time_begin": 0, "time_end": 420, "has_set_wifi_schedule": False,
                              "enable_band2_4": False},
            "eco_mode": {"enable": False, "has_set_eco_mode": False},
            "homeshield": {"web_protection": True, "iot_protection": False, "intrusion_prevention": False},
            "qos": {"enable": False, "has_set_bandwidth": False, "downstream_bandwidth": 100, "upstream_bandwidth": 100,
                    "downstream_bandwidth_max": 1024000, "upstream_bandwidth_max": 1024000},
        }
        def net(ssid, pw, enable, enc="wpa2"):
            return {"ssid": _b64(ssid), "password": _b64(pw), "enable": enable, "encryption_mode": enc}
        def band(radio, backhaul):
            return {"host": net("demo-home", "correct-horse-battery", True),
                    "guest": net("demo-home-guest", "", False, "none"),
                    "iot": net("demo-home-iot", "staple-lamp-42", False), "radio": radio, "backhaul": {"channel": backhaul}}
        self._wifi = {"band2_4": band({"enable": True, "channel": "0", "htmode": "HT40", "hwmode": "11ng"}, 6),
                      "band5_1": band({"enable": True, "channel": "0", "htmode": "HT80", "hwmode": "11ac"}, 44)}

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

    # ---- overview ----
    def device_resources(self):
        return [{"device_id": "demo-1", "cpu_usage": 7, "memory_usage": 251000, "memory_total": 415436}]

    def device_speeds(self):
        return {"device_list_speed": [{"device_id": "demo-1", "down_speed": 1840, "up_speed": 212},
                                      {"device_id": "demo-2", "down_speed": 96, "up_speed": 14}]}

    def lan_ip(self):
        return {"lan_ip": {"ip": "192.168.68.1", "mask": "255.255.252.0"}, "dns_server_ip": ["1.1.1.1", "9.9.9.9"],
                "wan_ip": ["203.0.113.24"]}

    def ipv4(self):
        return {"wan": {"dial_type": "dynamic_ip", "ip_info": {"ip": "203.0.113.24", "gateway": "203.0.113.1",
                                                               "mask": "255.255.255.0"}}}

    def dhcp(self):
        return {"start_ip": "192.168.68.100", "end_ip": "192.168.71.249", "gateway": "192.168.68.1",
                "dns1": "1.1.1.1", "dns2": "9.9.9.9", "ip_amount_in_use": 10}

    def fw_latest(self):
        return [{"device_model": "X60", "name": _b64("X60"), "version": _b64("1.7.1 Build 25080612 Rel. 70421"),
                 "need_to_upgrade": False, "release_note": "", "release_date": ""}]

    def fw_progress(self):
        return {"status": "idle", "download_progress": 0}

    def messages(self):
        now = int(time.time())
        return [{"type": "new_report_weekly", "timestamp": now - 86400, "content": {"date_range": "20261012-20261018"}},
                {"type": "new_report_v2", "timestamp": now - 30 * 86400, "content": {"year": "2026", "month": "9"}}]

    # ---- clients ----
    def client_list_speeds(self):
        return {c["mac"]: ((n * 37) % 900, (n * 11) % 120) for n, c in enumerate(self._clients) if c["online"]}

    def blocked_clients(self):
        return {"client_list": copy.deepcopy(self._blocked), "max_count": 128}

    def block_clients(self, clients):
        for c in clients:
            self._blocked.append({"mac": c["mac"], "name": _b64(c.get("name", "")), "client_type": c.get("client_type", "other")})
        return {"error_code": 0}

    def unblock_clients(self, macs):
        macs = {macs} if isinstance(macs, str) else set(macs)
        self._blocked = [b for b in self._blocked if b["mac"] not in macs]
        return {"error_code": 0}

    def set_client_priority(self, client, enable, minutes=-1):
        if not self._settings["qos"]["has_set_bandwidth"]:
            raise DecoError(-3501, "bandwidth unset")
        return {"error_code": 0}

    def modify_port_forward(self, port_forwarding_id, external_port, internal_ip, internal_port=None,
                            protocol="tcp", name="", service_type="custom"):
        for r in self._pf:
            if r["port_forwarding_id"] == str(port_forwarding_id):
                r.update(service_name=name, protocol=protocol, external_port=str(external_port), internal_ip=internal_ip,
                         internal_port=str(internal_port if internal_port is not None else external_port))
        return {"error_code": 0}

    # ---- routes, nodes ----
    def static_routes(self):
        return {"route_static_list": copy.deepcopy(self._routes), "max_count": 32, "interface": ["lan", "wan"]}

    def add_static_route(self, ip, mask, gateway, interface="lan", name="", enable=True):
        self._routes.append({"id": str(next(self._ids)), "ip": ip, "mask": mask, "gateway": gateway,
                             "interface": interface, "name": _b64(name), "enable": enable})
        return {"error_code": 0}

    def modify_static_route(self, route_id, ip, mask, gateway, interface="lan", name="", enable=True):
        for r in self._routes:
            if r["id"] == str(route_id):
                r.update(ip=ip, mask=mask, gateway=gateway, interface=interface, name=_b64(name), enable=enable)
        return {"error_code": 0}

    def remove_static_routes(self, route_ids):
        ids = {str(route_ids)} if isinstance(route_ids, (str, int)) else {str(i) for i in route_ids}
        self._routes = [r for r in self._routes if r["id"] not in ids]
        return {"error_code": 0}

    def set_device_nickname(self, device_id, custom_nickname, nickname="custom"):
        for n in _DEVICES:
            if n["device_id"] == device_id:
                n.update(nickname="custom", custom_nickname=_b64(custom_nickname))
        return {"error_code": 0}

    def reboot_devices(self, device_ids):
        return {"error_code": 0}

    # ---- settings ----
    def _set(self, name, changes):
        self._settings[name].update(changes)
        return {"error_code": 0}

    def upnp(self): return copy.deepcopy(self._settings["upnp"])
    def sip_alg(self): return copy.deepcopy(self._settings["sip_alg"])
    def client_isolation(self): return copy.deepcopy(self._settings["client_isolation"])
    def monthly_report(self): return copy.deepcopy(self._settings["monthly_report"])
    def auto_led(self): return copy.deepcopy(self._settings["led"])
    def reboot_schedule(self): return copy.deepcopy(self._settings["reboot_schedule"])
    def fw_auto_update(self): return copy.deepcopy(self._settings["fw_auto_update"])
    def wifi_schedule(self): return copy.deepcopy(self._settings["wifi_schedule"])
    def eco_mode(self): return copy.deepcopy(self._settings["eco_mode"])
    def antivirus_settings(self): return copy.deepcopy(self._settings["homeshield"])
    def qos_bandwidth(self): return copy.deepcopy(self._settings["qos"])
    def system_time(self): return {"tz_region": "America/New_York", "time": int(time.time()), "timezone": -300}
    def ddns(self): return {"ddns_enable": False, "ddns_info": {"connection_status": "success"}}
    def allowed_websites(self): return {"website_list": list(self._sites), "max_count": 256}

    def set_upnp(self, enable): return self._set("upnp", {"enable": enable})
    def set_sip_alg(self, enable): return self._set("sip_alg", {"enable": enable})
    def set_client_isolation(self, enable): return self._set("client_isolation", {"enable": enable})
    def set_monthly_report(self, enable): return self._set("monthly_report", {"enable": enable})
    def set_auto_led(self, **ch): return self._set("led", ch)
    def set_reboot_schedule(self, **ch): return self._set("reboot_schedule", ch)
    def set_wifi_schedule(self, **ch): return self._set("wifi_schedule", ch)
    def set_eco_mode(self, **ch): return self._set("eco_mode", ch)
    def set_antivirus_settings(self, **ch): return self._set("homeshield", ch)
    def set_qos_bandwidth(self, **ch): return self._set("qos", ch)

    def set_fw_auto_update(self, enable=None, time_begin=None, time_end=None):
        ch = {k: v for k, v in (("enable_auto_update", enable), ("time_begin", time_begin), ("time_end", time_end)) if v is not None}
        return self._set("fw_auto_update", ch)

    def allow_website(self, domain):
        self._sites.append(domain)
        return {"error_code": 0}

    def disallow_website(self, domain):
        self._sites = [d for d in self._sites if d != domain]
        return {"error_code": 0}

    # ---- Wi-Fi (ssid/password base64, as on a real Deco) ----
    def wireless(self):
        return copy.deepcopy(self._wifi)

    def set_wireless(self, **changes):
        self._wifi.update(copy.deepcopy(changes))
        return {"error_code": 0}

    def write_wireless(self, partial):
        for band, nets in partial.items():
            for net, fields in nets.items():
                self._wifi.setdefault(band, {}).setdefault(net, {}).update(fields)
        return {"error_code": 0}
