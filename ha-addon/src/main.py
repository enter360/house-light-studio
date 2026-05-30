#!/usr/bin/env python3
"""
House Light Studio — Home Assistant Add-on Bridge
=================================================
Responsibilities:
  1. Serve the designer web UI via HTTP (HA ingress)
  2. WebSocket server so the browser can send commands live
  3. Discover Govee devices on the local network (UDP multicast)
  4. Relay browser commands → Govee devices via UDP (port 4003)
  5. MQTT integration with Home Assistant:
       - Publish HA MQTT discovery so each device appears as a light entity
       - Subscribe to HA light command topics (on/off, brightness, effect)
       - Execute saved sequences when an effect is selected
       - Publish state back to HA after each command

MQTT topic structure (prefix = govee_studio by default):
  {prefix}/{device_id}/set       ← HA sends commands here
  {prefix}/{device_id}/state     ← bridge publishes state here
  homeassistant/light/{prefix}_{device_id}/config  ← discovery

WebSocket protocol (JSON):
  Browser → Bridge:
    {type: "discover"}
    {type: "send_frame",   device_ip, colors: [...], brightness}
    {type: "save_sequence", device_ip, name, sequence: {frames, loops, segmentCount, ...}}
    {type: "delete_sequence", device_ip, name}
    {type: "list_sequences", device_ip}
    {type: "play_sequence", device_ip, name}

  Bridge → Browser:
    {type: "devices",   devices: [...]}
    {type: "sequences", device_ip, sequences: [...]}
    {type: "ack",       ok, error?}
    {type: "state",     device_ip, ...}
"""

import asyncio
import json
import logging
import os
import socket
import struct
import time
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web
import aiomqtt
import websockets

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("hls")

# ─── Config ───────────────────────────────────────────────────────────────────
# HA supervisor injects MQTT_HOST etc. when services: [mqtt:need] is declared.
# Options from config.yaml are available as environment variables prefixed with
# their uppercased name (set via the supervisor's options injection).

def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()

MQTT_HOST     = _env("MQTT_HOST") or _env("OPTION_MQTT_HOST", "core-mosquitto")
MQTT_PORT     = int(_env("MQTT_PORT") or _env("OPTION_MQTT_PORT", "1883"))
MQTT_USER     = _env("MQTT_USERNAME") or _env("OPTION_MQTT_USERNAME", "")
MQTT_PASS     = _env("MQTT_PASSWORD") or _env("OPTION_MQTT_PASSWORD", "")
TOPIC_PREFIX  = _env("OPTION_TOPIC_PREFIX", "govee_studio")
SCAN_INTERVAL = int(_env("OPTION_SCAN_INTERVAL", "60"))
HTTP_PORT     = int(_env("INGRESS_PORT", "8099"))
WS_PORT       = 8765
DATA_DIR      = Path(_env("DATA_DIR", "/data"))
STATIC_DIR    = Path(__file__).parent / "static"

DATA_DIR.mkdir(parents=True, exist_ok=True)
DEVICES_FILE   = DATA_DIR / "devices.json"
SEQUENCES_FILE = DATA_DIR / "sequences.json"

# ─── Shared State ─────────────────────────────────────────────────────────────
devices: dict[str, dict] = {}      # device_id → {ip, sku, device_id, name, segments}
sequences: dict[str, dict] = {}    # device_id → {sequence_name → sequence_data}
ws_clients: set = set()
mqtt_client: aiomqtt.Client | None = None
device_states: dict[str, dict] = {}  # device_id → {on, brightness, effect}


# ─── Persistence ──────────────────────────────────────────────────────────────
def load_state() -> None:
    global devices, sequences
    if DEVICES_FILE.exists():
        try:
            devices = json.loads(DEVICES_FILE.read_text())
            log.info(f"Loaded {len(devices)} saved device(s)")
        except Exception as e:
            log.warning(f"Could not load devices: {e}")
    if SEQUENCES_FILE.exists():
        try:
            sequences = json.loads(SEQUENCES_FILE.read_text())
            log.info(f"Loaded sequences for {len(sequences)} device(s)")
        except Exception as e:
            log.warning(f"Could not load sequences: {e}")


def save_devices() -> None:
    DEVICES_FILE.write_text(json.dumps(devices, indent=2))


def save_sequences() -> None:
    SEQUENCES_FILE.write_text(json.dumps(sequences, indent=2))


