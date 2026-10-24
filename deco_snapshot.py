#!/usr/bin/env python3
"""Pull a FULL read snapshot of the Deco — every confirmed-working *_GET opcode —
and save the complete JSON. This is the 'get all the data' deliverable: the entire
locally-readable device state in one file. Categorized by management area.
"""
import json
import socket
import sys
import time

from deco_log import get_logger
log = get_logger("deco.snapshot")
from deco_api import DecoLocal, TmpError, _OPS

# The 48 confirmed-working reads, grouped by management area (from deco-read-map.json).
FEATURE_MAP = {
    "overview": ["OPERATION_MODE_GET", "LOCATION_GET", "SYSTEM_TIME_GET",
                 "INTERNET_GET", "SPEEDTEST_INFO_GET", "MONTHLY_REPORT_MGR_GET"],
    "topology": ["DEVICE_LIST_GET", "DEVICE_LIST_SPEED_GET", "DEVICE_SIGNAL_LEVEL_LIST_GET"],
    "clients": ["CLIENT_LIST_GET", "CLIENT_LIST_SPEED_GET", "CLIENT_SPEED_GET",
                "CLIENT_ISOLATION_GET", "IOT_CLIENT_LIST_GET", "IOT_PRODUCT_PROFILE_GET"],
    "wireless": ["WIRELESS_GET", "WIFI_SCHEDULE_SETTINGS_GET", "BEAMFORMING_GET",
                 "MAC_CLONE_GET", "MAC_CLONE_CLIENT_LIST_GET"],
    "network": ["IPV4_GET", "IPV6_GET", "IPV6_FIREWALL_LIST_GET", "WAN_ISP_GET",
                "SMART_DHCP_GET", "IPTV_GET", "SIP_ALG_GET"],
    "nat_forwarding": ["PORT_FORWARDING_LIST_GET", "IP_RESERVATION_LIST_GET"],
    "qos": ["QOS_MODE_GET", "DPI_QOS_INFO_GET", "BANDWIDTH_SWITCH_INFO_GET",
            "BANDWIDTH_SWITCH_RESULT_GET"],
    "security": ["SECURITY_INFO_GET", "SECURITY_HISTORY_GET", "AVIRA_ANTIVIRUS_GET",
                 "AVIRA_ANTIVIRUS_SETTINGS_GET", "ANTIVIRUS_ALLOWED_WEBSITES_GET",
                 "ANTIVIRUS_WHITE_LIST_GET"],
    "vpn": ["WIREGUARDVPN_ACCOUNT_DEFAULT_GET", "OPENVPN_CERT_GET"],
    "system": ["REBOOT_SCHEDULE_GET", "FW_AUTO_UPDATE_GET", "ECO_MODE_SETTINGS_GET",
               "MANAGER_PERMISSION_GET", "PRIVACY_POLICY_STATE_GET", "AUTOMATION_HISTORY_GET"],
    "tools": ["SPEEDTEST_SERVER_LIST_GET", "TSS_LOCAL_DISCOVER_DEVICES_GET"],
}


def main():
    d = DecoLocal.from_env_or_file(timeout=6)
    d.connect()
    snap = {"_device": {"model": d.master["device_model"], "ip": d.master["ip"],
                        "nodes": len(d.nodes)}, "_captured": int(time.time())}
    print(f"snapshot of {d.master['device_model']} @ {d.master['ip']} ({len(d.nodes)} nodes)\n")
    for area, ops in FEATURE_MAP.items():
        snap[area] = {}
        for name in ops:
            if name not in _OPS:
                continue
            try:
                obj = d.get(name, b"")
                snap[area][name] = obj
                r = obj.get("result") if isinstance(obj, dict) else obj
                n = (len(r) if isinstance(r, (list, dict)) else "?")
                print(f"  ✓ {area:14} {name:34} (result keys/len: {n})")
            except TmpError as e:
                snap[area][name] = {"_error": f"status {e.status}"}
                print(f"  · {area:14} {name:34} (status {e.status})")
                d.reconnect_channel()
            except (socket.timeout, EOFError, OSError) as e:
                snap[area][name] = {"_error": str(e)[:50]}
                print(f"  · {area:14} {name:34} (no response)")
                try:
                    d.reconnect_channel()
                except Exception:
                    d.connect()
    d.close()
    out = sys.argv[1] if len(sys.argv) > 1 else "deco-snapshot.json"
    json.dump(snap, open(out, "w"), indent=2)
    print(f"\nfull snapshot -> {out}")


if __name__ == "__main__":
    main()
