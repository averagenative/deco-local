#!/usr/bin/env python3
"""Disruptive write verification — RUN DURING A MAINTENANCE WINDOW.

Each test does an IDEMPOTENT write-back: read the current config, write the SAME
values back, confirm error_code 0 and that nothing changed. This proves the write
opcode + body shape work while changing no settings — BUT it RE-APPLIES the
subsystem, so it briefly disrupts that service.

Safety:
  * DRY-RUN by default — prints what it would write, makes NO changes. Add --run.
  * operation_mode (reboots the WHOLE mesh) is EXCLUDED unless --include-reboot.
  * Ordered least -> most disruptive; stops on the first failure.
  * Re-reads after each write and reports whether state is unchanged.
  * Tolerates the control connection dropping (auto-reconnects) — but if a unit
    doesn't come back, you may need to power-cycle it, so stay reachable.

Blast radius per test:
  ipv6            near-zero here (IPv6 is disabled)
  qos_mode        re-applies QoS
  mac_clone       WAN MAC re-applies -> brief INTERNET drop
  ipv4            WAN/LAN re-applies -> brief INTERNET drop (LAN IP unchanged)
  wireless        radios re-apply -> ALL Wi-Fi clients drop ~10-30s and rejoin
  operation_mode  (opt-in) REBOOTS the whole mesh -> ~2-3 min full outage

Usage:
  python3 deco_disruptive_test.py                 # dry run, safe subset
  python3 deco_disruptive_test.py --run           # actually execute the subset
  python3 deco_disruptive_test.py --run --only wireless
  python3 deco_disruptive_test.py --run --include-reboot
"""
import argparse
import json
import sys
import time

from deco_log import get_logger
from deco_api import DecoLocal, DecoError, TmpError

log = get_logger("deco.disruptive")

# (key, GET opcode, SET opcode, settle seconds, one-line impact)
TESTS = [
    ("ipv6",        "IPV6_GET",           "IPV6_SET",            2,  "near-zero (IPv6 off)"),
    ("qos_mode",    "QOS_MODE_GET",       "QOS_MODE_SET",        3,  "re-applies QoS"),
    ("qos_bandwidth", "BANDWIDTH_GET",    "BANDWIDTH_SET",       3,  "re-applies QoS bandwidth"),
    ("mac_clone",   "MAC_CLONE_GET",      "MAC_CLONE_SET",       8,  "WAN MAC -> brief internet drop"),
    ("ipv4",        "IPV4_GET",           "IPV4_SET",            8,  "WAN/LAN -> brief internet drop"),
    ("wireless",    "WIRELESS_GET",       "WIRELESS_SET",       25,  "radios -> all Wi-Fi drops ~10-30s"),
]
REBOOT_TEST = ("operation_mode", "OPERATION_MODE_GET", "OPERATION_MODE_SET", 120,
               "REBOOTS THE WHOLE MESH ~2-3 min")


def _connect():
    d = DecoLocal.from_env_or_file(timeout=15)
    d.connect()
    return d


def run_test(d, key, get_op, set_op, settle, impact, dry):
    log.info("=== %s (%s) ===", key, impact)
    before = d.read(get_op)
    log.info("current %s: %s", key, json.dumps(before)[:200])
    if dry:
        log.info("[dry-run] would write %s back unchanged via %s (operation=set)", key, set_op)
        return True, d
    log.warn("writing %s back (subsystem will re-apply) …", key)
    body = dict(before)
    if key == "qos_bandwidth":
        body.setdefault("bandwidth_mode", "custom")   # required by the SET, absent from the GET
    try:
        d.write(set_op, body, "set")
    except (DecoError, TmpError) as e:
        log.error("%s write REJECTED: %s", key, e)
        return False, d
    except (OSError, EOFError) as e:
        log.warn("control connection dropped during %s write (expected for radio/WAN): %s", key, e)
    # settle, then reconnect + verify
    log.info("settling %ds for %s to re-apply…", settle, key)
    time.sleep(settle)
    for attempt in range(6):
        try:
            d.reconnect_channel()
            break
        except Exception:
            try:
                d.close()
            except Exception:
                pass
            log.warn("reconnect attempt %d/6 …", attempt + 1)
            time.sleep(5)
            try:
                d = _connect()
                break
            except Exception as e:
                log.warn("full reconnect failed: %s", e)
    else:
        log.fail("could not reconnect after %s write — check the mesh!", key)
        return False, d
    after = d.read(get_op)
    same = json.dumps(after, sort_keys=True) == json.dumps(before, sort_keys=True)
    (log.info if same else log.warn)("%s after: %s (unchanged: %s)", key, json.dumps(after)[:200], same)
    return True, d


