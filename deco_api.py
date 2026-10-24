#!/usr/bin/env python3
"""deco_api — strictly-local TP-Link Deco management client (no cloud, no NOC).

A reverse-engineered local API for a TP-Link Deco mesh. Talks directly to the
master node on the LAN; never touches the TP-Link cloud.

Transport stack (all reverse-engineered & verified on a Deco X60, firmware 1.7.1):
    TDP discovery (UDP 20002)
      -> dropbear SSH :20001   user = hex(SHA1(lower(email))), pass = account password
        -> direct-tcpip tunnel to the device loopback 127.0.0.1:20002 (TMP daemon)
          -> TMP session: PUSH opcode 0x0001 to alloc a connection-bound token
            -> app opcodes (plaintext JSON; SSH provides confidentiality)

Wire framing (all BIG-ENDIAN):
    Outer TMP data frame (16B): verMaj=1,verMin=1,type(5=DATA,6=err),code,
      payloadLen(u16),subtype,status,seq(u32),CRC32(whole frame; slot preseeded 0x5A6B7C8D).
    Inner v2 packet (base{1,2}+18B): opCode(u16),type(2=PUSH,3=PUSH_ACK,4=PULL,5=PULL_ACK),
      status,txnId(u16),CRC32(json,u32),totalLen(u32),offset(u32), then JSON.

Quick start:
    from deco_api import DecoLocal
    with DecoLocal.from_env_or_file() as deco:
        print(deco.port_forwards())          # high-level, decoded
        print(deco.reservations())
        print(deco.read("WIRELESS_GET"))     # any opcode by name -> result dict
        print(deco.call(0x4012))             # raw full response incl. error_code

Credentials live in ~/.tplink_cloud (line 1 = TP-Link email, line 2 = password), or
$TPLINK_USER/$TPLINK_PASS via from_env_or_file(); the account password is also the
local Deco owner password. Never committed.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import socket
import struct
from pathlib import Path

import paramiko

from deco_log import get_logger

log = get_logger("deco.api")

__all__ = ["DecoLocal", "DecoError", "TmpError", "b64decode", "OPS", "log"]

# ---- protocol constants ----
MAGIC = 0x5A6B7C8D          # CRC32 seed in both TDP and TMP frames
CHUNK = 8156                # max JSON bytes per TMP chunk
PUSH, PUSH_ACK, PULL, PULL_ACK = 2, 3, 4, 5
TDP_PORT = 20002
SSH_USER = lambda email: hashlib.sha1(email.strip().lower().encode()).hexdigest()
TMP_DAEMON = ("127.0.0.1", 20002)   # on the DEVICE loopback, reached via the tunnel
TOKEN_ALLOC_OP = 0x0001
NEGOTIATE_OP = 0x4001

# ---- opcode name registry (extracted from the app's r.java) ----
_OPMAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deco-opcodes.json")
OPS: dict[str, int] = {}        # short name (no TMP_APPV2_OP_ prefix) -> opcode
OPS_BY_VALUE: dict[int, str] = {}
if os.path.exists(_OPMAP_PATH):
    for _k, _v in json.load(open(_OPMAP_PATH)).items():
        _short = _k[len("TMP_APPV2_OP_"):]
        OPS[_short] = _v
        OPS_BY_VALUE[_v] = _short
_OPS = OPS   # backwards-compatible alias


def resolve_op(op) -> int:
    """Accept an int opcode or a name like 'PORT_FORWARDING_LIST_GET'."""
    if isinstance(op, int):
        return op
    return OPS[op.upper().removeprefix("TMP_APPV2_OP_")]


def b64decode(s: str) -> str:
    """Decode a TP-Link base64 field (client/service names) to text, best-effort."""
    if not isinstance(s, str):
        return s
    try:
        return base64.b64decode(s).decode("utf-8")
    except Exception:
        return s


def _crc32(b: bytes) -> int:
    return binascii.crc32(b) & 0xFFFFFFFF


# ---- exceptions ----
class TmpError(RuntimeError):
    """TMP protocol-layer failure (status byte != 0 in a PUSH_ACK / PULL_ACK)."""

    STATUS = {10: "TOKEN_EXPIRED", 11: "TOKEN_ALLOC", 12: "BUSINESS_FAILED"}

    def __init__(self, status, msg=""):
        super().__init__(msg or f"TMP status {status} ({self.STATUS.get(status, '?')})")
        self.status = status


class DecoError(RuntimeError):
    """Application-layer failure (JSON error_code != 0)."""

    def __init__(self, error_code, msg="", opcode=None):
        super().__init__(f"error_code={error_code} {msg}".strip()
                         + (f" (op 0x{opcode:04x})" if opcode else ""))
        self.error_code = error_code
        self.msg = msg


# ---- frame builders ----
def _tmp_frame(payload: bytes, seq: int) -> bytes:
    hdr = struct.pack(">BBBBHBBI", 1, 1, 5, 0, len(payload), 0, 0, seq)
    frame = bytearray(hdr + struct.pack(">I", MAGIC) + payload)
    frame[12:16] = struct.pack(">I", _crc32(bytes(frame)))
    return bytes(frame)


def _v2(opcode: int, ptype: int, txnid: int, body: bytes = b"", offset: int = 0) -> bytes:
    crc = _crc32(body) if body else 0
    return (struct.pack(">BB", 1, 2)
            + struct.pack(">HBBHIII", opcode, ptype, 0, txnid, crc, len(body), offset)
            + body)


def _v2_parse(pkt: bytes) -> dict:
    return dict(
        opcode=struct.unpack(">H", pkt[2:4])[0], type=pkt[4], status=pkt[5],
        txnid=struct.unpack(">H", pkt[6:8])[0],
        crc=struct.unpack(">I", pkt[8:12])[0],
        total=struct.unpack(">I", pkt[12:16])[0],
        offset=struct.unpack(">I", pkt[16:20])[0], data=pkt[20:])


class DecoLocal:
    """A live local connection to a Deco mesh master.

    Construct with credentials, then ``connect()`` (or use as a context manager).
    Low-level:  ``request(op, body)`` -> bytes,  ``call(op, body)`` -> full dict,
                ``read(op, body)`` -> the ``result`` sub-dict (raises DecoError on error).
    High-level: the named per-feature methods below (``clients()``, ``port_forwards()``, ...).
    """

    def __init__(self, email: str, password: str, host: str | None = None, timeout: float = 10.0):
        self.email = email.strip()
        self.password = password
        self.host = host
        self.timeout = timeout
        self.master: dict | None = None
        self.nodes: list[dict] = []
        self._ssh = None
        self._ch = None
        self._seq = 1
        self._txn = 0
        self._token: bytes | None = None

    @classmethod
    def from_creds_file(cls, path: str = "~/.tplink_cloud", **kw) -> "DecoLocal":
        lines = Path(path).expanduser().read_text().splitlines()
        return cls(lines[0].strip(), lines[1].strip(), **kw)

    @classmethod
    def from_env_or_file(cls, path: str = "~/.tplink_cloud", **kw) -> "DecoLocal":
        """Credentials from $TPLINK_USER/$TPLINK_PASS when both are set, else the file."""
        user, pw = os.environ.get("TPLINK_USER"), os.environ.get("TPLINK_PASS")
        if user and pw:
            return cls(user, pw, **kw)
        return cls.from_creds_file(path, **kw)

    @property
    def username(self) -> str:
        """The dropbear SSH username = hex(SHA1(lowercased account email))."""
        return SSH_USER(self.email)

    # ---------- discovery ----------
    @staticmethod
    def discover(timeout: float = 3.0) -> list[dict]:
        """Broadcast a TDP probe; return each mesh node's advertised info dict
        ({ip, role, device_model, tmp_port, owner=md5(email), ...})."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(timeout)
        body = struct.pack(">BBHHBBI", 2, 0, 1, 0, 0, 0, 0x11223344)
        pkt = bytearray(body + struct.pack(">I", MAGIC))
        pkt[12:16] = struct.pack(">I", _crc32(bytes(pkt)))
        s.sendto(bytes(pkt), ("255.255.255.255", TDP_PORT))
        nodes: dict[str, dict] = {}
        while True:
            try:
                data, _ = s.recvfrom(8192)
            except socket.timeout:
                break
            try:
                r = json.loads(data[16:].decode())["result"]
                nodes[r["ip"]] = r
            except Exception:
                pass
        s.close()
        return list(nodes.values())

    # ---------- connection lifecycle ----------
    def connect(self) -> "DecoLocal":
        log.debug("TDP discovery (broadcast udp/%d)", TDP_PORT)
        self.nodes = self.discover()
        self.master = next((n for n in self.nodes if n.get("role") == "master"), None)
        if not self.master:
            log.fail("no Deco master found via TDP (%d nodes replied)", len(self.nodes))
            raise RuntimeError("no Deco master found via TDP (is the LAN reachable?)")
        host = self.host or self.master["ip"]
        port = self.master["tmp_port"][0]
        log.debug("SSH %s@%s:%d", self.username[:10] + "…", host, port)
        self._ssh = paramiko.SSHClient()
        self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self._ssh.connect(host, port=port, username=self.username, password=self.password,
                              allow_agent=False, look_for_keys=False, timeout=self.timeout,
                              banner_timeout=self.timeout, auth_timeout=self.timeout)
        except paramiko.AuthenticationException:
            log.fail("SSH auth rejected — check the TP-Link account password")
            raise
        self._open_channel()
        log.info("connected to %s @ %s (%d nodes)",
                 self.master.get("device_model", "Deco"), host, len(self.nodes))
        return self

    def _open_channel(self):
        ch = self._ssh.get_transport().open_channel("direct-tcpip", TMP_DAEMON,
                                                    ("127.0.0.1", 0), timeout=self.timeout)
        ch.settimeout(self.timeout)
        self._ch = ch
        self._seq = 1
        self._txn = 0
        self._token = self.request(TOKEN_ALLOC_OP, b"")   # bind a session to this connection
        log.debug("TMP channel open; session token allocated")

    def reconnect_channel(self):
        """Drop and re-open the TMP channel (e.g. after a desync/timeout)."""
        log.warn("reconnecting TMP channel")
        try:
            self._ch and self._ch.close()
        except Exception:
            pass
        self._open_channel()

    def close(self):
        for x in (self._ch, self._ssh):
            try:
                x and x.close()
            except Exception:
                pass
        self._ch = self._ssh = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc):
        self.close()

    # ---------- low-level I/O ----------
    def _recv_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            d = self._ch.recv(n - len(buf))
            if not d:
                raise EOFError("channel closed mid-frame")
            buf += d
        return buf

    def _read_frame(self) -> dict:
        head = self._recv_exact(4)
        if head[0] != 1 or head[1] != 1:
            raise ValueError(f"bad TMP version: {head.hex()}")
        if head[2] != 5:                       # not a DATA frame (e.g. hello-ack, error)
            return {"type": head[2], "code": head[3], "payload": b""}
        rest = self._recv_exact(12)
        plen = struct.unpack(">H", rest[0:2])[0]
        return {"type": 5, "code": head[3],
                "payload": self._recv_exact(plen) if plen else b""}

    def _send_v2(self, pkt: bytes):
        self._ch.sendall(_tmp_frame(pkt, self._seq))
        self._seq += 1

    def _next_v2(self) -> dict:
        while True:
            f = self._read_frame()
            if f["type"] == 6:
                raise TmpError(-1, f"TMP error frame code={f['code']}")
            if f["type"] == 5 and f["payload"]:
                return _v2_parse(f["payload"])

    # ---------- request primitives ----------
    def request(self, op, body=b"") -> bytes:
        """Send one opcode and return the raw response bytes (usually JSON).

        ``body`` may be bytes, a str, or a dict/list (JSON-encoded automatically).
        Raises TmpError on a protocol-layer rejection (e.g. status 12 = unimplemented).
        """
        opcode = resolve_op(op)
        if isinstance(body, (dict, list)):
            body = json.dumps(body, separators=(",", ":")).encode()
        elif isinstance(body, str):
            body = body.encode()
        txn = self._txn
        self._txn = (self._txn + 1) & 0xFFFF
        log.debug("-> op 0x%04x txn=%d body=%dB", opcode, txn, len(body))
        self._send_v2(_v2(opcode, PUSH, txn, body, 0))
        out = bytearray()
        total = crc = None
        sent_pull = False
        while True:
            r = self._next_v2()
            if r["type"] == PUSH_ACK:
                if r["status"] != 0:
                    raise TmpError(r["status"], f"PUSH rejected (op 0x{opcode:04x})")
                if not sent_pull:
                    self._send_v2(_v2(opcode, PULL, txn, b"", 0))
                    sent_pull = True
            elif r["type"] == PULL_ACK:
                if r["status"] != 0:
                    raise TmpError(r["status"], f"PULL_ACK rejected (op 0x{opcode:04x})")
                if total is None:
                    total, crc = r["total"], r["crc"]
                out[r["offset"]:r["offset"] + len(r["data"])] = r["data"]
                if not total or len(out) >= total:
                    break
                self._send_v2(_v2(opcode, PULL, txn, b"", len(out)))
            else:
                raise TmpError(r["status"], f"unexpected v2 type {r['type']}")
        data = bytes(out[:total or 0])
        if total and crc and _crc32(data) != crc:
            raise TmpError(-2, "response CRC mismatch")
        log.debug("<- op 0x%04x %dB", opcode, len(data))
        return data

    def call(self, op, body=b"") -> dict | None:
        """Send an opcode and return the full parsed JSON ({result, error_code})."""
        raw = self.request(op, body)
        return json.loads(raw.decode("utf-8", "replace")) if raw else None

    get = call   # backwards-compatible alias

    def read(self, op, body=b"") -> dict | list | None:
        """Send a read opcode and return the unwrapped ``result``.

        Raises DecoError if the device reports a non-zero error_code.
        """
        obj = self.call(op, body)
        if obj is None:
            return None
        ec = obj.get("error_code")
        if ec not in (0, None):
            log.error("op 0x%04x rejected: %s (error_code=%s)",
                      resolve_op(op), obj.get("msg", ""), ec)
            raise DecoError(ec, obj.get("msg", ""), resolve_op(op))
        return obj.get("result", obj)

    def write(self, op, params=None, operation=None) -> dict | None:
        """Send a WRITE opcode. Writes require the luci-style envelope
        ``{"operation": <op>, "params": <params>}`` (reads do not). Returns the
        ``result`` (often {} or a new id); raises DecoError on a non-zero error_code.
        """
        body: dict = {"params": params if params is not None else {}}
        if operation:
            body["operation"] = operation
        log.info("write op 0x%04x operation=%s", resolve_op(op), operation or "(implied)")
        return self.read(op, body)

    def negotiate(self) -> dict:
        """Run COMP_NEGOTIATE; returns working_status, operation_mode, and the
        device's negotiated component_list."""
        un = hashlib.sha256(self.email.encode()).hexdigest()
        return self.read(NEGOTIATE_OP, {"role": "ROLE_OWNER", "username": un})

    # ================= high-level reads (the local API surface) =================
    # Each returns the device's `result` payload; list helpers decode base64 names.

    # --- overview ---
    def operation_mode(self):   return self.read("OPERATION_MODE_GET")
    def location(self):         return self.read("LOCATION_GET")
    def system_time(self):      return self.read("SYSTEM_TIME_GET")
    def internet(self):         return self.read("INTERNET_GET")
    def speedtest_result(self): return self.read("SPEEDTEST_INFO_GET")
    def monthly_report(self):   return self.read("MONTHLY_REPORT_MGR_GET")

    # --- topology ---
    def devices(self):
        """Mesh nodes (the Deco units). Returns the device_list."""
        return self.read("DEVICE_LIST_GET").get("device_list", [])
    def device_speeds(self):    return self.read("DEVICE_LIST_SPEED_GET")
    def device_signal(self):    return self.read("DEVICE_SIGNAL_LEVEL_LIST_GET")

    # --- clients ---
    def clients(self, decode_names=True):
        """Connected clients. Decodes base64 `name` fields by default."""
        cl = self.read("CLIENT_LIST_GET").get("client_list", [])
        if decode_names:
            for c in cl:
                if "name" in c:
                    c["name"] = b64decode(c["name"])
        return cl
    def client_speeds(self):    return self.read("CLIENT_LIST_SPEED_GET")
    def client_isolation(self): return self.read("CLIENT_ISOLATION_GET")
    def iot_clients(self):      return self.read("IOT_CLIENT_LIST_GET")
    def iot_profiles(self):     return self.read("IOT_PRODUCT_PROFILE_GET")

    # --- wireless ---
    def wireless(self):         return self.read("WIRELESS_GET")
    def wifi_schedule(self):    return self.read("WIFI_SCHEDULE_SETTINGS_GET")
    def beamforming(self):      return self.read("BEAMFORMING_GET")
    def mac_clone(self):        return self.read("MAC_CLONE_GET")
    def mac_clone_clients(self): return self.read("MAC_CLONE_CLIENT_LIST_GET")

    # --- network ---
    def ipv4(self):             return self.read("IPV4_GET")
    def ipv6(self):             return self.read("IPV6_GET")
    def ipv6_firewall(self):    return self.read("IPV6_FIREWALL_LIST_GET")
    def wan_isp(self):          return self.read("WAN_ISP_GET")
    def smart_dhcp(self):       return self.read("SMART_DHCP_GET")
    def iptv(self):             return self.read("IPTV_GET")
    def sip_alg(self):          return self.read("SIP_ALG_GET")

    # --- NAT / forwarding ---
    def port_forwards(self, decode_names=True):
        """Port-forwarding rules. Decodes base64 `service_name` by default."""
        pf = self.read("PORT_FORWARDING_LIST_GET").get("port_forwarding_list", [])
        if decode_names:
            for r in pf:
                if "service_name" in r:
                    r["service_name"] = b64decode(r["service_name"])
        return pf

    def reservations(self):
        """DHCP address reservations (mac -> ip)."""
        return self.read("IP_RESERVATION_LIST_GET").get("reservation_list", [])

    # --- QoS ---
    def qos_mode(self):         return self.read("QOS_MODE_GET")
    def dpi_qos(self):          return self.read("DPI_QOS_INFO_GET")
    def bandwidth(self):        return self.read("BANDWIDTH_SWITCH_INFO_GET")

    # --- security ---
    def security_info(self):    return self.read("SECURITY_INFO_GET")
    def security_history(self): return self.read("SECURITY_HISTORY_GET")
    def antivirus(self):        return self.read("AVIRA_ANTIVIRUS_GET")
    def antivirus_settings(self): return self.read("AVIRA_ANTIVIRUS_SETTINGS_GET")

    # --- vpn ---
    def wireguard(self):        return self.read("WIREGUARDVPN_ACCOUNT_DEFAULT_GET")
    def openvpn_cert(self):     return self.read("OPENVPN_CERT_GET")

    # --- system ---
    def reboot_schedule(self):  return self.read("REBOOT_SCHEDULE_GET")
    def fw_auto_update(self):   return self.read("FW_AUTO_UPDATE_GET")
    def eco_mode(self):         return self.read("ECO_MODE_SETTINGS_GET")
    def managers(self):         return self.read("MANAGER_PERMISSION_GET")
    def automation_history(self): return self.read("AUTOMATION_HISTORY_GET")

    # --- tools ---
    def speedtest_servers(self): return self.read("SPEEDTEST_SERVER_LIST_GET")

    # ================= writes (verified) =================
    # All writes use the {"operation","params"} envelope via self.write().

    def add_reservation(self, ip: str, mac: str):
        """Reserve `ip` for `mac` (MAC like 'AA-BB-CC-DD-EE-FF'). Within DHCP pool."""
        return self.write("IP_RESERVATION_LIST_ADD",
                          {"reservation_list": [{"ip": ip, "mac": mac}]}, "add")

    def remove_reservations(self, macs):
        """Remove reservation(s) by MAC. `macs` is a str or list of MAC strings."""
        if isinstance(macs, str):
            macs = [macs]
        return self.write("IP_RESERVATION_LIST_REMOVE",
                          {"reservation_list": list(macs)}, "remove")

    def modify_reservation(self, original_ip, original_mac, ip, mac):
        """Change an existing reservation (identified by original_ip/original_mac)."""
        return self.write("IP_RESERVATION_MODIFY",
                          {"original_ip": original_ip, "original_mac": original_mac,
                           "ip": ip, "mac": mac}, "edit")

    def add_port_forward(self, external_port, internal_ip, internal_port=None,
                         protocol="tcp", name="", service_type="custom"):
        """Add a port-forwarding rule. protocol in {tcp,udp,all}. Returns the new
        port_forwarding_id. `name` is plain text (base64-encoded on the wire)."""
        params = {"external_port": str(external_port), "internal_ip": internal_ip,
                  "internal_port": str(internal_port if internal_port is not None else external_port),
                  "protocol": protocol, "service_type": service_type,
                  "service_name": base64.b64encode(name.encode()).decode()}
        res = self.write("PORT_FORWARDING_ADD", params, "add")
        return (res or {}).get("port_forwarding_id")

    def delete_port_forward(self, port_forwarding_id):
        """Delete a port-forwarding rule by its id (str, from port_forwards())."""
        return self.write("PORT_FORWARDING_DELETE",
                          {"port_forwarding_id": str(port_forwarding_id)}, "delete")

    # ---- settings: read-modify-write ----
    def _update(self, get_op, set_op, changes: dict):
        """Read the current settings, merge `changes`, and write back (operation
        'set'). Preserving unmodified fields is the safe way to change one flag."""
        cur = self.read(get_op)
        if not isinstance(cur, dict):
            cur = {}
        cur.update(changes)
        return self.write(set_op, cur, "set")

    # --- verified-safe setters (no radio/WAN/DHCP disruption) ---
    def set_sip_alg(self, enable: bool):
        return self._update("SIP_ALG_GET", "SIP_ALG_SET", {"enable": bool(enable)})

    def set_monthly_report(self, enable: bool):
        return self._update("MONTHLY_REPORT_MGR_GET", "MONTHLY_REPORT_MGR_SET",
                            {"enable": bool(enable)})

    def set_client_isolation(self, enable: bool):
        return self._update("CLIENT_ISOLATION_GET", "CLIENT_ISOLATION_SET",
                            {"enable": bool(enable)})

    def set_reboot_schedule(self, **changes):
        """e.g. set_reboot_schedule(enable=True, setting={...}). Merges into current."""
        return self._update("REBOOT_SCHEDULE_GET", "REBOOT_SCHEDULE_SET", changes)

    def set_system_time(self, **changes):
        """e.g. set_system_time(timezone='UTC-05:00', tz_region='America/New_York')."""
        return self._update("SYSTEM_TIME_GET", "SYSTEM_TIME_SET", changes)

    def set_eco_mode(self, **changes):
        """e.g. set_eco_mode(enable=True, power_mode=...)."""
        return self._update("ECO_MODE_SETTINGS_GET", "ECO_MODE_SETTINGS_SET", changes)

    def set_wifi_schedule(self, **changes):
        """e.g. set_wifi_schedule(enable=True, time_begin=..., time_end=...)."""
        return self._update("WIFI_SCHEDULE_SETTINGS_GET", "WIFI_SCHEDULE_SETTINGS_SET", changes)

    def set_antivirus_settings(self, **changes):
        """e.g. set_antivirus_settings(web_protection=True, iot_protection=True)."""
        return self._update("AVIRA_ANTIVIRUS_SETTINGS_GET", "AVIRA_ANTIVIRUS_SETTINGS_SET", changes)

    # --- antivirus allowed-website list (verified) ---
    def allow_website(self, domain: str):
        return self.write("ANTIVIRUS_ALLOWED_WEBSITES_ADD", {"website_list": [domain]}, "add")

    def disallow_website(self, domain: str):
        return self.write("ANTIVIRUS_ALLOWED_WEBSITES_REMOVE", {"website_list": [domain]}, "remove")

    # --- radio/DHCP-adjacent toggles (re-applies that subsystem; brief blip possible) ---
    def set_beamforming(self, enable: bool):
        "May briefly re-apply the radios."
        return self._update("BEAMFORMING_GET", "BEAMFORMING_SET", {"enable": bool(enable)})

    def set_smart_dhcp(self, enable: bool):
        "Re-applies DHCP."
        return self._update("SMART_DHCP_GET", "SMART_DHCP_SET", {"enable": bool(enable)})

    # --- DISRUPTIVE setters (implemented, NOT auto-tested — see docs/WRITES.md) ---
    # These re-apply core network/radio config and can drop clients or reboot the
    # mesh. Bodies merge `changes` into the matching *_GET. Use deliberately.
    def set_wireless(self, **changes):
        "DISRUPTIVE: re-applies Wi-Fi (SSID/passphrase/channel) — clients drop briefly."
        return self._update("WIRELESS_GET", "WIRELESS_SET", changes)

    def set_qos_mode(self, **changes):
        "Re-applies QoS."
        return self._update("QOS_MODE_GET", "QOS_MODE_SET", changes)

    def set_ipv6(self, **changes):
        "DISRUPTIVE: re-applies IPv6."
        return self._update("IPV6_GET", "IPV6_SET", changes)

    def set_ipv4(self, **changes):
        "DISRUPTIVE: re-applies WAN/LAN IPv4 — can drop the internet connection."
        return self._update("IPV4_GET", "IPV4_SET", changes)

    def set_mac_clone(self, **changes):
        "DISRUPTIVE: changes the WAN MAC — bounces the internet connection."
        return self._update("MAC_CLONE_GET", "MAC_CLONE_SET", changes)

    def set_operation_mode(self, **changes):
        "VERY DISRUPTIVE: switching Router/AP mode REBOOTS the whole mesh."
        return self._update("OPERATION_MODE_GET", "OPERATION_MODE_SET", changes)

    # --- more verified writes ---
    def set_fw_auto_update(self, enable=None, time_begin=None, time_end=None):
        """Firmware auto-update window. The GET returns time_* as strings but SET
        wants ints — handled here (the reason a raw write-back failed)."""
        cur = self.read("FW_AUTO_UPDATE_GET")
        body = {
            "enable_auto_update": bool(cur["enable_auto_update"] if enable is None else enable),
            "time_begin": int(cur["time_begin"] if time_begin is None else time_begin),
            "time_end": int(cur["time_end"] if time_end is None else time_end),
        }
        return self.write("FW_AUTO_UPDATE_SET", body, "set")

    def set_client(self, mac: str, **changes):
        """Update a client entry (CLIENT_LIST_SET) — e.g. name, enable_priority,
        enable_isolation, custom_client_type. `name` is base64-encoded on the wire
        (pass plain text here). Sends only mac + the changed fields."""
        if "name" in changes and isinstance(changes["name"], str):
            changes["name"] = base64.b64encode(changes["name"].encode()).decode()
        entry = {"mac": mac, **changes}
        return self.write("CLIENT_LIST_SET", {"client_list": [entry]}, "set")

    def set_device_nickname(self, device_id: str, custom_nickname: str, nickname="custom"):
        """Rename a Deco node. `nickname` is the preset type (or 'custom' with
        `custom_nickname` as free text)."""
        return self.write("NICKNAME_SET", {"device_id": device_id, "nickname": nickname,
                                           "custom_nickname": custom_nickname}, "set")

    def add_ipv6_firewall(self, ip: str, port: int, protocol="tcp", name=""):
        """Add an IPv6 firewall (inbound-allow) rule. NOTE: rules can only be
        modified/removed while IPv6 is ENABLED — the device's handler errors on a
        nil IPv6 prefix otherwise. Returns the new rule list."""
        rule = {"ip": ip, "port": int(port), "protocol": protocol,
                "name": base64.b64encode(name.encode()).decode()}
        return self.write("IPV6_FIREWALL_LIST_ADD", {"firewall_list": [rule]}, "add")

    def remove_ipv6_firewall(self, rule_id: str):
        """Remove an IPv6 firewall rule by id (requires IPv6 enabled — see add)."""
        return self.write("IPV6_FIREWALL_LIST_REMOVE",
                          {"firewall_list": [{"id": str(rule_id)}]}, "remove")


def _main(argv):
    import sys
    d = DecoLocal.from_env_or_file().connect()
    info = d.master
    print(f"# {info['device_model']} @ {info['ip']}  "
          f"({len(d.nodes)} nodes, owner={info['owner'][:8]}…)")
    if not argv:
        argv = ["port_forwards", "reservations"]
    for a in argv:
        print(f"\n## {a}")
        try:
            if hasattr(d, a) and callable(getattr(d, a)):
                out = getattr(d, a)()
            else:                                # treat as an opcode name / hex
                op = int(a, 16) if a.lower().startswith("0x") else a
                out = d.read(op)
            print(json.dumps(out, indent=2)[:2000])
        except Exception as e:
            print(f"  {type(e).__name__}: {e}")
    d.close()


if __name__ == "__main__":
    import sys
    _main(sys.argv[1:])