# ─── UDP / Govee ──────────────────────────────────────────────────────────────
def udp_send(host: str, port: int, payload: dict) -> None:
    data = json.dumps(payload).encode()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(data, (host, port))
    log.debug(f"UDP → {host}:{port}  cmd={payload.get('msg',{}).get('cmd','?')}")


async def discover_devices_async(timeout: float = 3.0) -> list[dict]:
    scan_msg = json.dumps({"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}).encode()
    found = []

    loop = asyncio.get_event_loop()

    # Send multicast scan
    def _send():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            s.sendto(scan_msg, ("239.255.255.250", 4001))
            s.close()
        except Exception as e:
            log.warning(f"Discovery send failed: {e}")

    await loop.run_in_executor(None, _send)

    # Listen for replies
    def _recv():
        results = []
        try:
            recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            recv_sock.settimeout(timeout)
            recv_sock.bind(("", 4002))
            while True:
                try:
                    data, addr = recv_sock.recvfrom(4096)
                    msg = json.loads(data)
                    d = msg.get("msg", {}).get("data", {})
                    if d.get("ip"):
                        results.append(d)
                        log.info(f"Discovered: {d.get('sku','?')} @ {d.get('ip')}")
                except socket.timeout:
                    break
                except Exception:
                    pass
            recv_sock.close()
        except Exception as e:
            log.warning(f"Discovery recv failed: {e}")
        return results

    return await loop.run_in_executor(None, _recv)


def build_brightness_cmd(value: int) -> dict:
    return {"msg": {"cmd": "brightness", "data": {"value": max(1, min(100, value))}}}


def build_turn_cmd(on: bool) -> dict:
    return {"msg": {"cmd": "turn", "data": {"value": 1 if on else 0}}}


def build_ptreal_payload(colors: list[str], direction: int = 9, speed: int = 0) -> dict:
    """Build the Grafiti-mode ptReal UDP payload for per-segment color control."""

    def hex_to_rgb(h):
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    n = len(colors)
    if n == 0:
        return {}

    cmd = "01pc"
    cmd += "03"
    cmd += f"{direction:02x}"
    cmd += f"{speed:02x}"
    cmd += "00"       # bg intensity
    cmd += "000000"   # bg color
    cmd += f"{n:02x}"

    for i, color in enumerate(colors):
        r, g, b = hex_to_rgb(color)
        cmd += "01"
        cmd += f"{r:02x}{g:02x}{b:02x}"
        cmd += f"{i:02x}"

    # Packetize (17-byte chunks)
    chunks = [cmd[i:i+34] for i in range(0, len(cmd), 34)]
    chunks[0] = chunks[0].replace("pc", f"{len(chunks):02x}", 1)

    import base64
    packets = []
    for i, chunk in enumerate(chunks):
        if i < len(chunks) - 1:
            pkt = f"a3{i:02x}" + chunk
        else:
            pkt = "a3ff" + chunk
            pkt = pkt.ljust(38, "0")

        xor = 0
        for j in range(0, len(pkt), 2):
            xor ^= int(pkt[j:j+2], 16)
        pkt += f"{xor:02x}"

        raw = bytes(int(pkt[j:j+2], 16) for j in range(0, len(pkt), 2))
        packets.append(base64.b64encode(raw).decode())

    packets.append("MwUKIAMAAAAAAAAAAAAAAAAAAB8=")
    return {"msg": {"cmd": "ptReal", "data": {"command": packets}}}


# ─── MQTT ─────────────────────────────────────────────────────────────────────
def ha_discovery_payload(device: dict, effect_list: list[str]) -> tuple[str, dict]:
    """Return (topic, payload) for HA MQTT light discovery."""
    dev_id = device["device_id"].replace(":", "").lower()
    unique_id = f"hls_{dev_id}"
    topic = f"homeassistant/light/{unique_id}/config"
    payload = {
        "name": device.get("name") or f"Govee {device.get('sku', 'Light')}",
        "unique_id": unique_id,
        "object_id": unique_id,
        "schema": "json",
        "command_topic": f"{TOPIC_PREFIX}/{dev_id}/set",
        "state_topic": f"{TOPIC_PREFIX}/{dev_id}/state",
        "brightness": True,
        "brightness_scale": 100,
        "effect": True,
        "effect_list": effect_list or ["(none)"],
        "optimistic": False,
        "retain": True,
        "device": {
            "identifiers": [unique_id],
            "name": device.get("name") or f"Govee {device.get('sku', 'Light')}",
            "model": device.get("sku", "Unknown"),
            "manufacturer": "Govee",
            "via_device": "house_light_studio",
        },
    }
    return topic, payload


async def publish_discovery(client: aiomqtt.Client) -> None:
    for dev_id, device in devices.items():
        dev_sequences = list((sequences.get(dev_id) or {}).keys())
        topic, payload = ha_discovery_payload(device, dev_sequences)
        await client.publish(topic, json.dumps(payload), retain=True)
        log.info(f"Published HA discovery for {device.get('sku','?')} ({dev_id})")


async def publish_state(client: aiomqtt.Client, dev_id: str) -> None:
    state = device_states.get(dev_id, {"state": "ON", "brightness": 100})
    short_id = dev_id.replace(":", "").lower()
    topic = f"{TOPIC_PREFIX}/{short_id}/state"
    await client.publish(topic, json.dumps(state), retain=True)


async def handle_mqtt_command(client: aiomqtt.Client, dev_id: str, payload: dict) -> None:
    """Called when HA sends a command to a light entity."""
    device = devices.get(dev_id)
    if not device:
        log.warning(f"Command for unknown device: {dev_id}")
        return

    ip = device.get("ip")
    if not ip:
        log.warning(f"No IP for device {dev_id}")
        return

    current = device_states.setdefault(dev_id, {"state": "ON", "brightness": 100, "effect": None})

    # On / Off
    if "state" in payload:
        on = payload["state"].upper() == "ON"
        udp_send(ip, 4003, build_turn_cmd(on))
        current["state"] = "ON" if on else "OFF"

    # Brightness
    if "brightness" in payload:
        # HA sends 0–255, Govee wants 1–100
        pct = max(1, round(payload["brightness"] / 255 * 100))
        udp_send(ip, 4003, build_brightness_cmd(pct))
        current["brightness"] = payload["brightness"]

    # Effect = play a named sequence
    if "effect" in payload:
        effect_name = payload["effect"]
        dev_seqs = sequences.get(dev_id, {})
        seq = dev_seqs.get(effect_name)
        if seq and seq.get("frames"):
            first_frame = seq["frames"][0]
            colors = first_frame.get("colors", [])
            direction = seq.get("animDir", 9)
            speed = seq.get("animSpeed", 0)
            udp_payload = build_ptreal_payload(colors, direction, speed)
            udp_send(ip, 4003, udp_payload)
            current["effect"] = effect_name
            log.info(f"Playing effect '{effect_name}' on {ip}")
        else:
            log.warning(f"Effect '{effect_name}' not found for device {dev_id}")

    await publish_state(client, dev_id)
    # Broadcast state update to all browser clients
    await broadcast_ws({"type": "state", "device_id": dev_id, **current})


async def mqtt_loop() -> None:
    global mqtt_client
    retry_delay = 5
    while True:
        try:
            log.info(f"Connecting to MQTT at {MQTT_HOST}:{MQTT_PORT}...")
            async with aiomqtt.Client(
                hostname=MQTT_HOST,
                port=MQTT_PORT,
                username=MQTT_USER or None,
                password=MQTT_PASS or None,
                keepalive=30,
            ) as client:
                mqtt_client = client
                log.info("MQTT connected")
                retry_delay = 5

                # Publish discovery for all known devices
                await publish_discovery(client)

                # Subscribe to all device command topics
                await client.subscribe(f"{TOPIC_PREFIX}/+/set")
                log.info(f"Subscribed to {TOPIC_PREFIX}/+/set")

                async for message in client.messages:
                    try:
                        topic_parts = str(message.topic).split("/")
                        if len(topic_parts) >= 3 and topic_parts[-1] == "set":
                            short_id = topic_parts[-2]
                            # Reverse-map short_id → full device_id
                            dev_id = next(
                                (did for did in devices
                                 if did.replace(":", "").lower() == short_id),
                                None
                            )
                            if dev_id:
                                payload = json.loads(message.payload)
                                await handle_mqtt_command(client, dev_id, payload)
                    except Exception as e:
                        log.error(f"Error handling MQTT message: {e}")

        except Exception as e:
            log.warning(f"MQTT disconnected: {e}. Retrying in {retry_delay}s...")
            mqtt_client = None
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)


# ─── WebSocket ────────────────────────────────────────────────────────────────
async def broadcast_ws(msg: dict) -> None:
    if not ws_clients:
        return
    data = json.dumps(msg)
    await asyncio.gather(
        *[ws.send(data) for ws in list(ws_clients)],
        return_exceptions=True
    )


async def ws_handler(websocket) -> None:
    ws_clients.add(websocket)
    client_addr = websocket.remote_address
    log.info(f"Browser connected: {client_addr}")

    # Send current device list immediately
    await websocket.send(json.dumps({"type": "devices", "devices": list(devices.values())}))

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
                await handle_ws_message(websocket, msg)
            except Exception as e:
                log.error(f"WS error: {e}")
                await websocket.send(json.dumps({"type": "ack", "ok": False, "error": str(e)}))
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        ws_clients.discard(websocket)
        log.info(f"Browser disconnected: {client_addr}")


async def handle_ws_message(ws, msg: dict) -> None:
    t = msg.get("type")

    if t == "discover":
        found = await discover_devices_async()
        for d in found:
            dev_id = d.get("device", "")
            if dev_id:
                devices[dev_id] = {
                    "device_id": dev_id,
                    "ip": d.get("ip"),
                    "sku": d.get("sku"),
                    "name": d.get("sku"),
                }
        save_devices()
        if mqtt_client:
            await publish_discovery(mqtt_client)
        await ws.send(json.dumps({"type": "devices", "devices": list(devices.values())}))

    elif t == "send_frame":
        ip = msg.get("device_ip")
        colors = msg.get("colors", [])
        brightness = msg.get("brightness", 100)
        direction = msg.get("direction", 9)
        speed = msg.get("speed", 0)
        if ip and colors:
            payload = build_ptreal_payload(colors, direction, speed)
            udp_send(ip, 4003, payload)
            if brightness != 100:
                udp_send(ip, 4003, build_brightness_cmd(brightness))
        await ws.send(json.dumps({"type": "ack", "ok": True}))

    elif t == "save_sequence":
        dev_id = msg.get("device_id") or _ip_to_dev_id(msg.get("device_ip", ""))
        name = msg.get("name", "").strip()
        sequence = msg.get("sequence")
        if dev_id and name and sequence:
            sequences.setdefault(dev_id, {})[name] = sequence
            save_sequences()
            # Re-publish discovery with updated effect list
            if mqtt_client and dev_id in devices:
                await publish_discovery(mqtt_client)
            await ws.send(json.dumps({"type": "ack", "ok": True}))
        else:
            await ws.send(json.dumps({"type": "ack", "ok": False, "error": "Missing device_id, name, or sequence"}))

    elif t == "delete_sequence":
        dev_id = msg.get("device_id") or _ip_to_dev_id(msg.get("device_ip", ""))
        name = msg.get("name", "")
        if dev_id and name and dev_id in sequences:
            sequences[dev_id].pop(name, None)
            save_sequences()
            if mqtt_client and dev_id in devices:
                await publish_discovery(mqtt_client)
        await ws.send(json.dumps({"type": "ack", "ok": True}))

    elif t == "list_sequences":
        dev_id = msg.get("device_id") or _ip_to_dev_id(msg.get("device_ip", ""))
        dev_seqs = list((sequences.get(dev_id) or {}).keys())
        await ws.send(json.dumps({"type": "sequences", "device_id": dev_id, "sequences": dev_seqs}))

    elif t == "play_sequence":
        dev_id = msg.get("device_id") or _ip_to_dev_id(msg.get("device_ip", ""))
        name = msg.get("name", "")
        device = devices.get(dev_id)
        if device and dev_id in sequences and name in sequences[dev_id]:
            seq = sequences[dev_id][name]
            asyncio.create_task(_play_sequence(device["ip"], seq))
            await ws.send(json.dumps({"type": "ack", "ok": True}))
        else:
            await ws.send(json.dumps({"type": "ack", "ok": False, "error": "Sequence not found"}))

    else:
        await ws.send(json.dumps({"type": "ack", "ok": False, "error": f"Unknown message type: {t}"}))


def _ip_to_dev_id(ip: str) -> str:
    for dev_id, d in devices.items():
        if d.get("ip") == ip:
            return dev_id
    return ""


async def _play_sequence(ip: str, seq: dict) -> None:
    """Play a full sequence to a device (frame-by-frame with timing)."""
    frames = seq.get("frames", [])
    loops = seq.get("loops", [])
    direction = seq.get("animDir", 9)
    speed = seq.get("animSpeed", 0)

    # Build expanded frame order (respecting loops)
    order = _expand_sequence(frames, loops)

    for frame_idx in order:
        if frame_idx >= len(frames):
            continue
        frame = frames[frame_idx]
        colors = frame.get("colors", [])
        duration_ms = frame.get("duration", 500)
        if colors:
            payload = build_ptreal_payload(colors, direction, speed)
            udp_send(ip, 4003, payload)
        await asyncio.sleep(duration_ms / 1000)


def _expand_sequence(frames: list, loops: list, max_frames: int = 500) -> list[int]:
    """Expand frame indices respecting loop regions."""
    order = []
    loop_counts = {l["id"]: 0 for l in loops if "id" in l}
    i = 0
    while i < len(frames) and len(order) < max_frames:
        order.append(i)
        jumped = False
        for loop in loops:
            if loop.get("end") == i:
                max_count = loop.get("count", 1)
                lid = loop.get("id", "")
                current = loop_counts.get(lid, 0)
                max_reps = 999 if max_count < 0 else max_count
                if current < max_reps - 1:
                    loop_counts[lid] = current + 1
                    i = loop.get("start", 0)
                    jumped = True
                    break
                else:
                    loop_counts[lid] = 0
        if not jumped:
            i += 1
    return order


# ─── HTTP (serves the designer UI via HA ingress) ─────────────────────────────
async def http_index(request: web.Request) -> web.Response:
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return web.Response(
            text=index_path.read_text(),
            content_type="text/html"
        )
    return web.Response(text="<h1>House Light Studio</h1><p>index.html not found.</p>", content_type="text/html")


async def http_devices(request: web.Request) -> web.Response:
    return web.json_response(list(devices.values()))


async def http_sequences(request: web.Request) -> web.Response:
    dev_id = request.match_info.get("device_id", "")
    return web.json_response(list((sequences.get(dev_id) or {}).keys()))


async def start_http() -> None:
    app = web.Application()
    app.router.add_get("/", http_index)
    app.router.add_get("/index.html", http_index)
    app.router.add_get("/api/devices", http_devices)
    app.router.add_get("/api/sequences/{device_id}", http_sequences)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HTTP_PORT)
    await site.start()
    log.info(f"HTTP server on port {HTTP_PORT}")


