# Deco local WRITES — mechanism + verified operations

Writes use the **same TMP transport/codec as reads** (`deco_api.py`), but with one
critical difference discovered empirically:

## The write envelope (universal)
Reads send the params (or empty) directly. **Writes must wrap params in a luci-style
envelope** — the TMP daemon dispatches to luci Lua controllers which expect it:

```json
{"operation": "<op>", "params": { ... } }
```

A bare params object (no envelope) returns `{"error_code":1,"msg":"invalid args"}`.
`{"params":{...}}` alone also works (the opcode implies the action), but we send
`operation` too, matching the app. `deco_api.DecoLocal.write(op, params, operation)`
builds this and raises `DecoError` on a non-zero `error_code`.

The success response is `{"error_code":0}`, sometimes with a `result` (e.g. a new id).

## Verified writes (tested live, self-cleaning round-trips)

### Address reservation
| op | opcode | body params | notes |
|----|--------|-------------|-------|
| add    | `0x40C1` | `{"reservation_list":[{"ip","mac"}]}` | ip within the DHCP pool; mac `AA-BB-CC-DD-EE-FF` |
| modify | `0x40C2` | `{"original_ip","original_mac","ip","mac"}` | identify by original_*, set new ip/mac |
| remove | `0x40C3` | `{"reservation_list":["<mac>", ...]}` | matches on MAC |

`deco_api`: `add_reservation(ip, mac)`, `modify_reservation(orig_ip, orig_mac, ip, mac)`,
`remove_reservations(macs)`.

### Port forwarding
| op | opcode | body params | notes |
|----|--------|-------------|-------|
| add    | `0x40B1` | `{"external_port","internal_ip","internal_port","protocol","service_type","service_name"}` | protocol tcp/udp/all; service_type "custom"; **service_name is base64**; returns `{"port_forwarding_id"}` |
| modify | `0x40B2` | PortForwardingBean (+ id) | not yet tested |
| delete | `0x40B3` | `{"port_forwarding_id":"<id>"}` | id from PORT_FORWARDING_LIST_GET |

`deco_api`: `add_port_forward(external_port, internal_ip, internal_port, protocol, name)`
→ returns new id; `delete_port_forward(id)`.

## Settings (the `set` envelope) — read-modify-write

Settings opcodes use `operation: "set"`. The safe idiom is **read-modify-write**: read the
current `*_GET`, change only the field(s) you want, write the whole object back. `deco_api`
provides `_update(get_op, set_op, changes)` and named setters that do exactly this.

### Verified-safe setters (no radio/WAN/DHCP disruption; tested live)
| method | get / set opcodes | shape (merged) |
|--------|-------------------|----------------|
| `set_sip_alg(enable)`            | `0x421D` / `0x421E` | `{enable}` — flip+restore verified |
| `set_monthly_report(enable)`     | `0x4222` / `0x4223` | `{enable}` |
| `set_client_isolation(enable)`   | `0x4302` / `0x4303` | `{enable}` |
| `set_reboot_schedule(**ch)`      | `0x42E0` / `0x42E1` | `{enable, setting}` |
| `set_system_time(**ch)`          | `0x427C` / `0x427D` | `{tz_region, time, timezone}` |
| `set_eco_mode(**ch)`             | `0x43C0` / `0x43C1` | `{has_set_eco_mode, duration, power_mode, enable}` |
| `set_wifi_schedule(**ch)`        | `0x43C2` / `0x43C3` | `{has_set_wifi_schedule, time_begin, time_end, enable, enable_band2_4}` |
| `set_antivirus_settings(**ch)`   | `0x4267` / `0x4268` | `{iot_protection, intrusion_prevention, web_protection}` |

All confirmed via idempotent write-back (`error_code 0`); SIP-ALG additionally flip+restored.

### Antivirus allowed-website list (verified, self-cleaning)
`allow_website(domain)` → `0x4324` add, `disallow_website(domain)` → `0x4325` remove, body
`{"website_list":[domain]}`.

