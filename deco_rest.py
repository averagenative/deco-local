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
    version="1.1.0",
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


def _node_name(node):
    """Display name for a mesh node: the custom nickname (base64 on the wire) or the
    preset location key (e.g. living_room)."""
    if node.get("nickname") == "custom" and node.get("custom_nickname"):
        return deco_api.b64decode(node["custom_nickname"])
    return (node.get("nickname") or node.get("device_model") or "Deco").replace("_", " ").title()


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
    nodes = session.call(lambda d: d.devices())
    for n in nodes:
        n["name"] = _node_name(n)
    return nodes


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