# ─── Periodic Discovery ───────────────────────────────────────────────────────
async def periodic_discovery() -> None:
    """Re-scan for devices every SCAN_INTERVAL seconds."""
    while True:
        await asyncio.sleep(SCAN_INTERVAL)
        log.info("Running periodic device discovery...")
        found = await discover_devices_async(timeout=3.0)
        updated = False
        for d in found:
            dev_id = d.get("device", "")
            if dev_id and (dev_id not in devices or devices[dev_id].get("ip") != d.get("ip")):
                devices[dev_id] = {
                    "device_id": dev_id,
                    "ip": d.get("ip"),
                    "sku": d.get("sku"),
                    "name": d.get("sku"),
                }
                updated = True
        if updated:
            save_devices()
            if mqtt_client:
                await publish_discovery(mqtt_client)
            await broadcast_ws({"type": "devices", "devices": list(devices.values())})


# ─── Entry Point ──────────────────────────────────────────────────────────────
async def main() -> None:
    log.info("=== House Light Studio Bridge starting ===")
    log.info(f"MQTT: {MQTT_HOST}:{MQTT_PORT}  |  HTTP: {HTTP_PORT}  |  WS: {WS_PORT}")
    log.info(f"Data dir: {DATA_DIR}")

    load_state()

    # Run initial discovery
    log.info("Running initial device discovery...")
    found = await discover_devices_async(timeout=4.0)
    for d in found:
        dev_id = d.get("device", "")
        if dev_id:
            devices.setdefault(dev_id, {
                "device_id": dev_id,
                "ip": d.get("ip"),
                "sku": d.get("sku"),
                "name": d.get("sku"),
            })
    if found:
        save_devices()
    log.info(f"Total devices known: {len(devices)}")

    # Start all services concurrently
    ws_server = await websockets.serve(ws_handler, "0.0.0.0", WS_PORT)
    log.info(f"WebSocket server on port {WS_PORT}")

    await asyncio.gather(
        start_http(),
        mqtt_loop(),
        periodic_discovery(),
    )


if __name__ == "__main__":
    asyncio.run(main())