### Radio/DHCP-adjacent toggles (implemented; re-applies that subsystem — brief blip)
`set_beamforming(enable)` `0x421C`, `set_smart_dhcp(enable)` `0x4093`. `{enable}` write-back
accepted; not flip-tested to avoid a radio/DHCP bounce.

### DISRUPTIVE setters — implemented, NOT auto-tested
These re-apply core config and can drop clients or reboot the mesh. Bodies merge `changes`
into the matching `*_GET`. Use deliberately (maintenance window):
`set_wireless` `0x4008` (SSID/passphrase/channel), `set_ipv4` `0x4005`, `set_ipv6` `0x4007`,
`set_mac_clone` `0x4227` (WAN MAC), `set_qos_mode` `0x4037`, `set_operation_mode` `0x40A1`
(Router/AP — **reboots the whole mesh**).

### More verified writes
| method | opcode | body | notes |
|--------|--------|------|-------|
| `set_fw_auto_update(enable,time_begin,time_end)` | `0x427F` | `{enable_auto_update:bool, time_begin:int, time_end:int}` | **FIX:** GET returns time_* as strings, SET wants ints (was the caveat below). Verified |
| `set_client(mac, **changes)` | `0x4013` | `{client_list:[{mac, ...}]}` | name base64; sends mac + changed fields. Idempotent-verified |
| `set_device_nickname(device_id, custom_nickname)` | `0x4003` | `{device_id, nickname, custom_nickname}` | rename a Deco node. Idempotent-verified |
| `add_ipv6_firewall(ip, port, protocol, name)` | `0x4231` | `{firewall_list:[{ip, port:int, protocol, name:b64}]}` | add verified; **remove needs IPv6 enabled** (see caveat) |
| `remove_ipv6_firewall(id)` | `0x4232` | `{firewall_list:[{id}]}` | id-only bean (the `l()` transform) |

### IPv6 firewall caveat
Add works, but **modify/remove only work while IPv6 is ENABLED**. With IPv6 off
(`IPV6_GET.enable_ipv6 == false`) the device's Lua handler errors `attempt to concatenate
a nil value` on the (nil) IPv6 prefix. So don't add IPv6 firewall rules unless IPv6 is on,
or you'll have an (inert) rule you can't remove until you enable IPv6.

### Resolved caveat
`FW_AUTO_UPDATE_SET` (`0x427F`) — the earlier "compare number with string" error was the
GET-string / SET-int mismatch; `set_fw_auto_update()` now converts and it's verified.

## Logging
All tools use `deco_log.py` (timestamped, leveled: DEBUG/INFO/WARN/ERROR/FAIL; `$DECO_LOG_LEVEL`).
`deco_api` logs: connect (INFO), each opcode req/resp (DEBUG), writes (INFO), rejections (ERROR),
reconnects (WARN), auth/no-master (FAIL). Same format is intended for the C app.

## Adding more writes (procedure)
1. Find the write opcode in `deco-opcodes.json` (e.g. `*_SET`, `*_ADD`, `*_DELETE`).
2. Find the param shape: the app's repo passes a bean to `postRequestForSet(r.<field>, <bean>)`;
   read that bean's `@SerializedName` fields (search `deco-decompiled/sources`).
3. Call `deco.write(opcode, params, operation)`. Operation string mirrors the action
   ("add"/"edit"/"remove"/"delete"/"set"); when unsure, `{"params":...}` without operation
   usually works since the opcode encodes the action.
4. **Test safely:** throwaway values (fake locally-administered MAC `02:...`, unused high
   port/IP within range), read-back to verify, then undo. Never mutate real config unchecked.

## Caveats
- The opcode-name registry (`deco-opcodes.json`) is regenerated from r.java; some constants
  aren't `f`-prefixed (e.g. `A1`) — the extractor now catches all identifiers (577 opcodes).
- 140+ write opcodes exist across the management areas (see FEATURES.md); only the two MVP
  features are verified so far. Each needs its param shape confirmed + a safe test.
