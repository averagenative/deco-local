"""deco_rest — a fully callable REST API (and web UI) over the strictly-local Deco backend.

Wraps the proven `deco_api.DecoLocal` behind FastAPI, so the mesh can be driven from
any language, from the auto-generated Swagger UI, or from the bundled web UI.

Run:
    uvicorn deco_rest:app --host 127.0.0.1 --port 8777
    # or:  python deco_rest.py         (same thing, reads DECO_API_HOST/PORT)

Then open http://127.0.0.1:8777/       (web UI: clients, port forwarding, reservations, mesh)
     or   http://127.0.0.1:8777/docs   (Swagger UI)
     or   http://127.0.0.1:8777/openapi.json   (OpenAPI schema)

Notes:
- The Deco allows a SINGLE local session (dropbear auth-lockout on repeated failures),
  so this server keeps ONE DecoLocal session behind a lock and serializes every call.
  The session is released after $DECO_IDLE_SECONDS without a device call (default 300,
  0 = never) so the GTK app can take the device in between; the next call reconnects.
- Credentials come from $TPLINK_USER/$TPLINK_PASS, else $DECO_CREDS_PATH
  (default ~/.tplink_cloud: email line, password line), never from the API.
- DECO_DEMO=1 serves an in-memory demo mesh (deco_demo.py) instead of a real Deco.
- The API has no auth. $DECO_ALLOWED_HOSTS (comma list, default "*") pins the Host
  header, which defeats DNS rebinding, and writes from another origin are refused, so a
  web page a LAN visitor opens cannot drive the router through their browser. Network
  reach (LAN/VPN only) is the reverse proxy's job.
"""

import os
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

import deco_api
import deco_demo
import deco_features
import deco_log

log = deco_log.get_logger("rest")

# --- transport vs. application error classification (GTK-free) ---
_TRANSPORT_ERRORS = (OSError, EOFError, socket.error, deco_api.TmpError)
_AUTH_ERRORS = ()
try:
    import paramiko

    _TRANSPORT_ERRORS = _TRANSPORT_ERRORS + (paramiko.SSHException,)
    _AUTH_ERRORS = (paramiko.AuthenticationException,)
except Exception:  # pragma: no cover
    pass


class Session:
    """One lazily-connected DecoLocal session, serialized by a lock."""

    def __init__(self, creds_path="~/.tplink_cloud", idle_seconds=0):
        self.creds_path = creds_path
        self.idle_seconds = idle_seconds
        self._lock = threading.Lock()
        self._deco = None
        self._last_use = 0.0
        self.locked_out = False
        if idle_seconds > 0:
            threading.Thread(target=self._reaper, name="deco-idle", daemon=True).start()

    def _ensure(self):
        if self._deco is None:
            if self.locked_out:
                raise HTTPException(503, "Device auth locked out — wait and retry.")
            try:
                if DEMO:
                    self._deco = deco_demo.DemoDeco()
                else:
                    self._deco = deco_api.DecoLocal.from_env_or_file(self.creds_path).connect()
            except _AUTH_ERRORS as e:
                self.locked_out = True
                raise HTTPException(503, f"Auth rejected (lockout risk): {e}")
            except FileNotFoundError:
                raise HTTPException(503, f"No credentials at {self.creds_path}")
            except Exception as e:
                raise HTTPException(503, f"Cannot reach Deco: {e}")
        return self._deco

    def call(self, fn):
        """Run fn(deco) under the session lock, classifying failures to HTTP codes."""
        with self._lock:
            deco = self._ensure()
            try:
                return fn(deco)
            except _AUTH_ERRORS as e:
                self._close()
                self.locked_out = True
                raise HTTPException(503, f"Auth locked out: {e}")
            except _TRANSPORT_ERRORS as e:
                self._close()
                raise HTTPException(503, f"Session dropped: {e}")
            except deco_api.DecoError as e:
                raise HTTPException(502, f"Device rejected the request: {e}")
            except ValueError as e:
                raise HTTPException(422, str(e))
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(500, f"Backend error: {type(e).__name__}: {e}")
            finally:
                self._last_use = time.monotonic()

    def status(self):
        with self._lock:
            base = {"locked_out": self.locked_out, "idle_release_seconds": self.idle_seconds}
            if self._deco is None:
                return {"connected": False, **base}
            m = self._deco.master or {}
            return {
                "connected": True,
                **base,
                "idle_for": round(time.monotonic() - self._last_use),
                "model": m.get("device_model"),
                "ip": m.get("ip"),
                "nodes": len(self._deco.nodes or []),
            }

    def release(self):
        """Drop the device session now; the next call reconnects."""
        with self._lock:
            self._close()

    def reset(self):
        """Clear an auth lockout so the next call logs in once more."""
        with self._lock:
            self._close()
            self.locked_out = False

    def _reaper(self):
        while True:
            time.sleep(min(15, self.idle_seconds))
            with self._lock:
                if self._deco is not None and time.monotonic() - self._last_use > self.idle_seconds:
                    log.info("idle %ds, releasing the Deco session", self.idle_seconds)
                    self._close()

    def _close(self):
        if self._deco is not None:
            try:
                self._deco.close()
            except Exception:
                pass
            self._deco = None


