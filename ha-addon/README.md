# House Light Studio — Home Assistant Add-on

Runs the full House Light Studio designer inside Home Assistant, with MQTT integration so your Govee lights appear as native HA light entities.

## What it does

```
┌─────────────────────────────────────────────────────────────┐
│  Home Assistant                                             │
│  ┌────────────┐   MQTT commands    ┌─────────────────────┐  │
│  │ Automations│ ──────────────────▶│  House Light Studio │  │
│  │ Dashboard  │                    │  Add-on (bridge)    │  │
│  │ Alexa/GH   │ ◀────────────────── │                     │  │
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

## Installation

### Prerequisites
- Home Assistant OS or Supervised
- **Mosquitto broker** add-on installed and running
- Govee lights with **LAN Control enabled** (Govee app → device → Settings → LAN Control)

### Install the add-on

1. In HA, go to **Settings → Add-ons → Add-on Store**
2. Click the **⋮ menu → Repositories**
3. Add: `https://github.com/YOUR_USERNAME/house-light-studio`
4. Find **House Light Studio** in the store and click **Install**
5. Start the add-on

The add-on auto-connects to your Mosquitto broker via HA's service discovery — no MQTT credentials to configure in most setups.

### Manual MQTT config (if not using Mosquitto add-on)

In the add-on **Configuration** tab:

```yaml
mqtt_host: "192.168.1.x"
mqtt_port: 1883
mqtt_username: "your_user"
mqtt_password: "your_password"
```

## Using the Designer

1. Click **Open Web UI** in the add-on page (or find "Light Studio" in the HA sidebar)
2. In the sidebar under **Bridge / HA**, click **Connect** — it auto-connects since you're inside HA
3. Design your sequence, then click **💾 Save to HA** with a name like "Sunset"
4. The sequence appears as a **light effect** on your Govee entity in HA

## Home Assistant Integration

Each discovered Govee device appears as a `light` entity with:

| Feature | Details |
|---------|---------|
| On/Off | Sends `turn` command via UDP |
| Brightness | Maps HA 0–255 → Govee 1–100% |
| Effects | Each saved sequence = one effect |
| State | Published back to MQTT after each command |

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
| `govee_studio/{device_id}/set` | HA → Bridge | Commands (JSON) |
| `govee_studio/{device_id}/state` | Bridge → HA | State (JSON) |
| `homeassistant/light/hls_{device_id}/config` | Bridge → HA | Discovery |

### Command payload

```json
{ "state": "ON", "brightness": 200, "effect": "Sunset" }
```

### State payload

```json
{ "state": "ON", "brightness": 200, "effect": "Sunset" }
```

## Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 8099 | HTTP | Designer web UI (also via HA ingress) |
| 8765 | WebSocket | Browser ↔ bridge real-time control |

## Data Storage

Sequences and device registry are persisted in the add-on's `/data` directory and survive restarts.

## Troubleshooting

**No devices discovered**
- Confirm LAN Control is enabled in the Govee app for each device
- Check that your HA instance is on the same network/VLAN as the lights
- UDP multicast may be blocked on some managed switches — try assigning a static IP to your lights and adding it to the scan list

**MQTT not connecting**
- Ensure Mosquitto add-on is running
- Check the add-on logs for the MQTT connection error
- Try setting credentials manually in Configuration

**Effects not showing in HA**
- Save at least one sequence via the designer UI first
- Restart the add-on after saving new sequences to force a discovery re-publish