def _reconnect(d):
    for attempt in range(12):
        try:
            d.close()
        except Exception:
            pass
        try:
            return _connect()
        except Exception as e:
            log.warn("reconnect %d/12 failed: %s", attempt + 1, e)
            time.sleep(10)
    raise RuntimeError("could not reconnect to the Deco")


def guest_toggle(d):
    """Turn the guest network on, verify, turn it off, verify. Two Wi-Fi restarts."""
    w = d.wireless()
    host_before = {k: (b["host"]["ssid"], b["host"]["password"]) for k, b in w.items() if isinstance(b, dict) and "host" in b}
    was = {k: b["guest"]["enable"] for k, b in w.items() if isinstance(b, dict) and "guest" in b}
    for want in (True, False) if not any(was.values()) else (False, True):
        partial = {k: {"guest": {"enable": want}} for k, b in d.wireless().items() if isinstance(b, dict) and "guest" in b}
        log.warn("guest network -> %s (Wi-Fi restarts)", want)
        try:
            d.write_wireless(partial)
        except (OSError, EOFError) as e:
            log.warn("connection dropped during the write (expected): %s", e)
        time.sleep(30)
        d = _reconnect(d)
        now = {k: b["guest"]["enable"] for k, b in d.wireless().items() if isinstance(b, dict) and "guest" in b}
        log.info("guest now %s (wanted %s)", now, want)
        if any(v != want for v in now.values()):
            return False, d
    w2 = d.wireless()
    host_after = {k: (b["host"]["ssid"], b["host"]["password"]) for k, b in w2.items() if isinstance(b, dict) and "host" in b}
    log.info("main network unchanged: %s; guest back to %s", host_after == host_before,
             {k: b["guest"]["enable"] for k, b in w2.items() if isinstance(b, dict) and "guest" in b})
    return host_after == host_before, d


def reboot_node(d, name):
    """Reboot one satellite by display name and wait until it rejoins the mesh."""
    from deco_features import node_name as label
    node = next((n for n in d.devices() if label(n).lower() == name.lower()), None)
    if node is None or node.get("role") == "master":
        log.fail("no satellite named %r (the main Deco is refused here)", name)
        return False, d
    log.warn("rebooting %s (%s) …", label(node), node["device_id"][:12])
    d.reboot_devices(node["device_id"])
    t0 = time.time()
    time.sleep(45)
    seen_down = False
    while time.time() - t0 < 420:
        try:
            st = next(n for n in d.devices() if n["device_id"] == node["device_id"]).get("group_status")
        except Exception as e:
            log.warn("read failed (%s); reconnecting", e)
            d = _reconnect(d)
            continue
        seen_down = seen_down or st != "connected"
        log.info("%4ds %s: %s", time.time() - t0, label(node), st)
        if st == "connected" and (seen_down or time.time() - t0 > 150):
            log.info("%s is back after %ds (went offline: %s)", label(node), time.time() - t0, seen_down)
            return True, d
        time.sleep(15)
    log.fail("%s did not come back within 7 minutes; power-cycle it", label(node))
    return False, d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="actually execute (default: dry-run)")
    ap.add_argument("--only", help="run only this test key")
    ap.add_argument("--include-reboot", action="store_true", help="also test operation_mode (reboots mesh)")
    ap.add_argument("--guest-toggle", action="store_true", help="after the tests, turn the guest network on and off")
    ap.add_argument("--reboot-node", metavar="NAME", help="after the tests, reboot this satellite and wait for it")
    args = ap.parse_args()

    tests = list(TESTS)
    if args.include_reboot:
        tests.append(REBOOT_TEST)
    if args.only:
        tests = [t for t in tests if t[0] == args.only] or \
                ([REBOOT_TEST] if args.only == "operation_mode" else [])
        if not tests:
            log.fail("unknown test key: %s", args.only)
            return 2

    mode = "DRY-RUN (no changes)" if not args.run else "LIVE — WILL DISRUPT THE NETWORK"
    log.warn("disruptive write test — %s", mode)
    log.warn("tests: %s", ", ".join(t[0] for t in tests))
    d = _connect()
    log.info("connected; baseline operation_mode=%s", d.operation_mode().get("mode"))
    ok = True
    for key, gop, sop, settle, impact in tests:
        passed, d = run_test(d, key, gop, sop, settle, impact, dry=not args.run)
        if not passed:
            log.error("stopping after failed test: %s", key)
            ok = False
            break
        time.sleep(1)
    if ok and args.run and args.guest_toggle:
        passed, d = guest_toggle(d)
        ok = ok and passed
    if ok and args.run and args.reboot_node:
        passed, d = reboot_node(d, args.reboot_node)
        ok = ok and passed
    d.close()
    log.info("done — %s", "all passed" if ok else "see failures above")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
