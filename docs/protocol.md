# Govee LAN Protocol Notes

This document summarizes the Govee LAN UDP protocol as used by House Light Studio. It is based on community reverse-engineering efforts (see acknowledgments in README).

## Overview

Govee devices with LAN control enabled listen for UDP JSON messages on their local IP. No authentication is required — any device on the same network can send commands.

| Port | Direction | Purpose |
|------|-----------|---------|
| 4001 | → Device | Discovery (multicast to `239.255.255.250`) |
| 4002 | ← Device | Discovery responses + status replies |
| 4003 | → Device | Control commands |

## Device Discovery

Send a multicast UDP packet to `239.255.255.250:4001`:

```json
{
  "msg": {
    "cmd": "scan",
    "data": { "account_topic": "reserve" }
  }
}
```

Listen on port `4002` for responses:

```json
{
  "msg": {
    "cmd": "scan",
    "data": {
      "ip": "192.168.1.23",
      "device": "1F:80:C5:32:32:36:72:4E",
      "sku": "H705A"
    }
  }
}
```

## Basic Commands (port 4003)

### Turn On/Off

```json
{ "msg": { "cmd": "turn", "data": { "value": 1 } } }
```

`value`: `1` = on, `0` = off

### Brightness

```json
{ "msg": { "cmd": "brightness", "data": { "value": 80 } } }
```

`value`: 1–100 (percent)

### Solid Color

```json
{
  "msg": {
    "cmd": "colorwc",
    "data": {
      "color": { "r": 255, "g": 128, "b": 0 },
      "colorTemInKelvin": 0
    }
  }
}
```

Set `colorTemInKelvin` to `0` to use the RGB value. Set it to `2000–9000` to use a color temperature instead.

### Device Status Query

```json
{ "msg": { "cmd": "devStatus", "data": {} } }
```

## Per-Segment Control (Grafiti Mode)

This is the protocol used by House Light Studio for individual segment colors. It works by encoding BLE-style binary packets as base64 strings and sending them via the `ptReal` command.

### Payload structure

```json
{
  "msg": {
    "cmd": "ptReal",
    "data": {
      "command": [
        "owAB...",
        "owEB...",
        "o/8A...",
        "MwUK..."
      ]
    }
  }
}
```

### Building the binary command

The raw command bytes (before packetization) follow this format:

```
01 [packetCount:1] 03 [direction:1] [speed:1] [bgIntensity:1] [bgR:1][bgG:1][bgB:1] [segmentCount:1]
  for each segment:
    [segmentSize:1] [R:1][G:1][B:1] [pixelIndex:1 per pixel in segment]
```

| Field | Description |
|-------|-------------|
| `03` | Mode byte for Grafiti / segment mode |
| `direction` | Animation direction: `0x09`=Up, `0x0A`=Down, `0x02`=Cycle, `0x13`=Fading, `0x0F`=Sparkle, `0x14`=Breathe |
| `speed` | 0–100 |
| `bgIntensity` | Background brightness 0–100 |
| `bgR/G/B` | Background color |
| `segmentCount` | Number of color segments |
| `segmentSize` | Number of physical pixels in this segment |
| `R/G/B` | Segment color |
| `pixelIndex` | Physical pixel indices assigned to this segment |

### Packetization

1. Split the raw hex command into **17-byte (34 hex char) chunks**
2. Prepend each chunk:
   - Non-final chunks: `a3` + `[2-hex index]`
   - Final chunk: `a3ff`, then **zero-pad to 19 bytes (38 hex chars)**
3. Append **XOR checksum** of all bytes in the packet
4. Base64-encode each packet
5. Always append the terminator packet: `MwUKIAMAAAAAAAAAAAAAAAAAAB8=`

### JavaScript reference implementation

See the `buildGrafitiPackets()` function in `index.html`.

## Scene Commands

Pre-defined scenes can be activated by encoding their scene code into a BLE packet and sending via `ptReal`. Scene codes can be fetched from the Govee catalog API:

```bash
curl "https://app2.govee.com/appsku/v1/light-effect-libraries?sku=H705A" \
  -H 'AppVersion: 5.6.01'
```

Convert the `sceneCode` integer to 3 bytes little-endian, then build:
```
0x33 0x05 0x04 [byte0] [byte1] [byte2] 0x00 ... [xor]
```

## References

- [Govee official LAN API guide](https://app-h5.govee.com/user-manual/wlan-guide)
- [egold555/Govee-Reverse-Engineering — scene codes issue](https://github.com/egold555/Govee-Reverse-Engineering/issues/11)
- [wez/govee2mqtt LAN docs](https://github.com/wez/govee2mqtt/blob/main/docs/LAN.md)
- [AlgoClaw/Govee decoder](https://github.com/AlgoClaw/Govee)
