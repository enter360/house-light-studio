#!/usr/bin/env python3
"""
House Light Studio — WebSocket-to-UDP Bridge

Allows the browser app to send UDP commands directly to Govee lights
by relaying messages through this local bridge server.

Usage:
    pip install websockets
    python3 udp_bridge.py

Then enable "Local Bridge" in the app settings and set the bridge URL
to ws://localhost:8765

The browser sends JSON: { "host": "192.168.1.x", "port": 4003, "payload": {...} }
The bridge forwards payload as UDP to host:port.
"""

import asyncio
import json
import socket
import argparse
import logging
from datetime import datetime

try:
    import websockets
except ImportError:
    print("Missing dependency: pip install websockets")
    raise

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("udp_bridge")


def send_udp(host: str, port: int, data: bytes) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(data, (host, port))


async def handler(websocket):
    client = websocket.remote_address
    log.info(f"Client connected: {client}")
    try:
        async for message in websocket:
            try:
                msg = json.loads(message)
                host = msg.get("host", "")
                port = int(msg.get("port", 4003))
                payload = msg.get("payload")

                if not host or not payload:
                    await websocket.send(json.dumps({"ok": False, "error": "Missing host or payload"}))
                    continue

                data = json.dumps(payload).encode()
                send_udp(host, port, data)
                log.info(f"→ UDP {host}:{port}  cmd={payload.get('msg',{}).get('cmd','?')}")
                await websocket.send(json.dumps({"ok": True}))

            except Exception as e:
                log.error(f"Error handling message: {e}")
                await websocket.send(json.dumps({"ok": False, "error": str(e)}))

    except websockets.exceptions.ConnectionClosed:
        log.info(f"Client disconnected: {client}")


async def discover_devices(multicast_group="239.255.255.250", port=4001, timeout=3.0):
    """Send a scan broadcast and collect responses."""
    scan_msg = json.dumps({"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}).encode()
    devices = []

    # Send multicast
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        s.sendto(scan_msg, (multicast_group, port))

    # Listen for replies on port 4002
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock.settimeout(timeout)
    recv_sock.bind(("", 4002))
    log.info(f"Listening for device responses on port 4002 (timeout {timeout}s)...")
    try:
        while True:
            data, addr = recv_sock.recvfrom(4096)
            try:
                msg = json.loads(data)
                device_data = msg.get("msg", {}).get("data", {})
                log.info(f"Found device: {device_data}")
                devices.append(device_data)
            except Exception:
                pass
    except socket.timeout:
        pass
    finally:
        recv_sock.close()

    return devices


async def main(host, port):
    log.info(f"House Light Studio UDP Bridge starting on ws://{host}:{port}")
    log.info("Open index.html and enable 'Local Bridge' in device settings")

    async with websockets.serve(handler, host, port):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebSocket-to-UDP bridge for House Light Studio")
    parser.add_argument("--host", default="0.0.0.0", help="WebSocket bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket port (default: 8765)")
    parser.add_argument("--discover", action="store_true", help="Run device discovery and exit")
    args = parser.parse_args()

    if args.discover:
        devices = asyncio.run(discover_devices())
        print(f"\nFound {len(devices)} device(s):")
        for d in devices:
            print(f"  {d.get('sku','?')}  {d.get('ip','?')}  ({d.get('device','?')})")
    else:
        asyncio.run(main(args.host, args.port))
