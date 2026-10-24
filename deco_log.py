#!/usr/bin/env python3
"""deco_log — small standard logging setup shared by the Deco tools.

Timestamped, leveled output to stderr. Levels: DEBUG, INFO, WARN, ERROR, FAIL
(FAIL sits above ERROR for unrecoverable conditions). The format mirrors what the
C app will emit, so logs look the same across the Python tooling and the GTK/C client:

    2026-06-12 14:30:01 [INFO ] deco: connected to X60 @ 192.168.68.1
    2026-06-12 14:30:02 [WARN ] deco: channel desync, reconnecting
    2026-06-12 14:30:02 [ERROR] deco: op 0x40c0 rejected: invalid args
    2026-06-12 14:30:03 [FAIL ] deco: SSH auth failed

Level is controlled by $DECO_LOG_LEVEL (DEBUG/INFO/WARN/ERROR/FAIL), default INFO.
Use logging output, not print(), in the tools.

    from deco_log import get_logger
    log = get_logger("deco")
    log.info("connected to %s", host)
    log.warn("retrying (%d/%d)", n, total)
    log.error("op 0x%04x failed: %s", op, err)
    log.fail("unrecoverable: %s", err)
"""
import logging
import os
import sys

# Custom FAIL level above ERROR (40) / below CRITICAL (50).
FAIL = 45
logging.addLevelName(FAIL, "FAIL")
# Render WARNING as the 5-char "WARN " so columns line up with FAIL/INFO.
logging.addLevelName(logging.WARNING, "WARN")

_LEVELS = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARN": logging.WARNING,
           "WARNING": logging.WARNING, "ERROR": logging.ERROR, "FAIL": FAIL}


class DecoLogger(logging.Logger):
    """Logger with .warn() and .fail() helpers alongside the stdlib levels."""

    def warn(self, msg, *args, **kwargs):          # noqa: D401 (stdlib warn is deprecated)
        if self.isEnabledFor(logging.WARNING):
            self._log(logging.WARNING, msg, args, **kwargs)

    def fail(self, msg, *args, **kwargs):
        """Log an unrecoverable condition (level FAIL, above ERROR)."""
        if self.isEnabledFor(FAIL):
            self._log(FAIL, msg, args, **kwargs)


logging.setLoggerClass(DecoLogger)

_FORMAT = "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"
_configured = False


def _level_from_env(default=logging.INFO):
    return _LEVELS.get(os.environ.get("DECO_LOG_LEVEL", "").upper(), default)


def configure(level=None, stream=sys.stderr):
    """Install the timestamped formatter on the root 'deco' logger once.
    `level` overrides $DECO_LOG_LEVEL; otherwise the env var (default INFO) wins."""
    global _configured
    root = logging.getLogger("deco")
    if not _configured:
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter(_FORMAT, _DATEFMT))
        root.addHandler(handler)
        root.propagate = False
        _configured = True
    root.setLevel(level if level is not None else _level_from_env())
    return root


def get_logger(name="deco", level=None):
    """Return a configured logger. Children of 'deco' share its handler/level."""
    configure(level)
    return logging.getLogger(name if name.startswith("deco") else f"deco.{name}")


if __name__ == "__main__":
    log = get_logger("deco", level=logging.DEBUG)
    log.debug("debug detail")
    log.info("informational message")
    log.warn("warning: %s", "something looks off")
    log.error("error: op 0x%04x rejected", 0x40C0)
    log.fail("fail: unrecoverable condition")
