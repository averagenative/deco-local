"""Serialized backend worker for the GTK app.

Owns exactly one `DecoLocal` session on a dedicated thread. The UI never calls the
device directly — it submits jobs, and results/errors are marshaled back to the UI
thread with `GLib.idle_add`. All jobs run one at a time, matching the TMP session's
single-connection model and the device's auth-lockout constraint (never retry auth
in a loop).
"""

import os
import queue
import socket
import sys
import threading
from pathlib import Path

from gi.repository import GLib

# Make the proven backend (`deco_api.py`, sibling of this package) importable
# regardless of the current working directory.
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import deco_api  # noqa: E402  (path set up above)
import deco_demo  # noqa: E402
import deco_log  # noqa: E402

_log = deco_log.get_logger("desktop")


# DECO_DEMO=1: an in-memory demo mesh instead of a real Deco (deco_demo.py).
DEMO = os.environ.get("DECO_DEMO", "") not in ("", "0", "false")

# Connection states
DISCONNECTED = "disconnected"
CONNECTING = "connecting"
CONNECTED = "connected"
LOCKED_OUT = "locked-out"

# Transport-level exceptions that mean the tunnel/session is gone (vs. an
# application-layer DecoError, which leaves the session usable).
_TRANSPORT_ERRORS = (OSError, EOFError, socket.error, deco_api.TmpError)
try:  # paramiko transport failures
    import paramiko

    _TRANSPORT_ERRORS = _TRANSPORT_ERRORS + (paramiko.SSHException,)
    _AUTH_ERRORS = (paramiko.AuthenticationException,)
except Exception:  # pragma: no cover - paramiko always present in practice
    _AUTH_ERRORS = ()


class CredentialsError(RuntimeError):
    """No usable TP-Link credentials were found."""


class _Job:
    __slots__ = ("fn", "on_success", "on_error", "label")

    def __init__(self, fn, on_success, on_error, label):
        self.fn = fn
        self.on_success = on_success
        self.on_error = on_error
        self.label = label


_SHUTDOWN = object()
_CONNECT = object()
_DISCONNECT = object()


class Backend:
    """A single-threaded, serialized owner of one DecoLocal session.

    Callbacks (`on_state_change`, and each job's `on_success`/`on_error`) are always
    invoked on the GTK main thread.
    """

    def __init__(self, creds_path="~/.tplink_cloud", on_state_change=None):
        self.creds_path = creds_path
        self._on_state_change = on_state_change
        self._q = queue.Queue()
        self._deco = None
        self.state = DISCONNECTED
        self.info = None  # dict: {'model','ip','nodes'} once connected
        self._thread = threading.Thread(target=self._run, name="deco-backend", daemon=True)
        self._thread.start()

    # ---- public API (called from the UI thread) ----

    def connect(self):
        """Establish the single session. Safe to call only when disconnected."""
        if self.state in (CONNECTING, CONNECTED):
            return
        self._set_state(CONNECTING)
        self._q.put(_CONNECT)

    def disconnect(self):
        self._q.put(_DISCONNECT)

    def reconnect(self):
        """Drop the session (if any) and connect again, e.g. after new credentials."""
        self._q.put(_DISCONNECT)
        self._q.put(_CONNECT)

    def has_credentials(self):
        if DEMO or (os.environ.get("TPLINK_USER") and os.environ.get("TPLINK_PASS")):
            return True
        return Path(self.creds_path).expanduser().is_file()

    def saved_email(self):
        try:
            return Path(self.creds_path).expanduser().read_text().splitlines()[0].strip()
        except (OSError, IndexError):
            return ""

    def save_credentials(self, email, password):
        """Write the two-line credentials file (email, password), readable only by you."""
        path = Path(self.creds_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(f"{email.strip()}\n{password}\n")
        os.chmod(path, 0o600)

    def submit(self, fn, on_success=None, on_error=None, label=None):
        """Queue a backend call. `fn` receives the live DecoLocal and returns a result.

        `on_success(result)` / `on_error(exception)` run on the UI thread. Jobs run
        strictly one at a time on the worker thread.
        """
        self._q.put(_Job(fn, on_success, on_error, label))

    def shutdown(self):
        self._q.put(_SHUTDOWN)

    # ---- worker thread ----

    def _run(self):
        while True:
            item = self._q.get()
            if item is _SHUTDOWN:
                self._safe_close()
                return
            if item is _CONNECT:
                if self.state != CONNECTING:
                    self._set_state(CONNECTING)
                self._do_connect()
                continue
            if item is _DISCONNECT:
                self._safe_close()
                self.info = None
                self._set_state(DISCONNECTED)
                continue
            # a normal job
            self._do_job(item)

    def _do_connect(self):
        try:
            if not self.has_credentials():
                raise CredentialsError("Sign in with your TP-Link account to connect.")
            if DEMO:
                deco = deco_demo.DemoDeco()
            else:
                deco = deco_api.DecoLocal.from_env_or_file(self.creds_path).connect()
        except CredentialsError as e:
            self._set_state(DISCONNECTED, error=e)
            return
        except _AUTH_ERRORS as e:
            # Do NOT retry — the device locks out after repeated auth failures.
            self._set_state(LOCKED_OUT, error=e)
            return
        except Exception as e:
            self._set_state(DISCONNECTED, error=e)
            return
        self._deco = deco
        m = deco.master or {}
        self.info = {
            "model": m.get("device_model", "Deco"),
            "ip": m.get("ip", "?"),
            "nodes": len(deco.nodes or []),
        }
        _log.info("connected to %s @ %s (%d nodes)",
                  self.info["model"], self.info["ip"], self.info["nodes"])
        self._set_state(CONNECTED)

    def _do_job(self, job):
        if self._deco is None:
            self._dispatch_error(job, RuntimeError("Not connected."))
            return
        try:
            result = job.fn(self._deco)
        except _AUTH_ERRORS as e:
            self._safe_close()
            self.info = None
            self._set_state(LOCKED_OUT, error=e)
            self._dispatch_error(job, e)
            return
        except _TRANSPORT_ERRORS as e:
            # The tunnel/session is gone — drop to disconnected, do not auto-retry.
            self._safe_close()
            self.info = None
            self._set_state(DISCONNECTED, error=e)
            self._dispatch_error(job, e)
            return
        except Exception as e:
            # Application-layer failure (e.g. DecoError): session is still fine.
            self._dispatch_error(job, e)
            return
        if job.on_success is not None:
            GLib.idle_add(job.on_success, result)

    # ---- helpers ----

    def _dispatch_error(self, job, exc):
        if job.on_error is not None:
            GLib.idle_add(job.on_error, exc)

    def _safe_close(self):
        if self._deco is not None:
            try:
                self._deco.close()
            except Exception:
                pass
            self._deco = None

    def _set_state(self, state, error=None):
        self.state = state
        if error is not None:
            _log.warn("state=%s: %s", state, error)
        else:
            _log.debug("state=%s", state)
        if self._on_state_change is not None:
            GLib.idle_add(self._on_state_change, state, self.info, error)
