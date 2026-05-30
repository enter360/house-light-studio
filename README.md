# House Light Studio

A browser-based sequence designer for **Govee permanent outdoor lights** (and compatible RGBIC devices). Design frame-by-frame color patterns across individually addressable segments, preview them live in the browser, add loops, then export UDP payloads ready to send directly to your lights over your local network — no cloud required.

![screenshot placeholder](docs/screenshot.png)

## Features

- **Per-segment color control** — paint individual segments using the Govee "Grafiti mode" protocol
- **Timeline editor** — multi-frame sequences with per-frame duration
- **Loop support** — define loop regions with configurable repeat counts (including infinite)
- **Live browser preview** — three visualization modes: strip, house outline, vertical
- **Gradient tool** — interpolate between two colors across selected segments
- **LAN-first** — generates `ptReal` UDP payloads for direct local device control (no Govee cloud needed)
- **Import / Export** — save and load sequences as JSON
- **Zero dependencies** — single HTML file, no build step, works offline

## Quick Start

1. Download `index.html`
2. Open it in any modern browser (Chrome, Firefox, Safari, Edge)
3. Set your **segment count** to match your lights (sidebar → Segments)
4. Paint segments, build a sequence, add loops
5. Click **Send to Device** to get the UDP payload

## Sending to Your Lights

Browsers can't send raw UDP, so copy the generated JSON and send it from a terminal:

```bash
# macOS / Linux (netcat)
echo '<paste JSON here>' | nc -w1 -u 192.168.1.x 4003

# Python
python3 -c "
import socket, json, sys
payload = json.loads(sys.stdin.read())
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.sendto(json.dumps(payload).encode(), ('192.168.1.x', 4003))
" <<< '<paste JSON here>'
```

Or use the included bridge script for live in-browser control:

```bash
cd bridge
pip install websockets
python3 udp_bridge.py --host 0.0.0.0 --port 8765
```

Then enable the bridge in the app settings.

## Device Prerequisites

1. Open the **Govee Home** app on your phone
2. Go to your device → Settings → **LAN Control** → enable it
3. Note the device's local IP address (check your router's DHCP table or the app)

### Supported Devices

Any Govee device with LAN control and segment support, including:

| Series | Models |
|--------|--------|
| Permanent outdoor lights | H705A, H705B, H705C, H7050, H7051, H7055 |
| String lights | H619x, H61xx series |
| Strip lights | H618x, H615x series |

The app auto-adapts to any segment count (1–50). If your model isn't listed, try it anyway — if LAN control is enabled it will likely work.

## Protocol

The app uses the Govee LAN UDP API with the **`ptReal` / Grafiti mode** for per-segment color control.

| Port | Purpose |
|------|---------|
| 4001 | Device discovery (multicast to `239.255.255.250`) |
| 4002 | Device responses (listen here) |
| 4003 | Control commands (send here) |

Full protocol documentation: [`docs/protocol.md`](docs/protocol.md)

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Space` | Play / Pause |
| `←` / `→` | Step frames |
| `Shift+Enter` | Add frame |
| `Ctrl/⌘+D` | Duplicate frame |
| `Ctrl/⌘+F` | Fill all segments |
| `Ctrl/⌘+A` | Select all segments |
| `Esc` | Deselect segments |
| Right-click segment | Toggle select |
| `Shift+click` segment | Range select |

## Home Assistant

House Light Studio ships as a **native HA add-on** — not a HACS integration. Add-ons run as supervised containers managed by the HA Supervisor; HACS is for custom integrations and Lovelace plugins, which is a separate system.

### Installing the add-on

> **Requires:** Home Assistant OS or Supervised + Mosquitto broker add-on

1. Go to **Settings → Add-ons → Add-on Store**
2. Click **⋮ → Repositories**
3. Add `https://github.com/YOUR_USERNAME/house-light-studio`
4. Find **House Light Studio** and click **Install → Start**
5. The designer opens in the HA sidebar under **Light Studio**

The add-on auto-connects to your Mosquitto broker. Each discovered Govee device appears as a `light` entity. Sequences you save in the designer become **light effects** you can trigger from automations, dashboards, and voice assistants.

```yaml
# Example automation
action:
  - service: light.turn_on
    target:
      entity_id: light.govee_h705a
    data:
      effect: "Sunset"
      brightness: 200
```

Full add-on docs: [`ha-addon/README.md`](ha-addon/README.md)

## Contributing

PRs and issues welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

Ideas for future work:
- Scene presets library (chase, breathe, twinkle, etc.)
- Timeline drag-to-reorder frames
- Per-segment timing offsets
- Multi-device sync (send one sequence to multiple lights simultaneously)
- Live sequence playback via bridge (not just first-frame)

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

Protocol reverse engineering by the community at:
- [egold555/Govee-Reverse-Engineering](https://github.com/egold555/Govee-Reverse-Engineering)
- [wez/govee2mqtt](https://github.com/wez/govee2mqtt)
- [AlgoClaw/Govee](https://github.com/AlgoClaw/Govee)
- [loebi-ch](https://github.com/egold555/Govee-Reverse-Engineering/issues/11#issuecomment-1) (Grafiti mode segment control)
