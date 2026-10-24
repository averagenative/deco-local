# How deco-local talks to a Deco

deco-local manages a TP-Link Deco mesh through a local channel on the main Deco, the same one the Deco app uses when it manages the mesh locally. No TP-Link cloud service is involved. This page describes that channel as observed on a Deco X60 (hardware 4.0, firmware 1.7.1). `deco_api.py` is the reference implementation.

## Connection steps

A session takes five steps:

1. **Discover the mesh (TDP).** Broadcast a 16-byte probe to UDP port 20002 on `255.255.255.255`. Each Deco answers with a 16-byte header followed by plain JSON, for example `{"result": {"ip": "192.168.68.1", "role": "master", "device_model": "X60", "tmp_port": [20001], "owner": "<md5 of the lowercased account email>", ...}}`. The main Deco reports `"role": "master"`. Its SSH port stays closed until it receives a probe.
2. **Log in over SSH.** Connect to the main Deco on its `tmp_port` (20001). The username is the hex SHA-1 of the lowercased TP-Link account email. The password is the TP-Link account password. The server is dropbear, and it locks the account out after repeated failures, so never retry a rejected login in a loop.
3. **Open the tunnel.** The SSH server offers no shell. Open a `direct-tcpip` channel to `127.0.0.1:20002` on the device, where the TMP daemon listens.
4. **Bind a TMP session.** Send opcode `0x0001` with an empty body. The reply is a token tied to this connection.
5. **Send requests.** Each request is an opcode plus an optional JSON body, carried in the frames that the next section describes.

The Deco accepts one local session at a time. Close it when you are done so other clients, such as the desktop app, can connect.

## Frames

All integers are big-endian. The CRC is CRC-32 (the zlib polynomial).

Every message on the tunnel is a TMP frame with a 16-byte header:

| Offset | Size | Field |
|---|---|---|
| 0 | 1 | Major version, `1` |
| 1 | 1 | Minor version, `1` |
| 2 | 1 | Type: `5` for data, `6` for an error |
| 3 | 1 | Code, `0` |
| 4 | 2 | Payload length |
| 6 | 1 | Subtype, `0` |
| 7 | 1 | Status, `0` |
| 8 | 4 | Sequence number |
| 12 | 4 | CRC-32 of the whole frame, computed with this field set to `0x5A6B7C8D` |

The payload of a data frame is a v2 packet:

| Offset | Size | Field |
|---|---|---|
| 0 | 2 | `01 02` |
| 2 | 2 | Opcode |
| 4 | 1 | Type: `2` PUSH, `3` PUSH_ACK, `4` PULL, `5` PULL_ACK |
| 5 | 1 | Status (non-zero means rejected; `12` means the opcode is not implemented) |
| 6 | 2 | Transaction ID |
| 8 | 4 | CRC-32 of the complete JSON body |
| 12 | 4 | Total length of the JSON body |
| 16 | 4 | Offset of this chunk in the body |
| 20 | ... | JSON bytes |

A request runs as follows:

1. The client sends PUSH with the opcode and the JSON body.
2. The device answers PUSH_ACK.
3. The client sends PULL at offset 0.
4. The device answers PULL_ACK with the first chunk of the response and its total length.
5. If the response is longer than the chunk, the client sends PULL at the next offset until it has the whole body.

## Reads and writes

A read sends the opcode with an empty body. The response is JSON in the form `{"result": {...}, "error_code": 0}`.

A write wraps its parameters in an envelope. Without the envelope the device answers `{"error_code": 1, "msg": "invalid args"}`.

```json
{"operation": "add", "params": {"reservation_list": [{"ip": "192.168.68.40", "mac": "AA-BB-CC-DD-EE-FF"}]}}
```

The `operation` value is `add`, `remove`, `edit`, `set`, or `delete`, matching what the Deco app sends. A successful write returns `{"error_code": 0}`, sometimes with a `result`, such as the ID of a new port-forwarding rule.

Text that people type, such as client names, port-forwarding service names, node nicknames, and SSIDs, travels base64-encoded.

## Opcodes used by the UIs

The following table lists the opcodes the web UI and desktop app use:

| Opcode | Name | Body |
|---|---|---|
| `0x400F` | `DEVICE_LIST_GET` | Read. Mesh nodes. |
| `0x4012` | `CLIENT_LIST_GET` | Read. Clients, names in base64. |
| `0x4013` | `CLIENT_LIST_SET` | `set` with `{"client_list": [{"mac", "name"}]}` |
| `0x40B0` | `PORT_FORWARDING_LIST_GET` | Read. |
| `0x40B1` | `PORT_FORWARDING_ADD` | `add` with `external_port`, `internal_ip`, `internal_port`, `protocol` (`tcp`, `udp`, or `all`), `service_type` (`custom`), and `service_name` (base64) |
| `0x40B3` | `PORT_FORWARDING_DELETE` | `delete` with `{"port_forwarding_id": "<id>"}` |
| `0x40C0` | `IP_RESERVATION_LIST_GET` | Read. |
| `0x40C1` | `IP_RESERVATION_LIST_ADD` | `add` with `{"reservation_list": [{"ip", "mac"}]}` |
| `0x40C2` | `IP_RESERVATION_MODIFY` | `edit` with `original_ip`, `original_mac`, `ip`, and `mac` |
| `0x40C3` | `IP_RESERVATION_LIST_REMOVE` | `remove` with `{"reservation_list": ["<mac>", ...]}` |

`deco-opcodes.json` maps every opcode name the Deco app defines (577 of them) to its value. [FEATURES.md](FEATURES.md) lists the reads confirmed on an X60, and [WRITES.md](WRITES.md) lists the writes verified on one.
