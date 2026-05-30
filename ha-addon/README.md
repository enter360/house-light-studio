# House Light Studio — Home Assistant Add-on

Runs the full House Light Studio designer inside Home Assistant, with MQTT integration so your Govee lights appear as native HA light entities.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Home Assistant                                             │
│  ┌────────────┐   MQTT commands    ┌─────────────────────┐  │
│  │ Automations│ ──────────────────▶│  House Light Studio │  │
│  │ Dashboard  │                    │  Add-on (bridge)    │  │
│  │ Alexa/GH   │ ◀──────────────────│                     │  │
│  └────────────┘   MQTT state       │  • Device discovery │  │
│                                    │  • Sequence storage  │  │
│  ┌────────────┐   WebSocket        │  • HA MQTT discovery │  │
│  │  Browser   │ ◀─────────────────▶│  • Ingress web UI   │  │
│  │  Designer  │                    └──────────┬──────────┘  │
│  │  (UI)      │                               │ UDP :4003   │
│  └────────────┘                    ┌──────────▼──────────┐  │
│                                    │   Govee Lights      │  │
│                                    │   (local network)   │  │
│                                    └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

Before installing the add-on:

1. **Home Assistant OS or Supervised** — add-ons are not available on Home Assistant Container or Core
2. **Mosquitto broker add-on** installed and running
   - Go to **Settings → Add-ons → Add-on Store → Mosquitto broker → Install → Start**
   - In Mosquitto's **Configuration** tab, ensure `customize.active` is `false` (default) — this allows the add-on to auto-connect without extra credentials
3. **LAN Control enabled on your Govee lights**
   - Open the **Govee Home** app → tap your device → Settings → **LAN Control → ON**
   - Your lights and HA must be on the **same network/VLAN**

## Installation

### Step 1 — Add this repository to HA

1. Go to **Settings → Add-ons → Add-on Store**
2. Click the **⋮ menu** (top right) → **Repositories**
3. Paste the URL and click **Add**:
   ```
   https://github.com/YOUR_USERNAME/house-light-studio
   ```
4. Close the dialog — the store will refresh

### Step 2 — Install and start

1. Find **House Light Studio** in the store (scroll down or search)
2. Click **Install** and wait for the image to download (~1–2 min)
3. Click **Start**
4. Enable **"Show in sidebar"** if you want quick access from the HA nav

### Step 3 — Open the designer

- Click **Open Web UI** on the add-on page, or
- Click **Light Studio** in the HA sidebar

The add-on auto-discovers your Govee lights on startup (takes ~5 seconds). You'll see them appear in the **Bridge / HA** section of the designer sidebar.

## Configuration

Most users need no manual config — the add-on connects to Mosquitto automatically via HA's service discovery.

If you're using an external MQTT broker, set these in the add-on **Configuration** tab:

```yaml
mqtt_host: "192.168.1.x"    # your broker IP
mqtt_port: 1883
mqtt_username: "your_user"  # leave blank if no auth
mqtt_password: "your_pass"
scan_interval: 60           # seconds between device re-scans
topic_prefix: "govee_studio"
```

## Using the Designer

1. Open the web UI (sidebar or **Open Web UI**)
2. Under **Bridge / HA** in the left sidebar, click **Connect**
   - The URL defaults to `ws://homeassistant.local:8765` — change it if your HA has a different hostname
3. Select your device from the **Device** dropdown
4. Design your sequence using the segment editor and timeline
5. Enter a name (e.g. `Sunset`) in the **Sequence name** field
6. Click **💾 Save to HA** — this stores the sequence and republishes MQTT discovery
7. Your Govee device now has a new **effect** in HA named `Sunset`

## Home Assistant Integration

Each discovered Govee device appears as a `light` entity supporting:

| Feature | Details |
|---------|---------|
| On/Off | UDP `turn` command |
| Brightness | HA 0–255 mapped to Govee 1–100% |
| Effects | Each saved sequence = one selectable effect |
| State reporting | Published to MQTT after every command |

### Example automation

```yaml
automation:
  - alias: "Sunset mode at dusk"
    trigger:
      - platform: sun
        event: sunset
    action:
      - service: light.turn_on
        target:
          entity_id: light.govee_h705a
        data:
          effect: "Sunset"
          brightness: 200

  - alias: "Turn off at midnight"
    trigger:
      - platform: time
        at: "00:00:00"
    action:
      - service: light.turn_off
        target:
          entity_id: light.govee_h705a
```

### Dashboard card

```yaml
type: light
entity: light.govee_h705a
name: House Lights
```

## MQTT Topics

| Topic | Direction | Description |
|-------|-----------|-------------|
| `govee_studio/{device_id}/set` | HA → Add-on | On/off, brightness, effect commands |
| `govee_studio/{device_id}/state` | Add-on → HA | Current state after each command |
| `homeassistant/light/hls_{device_id}/config` | Add-on → HA | Auto-discovery config (retained) |

`{device_id}` is the device's MAC address with colons stripped and lowercased, e.g. `1f80c532323672`.

### Command payload (HA → Add-on)

```json
{ "state": "ON", "brightness": 200, "effect": "Sunset" }
```

### State payload (Add-on → HA)

```json
{ "state": "ON", "brightness": 200, "effect": "Sunset" }
```

## Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 8099 | HTTP | Designer web UI (also served via HA ingress) |
| 8765 | WebSocket | Browser ↔ add-on real-time control |

## Data Storage

The add-on stores device registry and sequences in `/data` (the add-on's persistent storage directory). This survives restarts and updates. You can back it up via HA's built-in backup system.

## Building Locally (developers)

The `ha-addon/` directory is the Docker build context, so `index.html` must be staged there before building:

```bash
cd ha-addon
chmod +x build.sh
./build.sh
```

This copies `index.html` into `ha-addon/static/`, then builds the image. See `build.sh` for the full command including how to run the container standalone for testing without HA.

## Troubleshooting

**Add-on doesn't appear after adding repository**
- Hard refresh the browser (Ctrl+Shift+R) after adding the repository URL
- Check HA logs under **Settings → System → Logs** for Supervisor errors

**No devices discovered**
- Confirm LAN Control is enabled in the Govee app (per Prerequisites above)
- Confirm your HA instance and lights are on the same network — separate VLANs will block UDP multicast
- Check the add-on logs (**Add-ons → House Light Studio → Log**) for discovery output

**MQTT not connecting**
- Verify the Mosquitto add-on is running (green status dot)
- Open Mosquitto's **Log** tab — look for connection errors mentioning `house_light_studio`
- If you see auth errors, set credentials manually in the Configuration tab

**Effects not showing in HA**
- You must save at least one sequence in the designer first
- After saving, wait ~10 seconds for MQTT discovery to republish, then check **Developer Tools → States** and search for your light entity
- If still missing, restart the add-on to force a fresh discovery publish

**WebSocket won't connect from the designer**
- Make sure the bridge URL is `ws://homeassistant.local:8765` (or your HA's IP/hostname)
- If accessing HA via HTTPS, you may need `wss://` — only works if you have a valid TLS cert
