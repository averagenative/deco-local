"""deco_features — feature logic shared by the REST API (and web UI) and the desktop app.

Everything here takes a connected `deco_api.DecoLocal` (or `deco_demo.DemoDeco`) and returns
plain data, so the two front ends show and change the same things in the same way:
the overview, the settings registry, Wi-Fi changes, and decoded names.
"""

import base64

import deco_api


def _try(fn, default=None):
    """One optional read inside an aggregate: a DecoError there must not sink the rest."""
    try:
        return fn()
    except deco_api.DecoError:
        return default


def b64(text):
    return deco_api.b64decode(text) if text else text


def node_name(node):
    """Display name for a mesh node: the custom nickname (base64 on the wire) or the
    preset location key (e.g. living_room)."""
    if node.get("nickname") == "custom" and node.get("custom_nickname"):
        return deco_api.b64decode(node["custom_nickname"])
    return (node.get("nickname") or node.get("device_model") or "Deco").replace("_", " ").title()


def devices(d):
    """Mesh nodes, each with a decoded display `name`."""
    nodes = d.devices()
    for n in nodes:
        n["name"] = node_name(n)
    return nodes


def overview(d):
    """Internet, LAN and DHCP, firmware, and every node with CPU, memory, and throughput."""
    nodes = devices(d)
    res = {r["device_id"]: r for r in _try(d.device_resources, [])}
    spd = {r["device_id"]: r for r in _try(lambda: d.device_speeds().get("device_list_speed", []), [])}
    for n in nodes:
        r, sp = res.get(n.get("device_id"), {}), spd.get(n.get("device_id"), {})
        n["cpu_usage"], n["memory_usage"], n["memory_total"] = r.get("cpu_usage"), r.get("memory_usage"), r.get("memory_total")
        n["down_speed"], n["up_speed"] = sp.get("down_speed"), sp.get("up_speed")
    fw = [{"model": f.get("device_model"), "name": b64(f.get("name")), "version": b64(f.get("version")),
           "need_to_upgrade": f.get("need_to_upgrade"), "release_note": b64(f.get("release_note")),
           "release_date": f.get("release_date")} for f in _try(d.fw_latest, [])]
    return {"lan": _try(d.lan_ip, {}), "wan": (_try(d.ipv4, {}) or {}).get("wan", {}),
            "dhcp": _try(d.dhcp, {}), "nodes": nodes, "firmware": fw, "messages": _try(d.messages, [])}


def firmware(d):
    fw = [{"model": f.get("device_model"), "version": b64(f.get("version")),
           "need_to_upgrade": f.get("need_to_upgrade")} for f in d.fw_latest()]
    return {"firmware": fw, "progress": _try(d.fw_progress, {}), "auto_update": _try(d.fw_auto_update, {})}


def blocked_clients(d):
    b = d.blocked_clients()
    for c in b.get("client_list", []):
        c["name"] = b64(c.get("name"))
    return b


def block_macs(d, macs):
    """Block clients by MAC, sending the name and type the Deco already knows for each."""
    known = {c["mac"]: c for c in d.clients()}
    return d.block_clients([known.get(m, {"mac": m}) for m in macs])


def static_routes(d):
    r = d.static_routes()
    for x in r.get("route_static_list", []):
        x["name"] = b64(x.get("name"))
    return r


# Settings that apply without dropping Wi-Fi or the internet (QoS re-applies shaping, a brief
# blip): name -> (read, write(changes)). `changes` holds only the fields to change.
SETTINGS = {
    "upnp": (lambda d: d.upnp(), lambda d, ch: d.set_upnp(ch["enable"])),
    "sip_alg": (lambda d: d.sip_alg(), lambda d, ch: d.set_sip_alg(ch["enable"])),
    "client_isolation": (lambda d: d.client_isolation(), lambda d, ch: d.set_client_isolation(ch["enable"])),
    "monthly_report": (lambda d: d.monthly_report(), lambda d, ch: d.set_monthly_report(ch["enable"])),
    "led": (lambda d: d.auto_led(), lambda d, ch: d.set_auto_led(**ch)),
    "reboot_schedule": (lambda d: d.reboot_schedule(), lambda d, ch: d.set_reboot_schedule(**ch)),
    "fw_auto_update": (lambda d: d.fw_auto_update(),
                       lambda d, ch: d.set_fw_auto_update(ch.get("enable_auto_update"), ch.get("time_begin"), ch.get("time_end"))),
    "wifi_schedule": (lambda d: d.wifi_schedule(), lambda d, ch: d.set_wifi_schedule(**ch)),
    "eco_mode": (lambda d: d.eco_mode(), lambda d, ch: d.set_eco_mode(**ch)),
    "homeshield": (lambda d: d.antivirus_settings(), lambda d, ch: d.set_antivirus_settings(**ch)),
    # Limits are Kbps (1 Mbps = 1024). Writing them marks the bandwidth as set on the Deco.
    "qos": (lambda d: d.qos_bandwidth(), lambda d, ch: d.set_qos_bandwidth(**{**ch, "has_set_bandwidth": True})),
}


def read_settings(d):
    """Every setting in SETTINGS, plus read-only context (time zone, DDNS, DHCP)."""
    out = {}
    for name, (read, _write) in SETTINGS.items():
        try:
            out[name] = read(d)
        except deco_api.DecoError as e:
            out[name] = {"_error": str(e)}
    out["system_time"] = _try(d.system_time, {})
    out["ddns"] = _try(d.ddns, {})
    out["dhcp"] = _try(d.dhcp, {})
    return out


def write_setting(d, name, changes):
    """Apply `changes` to one setting and return its new value."""
    read, write = SETTINGS[name]
    write(d, changes)
    return read(d)


def wifi(d):
    """Main, guest, and IoT networks per band, with SSIDs and passwords decoded."""
    w = d.wireless()
    for band in w.values():
        for net in ("host", "guest", "iot"):
            if isinstance(band, dict) and isinstance(band.get(net), dict):
                for k in ("ssid", "password"):
                    band[net][k] = b64(band[net].get(k))
    return w


def set_wifi_network(d, network, ssid=None, password=None, enable=None, secured=None):
    """Change one network (host, guest, or iot) on every band at once; the Deco uses one
    name across bands. `secured` (guest/iot only) switches between WPA2 and open. Every
    Wi-Fi device reconnects, which takes 10 to 30 seconds."""
    if network not in ("host", "guest", "iot"):
        raise ValueError("network must be host, guest, or iot")
    if password and len(password) < 8:
        raise ValueError("Wi-Fi passwords need at least 8 characters")
    fields = {}
    if ssid is not None:
        fields["ssid"] = base64.b64encode(ssid.encode()).decode()
    if password is not None:
        fields["password"] = base64.b64encode(password.encode()).decode()
    if enable is not None:
        fields["enable"] = enable
    if secured is not None and network != "host":
        fields["encryption_mode"] = "wpa2" if secured else "none"
    if not fields:
        return {"error_code": 0}
    # Only the changed fields, on every band that has this network (as the Deco app does).
    partial = {band: {network: dict(fields)} for band, b in d.wireless().items()
               if isinstance(b, dict) and isinstance(b.get(network), dict)}
    return d.write_wireless(partial)