DEMO = os.environ.get("DECO_DEMO", "") not in ("", "0", "false")
if DEMO:
    log.info("DECO_DEMO is set: serving an in-memory demo mesh, not a real Deco")

session = Session(
    os.environ.get("DECO_CREDS_PATH", "~/.tplink_cloud"),
    idle_seconds=int(os.environ.get("DECO_IDLE_SECONDS", "300")),
)

app = FastAPI(
    title="Deco Local API",
    version="1.3.1",
    description="Strictly-local REST control for a TP-Link Deco mesh (no cloud/NOC).",
)

_ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DECO_ALLOWED_HOSTS", "*").split(",") if h.strip()]
if _ALLOWED_HOSTS and _ALLOWED_HOSTS != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_ALLOWED_HOSTS)


@app.middleware("http")
async def refuse_cross_origin_writes(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        cross = request.headers.get("sec-fetch-site") == "cross-site"
        if cross or (origin and urlsplit(origin).netloc != request.headers.get("host")):
            return JSONResponse({"detail": "Cross-origin write refused."}, status_code=403)
    return await call_next(request)


# ---- request models (drive the OpenAPI schema) ----
class ClientRename(BaseModel):
    name: str = Field(..., description="New display name (plain text).")


class PortForwardCreate(BaseModel):
    external_port: int = Field(..., description="WAN-side port.")
    internal_ip: str = Field(..., description="LAN IP to forward to.")
    internal_port: int | None = Field(None, description="LAN port (defaults to external_port).")
    protocol: str = Field("tcp", description="tcp | udp | all")
    name: str = Field("", description="Service name (plain text).")


class ReservationCreate(BaseModel):
    ip: str = Field(..., description="Reserved IP (within the DHCP pool).")
    mac: str = Field(..., description="Client MAC, e.g. AA-BB-CC-DD-EE-FF.")


class ReservationModify(BaseModel):
    original_ip: str
    original_mac: str
    ip: str
    mac: str


# ---- routes ----
@app.get("/health", tags=["meta"])
def health():
    return {"ok": True}


@app.get("/status", tags=["meta"])
def get_status():
    return session.status()


@app.post("/session/release", tags=["meta"])
def release_session():
    """Drop the device session now (frees it for the GTK app). The next call reconnects."""
    session.release()
    return session.status()


@app.post("/session/reset", tags=["meta"])
def reset_session():
    """Clear an auth lockout; the next call tries to log in once."""
    session.reset()
    return session.status()


@app.get("/devices", tags=["mesh"])
def list_devices():
    """Mesh nodes (the Deco units), each with a decoded display `name`."""
    return session.call(deco_features.devices)


@app.get("/clients", tags=["clients"])
def list_clients():
    """Connected clients (base64 names decoded)."""
    return session.call(lambda d: d.clients())


@app.post("/clients/{mac}/name", tags=["clients"])
def rename_client(mac: str, body: ClientRename):
    return session.call(lambda d: d.set_client(mac, name=body.name))


@app.get("/port-forwards", tags=["port-forwarding"])
def list_port_forwards():
    return session.call(lambda d: d.port_forwards())


@app.post("/port-forwards", tags=["port-forwarding"])
def add_port_forward(body: PortForwardCreate):
    pid = session.call(
        lambda d: d.add_port_forward(
            body.external_port, body.internal_ip, body.internal_port,
            protocol=body.protocol, name=body.name,
        )
    )
    return {"port_forwarding_id": pid}


@app.delete("/port-forwards/{pf_id}", tags=["port-forwarding"])
def delete_port_forward(pf_id: str):
    return session.call(lambda d: d.delete_port_forward(pf_id))


@app.get("/reservations", tags=["reservations"])
def list_reservations():
    return session.call(lambda d: d.reservations())


@app.post("/reservations", tags=["reservations"])
def add_reservation(body: ReservationCreate):
    return session.call(lambda d: d.add_reservation(body.ip, body.mac))


@app.put("/reservations", tags=["reservations"])
def modify_reservation(body: ReservationModify):
    return session.call(
        lambda d: d.modify_reservation(body.original_ip, body.original_mac, body.ip, body.mac)
    )


@app.delete("/reservations/{mac}", tags=["reservations"])
def remove_reservation(mac: str):
    return session.call(lambda d: d.remove_reservations(mac))


# ---- second-sweep features: overview, client controls, routes, settings, Wi-Fi ----
# The logic lives in deco_features, shared with the desktop app.
@app.get("/overview", tags=["overview"])
def overview():
    """Internet, LAN and DHCP, firmware, and every node with CPU, memory, and throughput."""
    return session.call(deco_features.overview)


@app.get("/overview/nodes", tags=["overview"])
def overview_nodes():
    """Just the nodes with CPU, memory, and throughput, for polling the overview."""
    return session.call(deco_features.node_stats)


@app.get("/clients/speeds", tags=["clients"])
def client_speeds():
    """Live throughput per client in KB/s: {mac: {"down", "up"}}."""
    return session.call(lambda d: {m: {"down": dn, "up": up} for m, (dn, up) in d.client_list_speeds().items()})


class MacList(BaseModel):
    macs: list[str] = Field(..., description="Client MACs, e.g. AA-BB-CC-DD-EE-FF.")


@app.get("/clients/blocked", tags=["clients"])
def blocked_clients():
    return session.call(deco_features.blocked_clients)


@app.post("/clients/block", tags=["clients"])
def block_clients(body: MacList):
    """Block clients from the network (they stay blocked until unblocked)."""
    return session.call(lambda d: deco_features.block_macs(d, body.macs))


@app.delete("/clients/blocked/{mac}", tags=["clients"])
def unblock_client(mac: str):
    return session.call(lambda d: d.unblock_clients(mac))


class Priority(BaseModel):
    enable: bool
    minutes: int = Field(-1, description="How long priority lasts; -1 means always.")


@app.post("/clients/{mac}/priority", tags=["clients"])
def client_priority(mac: str, body: Priority):
    """QoS priority for a client. The Deco rejects this until QoS bandwidth is set."""
    def fn(d):
        c = next((x for x in d.clients() if x.get("mac") == mac), None)
        if c is None:
            raise HTTPException(404, f"No client {mac}")
        return d.set_client_priority(c, body.enable, body.minutes)
    return session.call(fn)


@app.put("/port-forwards/{pf_id}", tags=["port-forwarding"])
def modify_port_forward(pf_id: str, body: PortForwardCreate):
    return session.call(lambda d: d.modify_port_forward(
        pf_id, body.external_port, body.internal_ip, body.internal_port, protocol=body.protocol, name=body.name))


class Route(BaseModel):
    ip: str = Field(..., description="Destination network, e.g. 10.20.0.0")
    mask: str = Field(..., description="Netmask, e.g. 255.255.255.0")
    gateway: str
    interface: str = Field("lan", description="lan | wan")
    name: str = ""
    enable: bool = True


@app.get("/routes", tags=["network"])
def list_routes():
    return session.call(deco_features.static_routes)


@app.post("/routes", tags=["network"])
def add_route(body: Route):
    return session.call(lambda d: d.add_static_route(body.ip, body.mask, body.gateway, body.interface, body.name, body.enable))


@app.put("/routes/{route_id}", tags=["network"])
def modify_route(route_id: str, body: Route):
    return session.call(lambda d: d.modify_static_route(
        route_id, body.ip, body.mask, body.gateway, body.interface, body.name, body.enable))


@app.delete("/routes/{route_id}", tags=["network"])
def remove_route(route_id: str):
    return session.call(lambda d: d.remove_static_routes(route_id))


class NodeName(BaseModel):
    name: str


@app.post("/devices/{device_id}/name", tags=["mesh"])
def rename_node(device_id: str, body: NodeName):
    return session.call(lambda d: d.set_device_nickname(device_id, body.name))


@app.get("/settings", tags=["settings"])
def get_settings():
    """Every safe setting, plus read-only context (time zone, DDNS, DHCP)."""
    return session.call(deco_features.read_settings)


@app.put("/settings/{name}", tags=["settings"])
def put_setting(name: str, changes: dict):
    """Change one setting. The body holds only the fields to change; the server merges them
    into the current value and returns the result."""
    if name not in deco_features.SETTINGS:
        raise HTTPException(404, f"Unknown setting {name}. Known: {', '.join(deco_features.SETTINGS)}")
    return session.call(lambda d: deco_features.write_setting(d, name, changes))


@app.get("/security/allowed-websites", tags=["security"])
def allowed_websites():
    return session.call(lambda d: d.allowed_websites())


class Website(BaseModel):
    domain: str


@app.post("/security/allowed-websites", tags=["security"])
def allow_website(body: Website):
    return session.call(lambda d: d.allow_website(body.domain))


@app.delete("/security/allowed-websites/{domain}", tags=["security"])
def disallow_website(domain: str):
    return session.call(lambda d: d.disallow_website(domain))


# ---- Phase 2: changes that drop Wi-Fi or reboot a node ----
@app.get("/wifi", tags=["wifi"])
def get_wifi():
    """Main, guest, and IoT networks per band, with SSIDs and passwords decoded."""
    return session.call(deco_features.wifi)


class WifiChange(BaseModel):
    network: str = Field(..., description="host (main) | guest | iot")
    ssid: str | None = None
    password: str | None = None
    enable: bool | None = None
    secured: bool | None = Field(None, description="Guest/IoT only: true = WPA2 with the password, false = open.")


@app.put("/wifi", tags=["wifi"])
def put_wifi(body: WifiChange):
    """Change a network on every band at once (the Deco uses one name across bands).
    Every Wi-Fi device reconnects, which takes 10 to 30 seconds."""
    if body.network not in ("host", "guest", "iot"):
        raise HTTPException(422, "network must be host, guest, or iot")
    if body.password and len(body.password) < 8:
        raise HTTPException(422, "Wi-Fi passwords need at least 8 characters")
    return session.call(lambda d: deco_features.set_wifi_network(
        d, body.network, ssid=body.ssid, password=body.password, enable=body.enable, secured=body.secured))


# ---- WAN / LAN: UNTESTED on hardware (shapes mirror the Deco app; see docs/WRITES.md) ----
class WanChange(BaseModel):
    dial_type: str = Field(..., description="dynamic_ip | static_ip | pppoe")
    enable_auto_dns: bool = True
    dns1: str | None = None
    dns2: str | None = None
    mtu_size: int | None = None
    ip: str | None = Field(None, description="static_ip only")
    mask: str | None = Field(None, description="static_ip only")
    gateway: str | None = Field(None, description="static_ip only")
    username: str | None = Field(None, description="pppoe only")
    password: str | None = Field(None, description="pppoe only")


class Toggle(BaseModel):
    enable: bool


class LanIp(BaseModel):
    ip: str
    mask: str = "255.255.255.0"


class DhcpChange(BaseModel):
    start_ip: str | None = None
    end_ip: str | None = None
    dns1: str | None = None
    dns2: str | None = None


@app.get("/wan", tags=["wan-lan (untested)"])
def get_wan():
    """The internet connection: type, DNS, MTU, ping, and static-IP fields."""
    return session.call(deco_features.wan_settings)


@app.put("/wan", tags=["wan-lan (untested)"])
def put_wan(body: WanChange):
    """UNTESTED on hardware. Re-applies the internet connection (it drops for a few seconds);
    wrong values keep it down until corrected. deco-local itself keeps working over the LAN."""
    return session.call(lambda d: deco_features.set_wan(d, **body.model_dump()))


@app.put("/wan/ping", tags=["wan-lan (untested)"])
def put_wan_ping(body: Toggle):
    """UNTESTED on hardware. Whether the Deco answers pings from the internet."""
    return session.call(lambda d: deco_features.set_wan_ping(d, body.enable))


@app.get("/lan", tags=["wan-lan (untested)"])
def get_lan():
    """The Deco's LAN address and the DHCP server settings."""
    return session.call(deco_features.lan_settings)


@app.put("/lan/ip", tags=["wan-lan (untested)"])
def put_lan_ip(body: LanIp):
    """UNTESTED on hardware. Changes the Deco's own address: every device has to get a new
    address, and reservations and port forwards in the old range stop working."""
    return session.call(lambda d: deco_features.set_lan_ip(d, body.ip, body.mask))


@app.put("/lan/dhcp", tags=["wan-lan (untested)"])
def put_dhcp(body: DhcpChange):
    """UNTESTED on hardware. The DHCP pool and the DNS servers it hands out; devices pick
    up the change when their leases renew."""
    return session.call(lambda d: deco_features.set_dhcp(d, **body.model_dump()))


@app.get("/firmware", tags=["system"])
def firmware():
    return session.call(deco_features.firmware)


@app.post("/devices/{device_id}/reboot", tags=["mesh"])
def reboot_node(device_id: str):
    """Reboot one Deco. It drops off the mesh for 3 to 5 minutes; the main Deco takes the
    whole network down for that long."""
    return session.call(lambda d: d.reboot_devices(device_id))


# ---- web UI (web/index.html + assets), when present ----
WEB_DIR = Path(__file__).resolve().parent / "web"
if WEB_DIR.is_dir():
    app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")

    @app.get("/", include_in_schema=False)
    def web_ui():
        return FileResponse(WEB_DIR / "index.html")


def healthcheck():
    """Exit 0 if this server answers /health (the container HEALTHCHECK)."""
    import urllib.request

    host = os.environ.get("DECO_API_HOST", "127.0.0.1")
    host = "127.0.0.1" if host in ("", "0.0.0.0") else host
    url = f"http://{host}:{os.environ.get('DECO_API_PORT', '8777')}/health"
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers={"Host": "localhost"}), timeout=4)
    except Exception as e:
        print(f"unhealthy: {e}")
        return 1
    return 0


def main():
    import sys

    import uvicorn

    if "--healthcheck" in sys.argv[1:]:
        sys.exit(healthcheck())
    uvicorn.run(
        app,
        host=os.environ.get("DECO_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("DECO_API_PORT", "8777")),
    )


if __name__ == "__main__":
    main()
