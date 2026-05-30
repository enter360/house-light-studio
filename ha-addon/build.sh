#!/usr/bin/env bash
# Stages files needed by the Docker build (which cannot access parent directories)
# then builds the add-on image for local testing.
#
# Usage: ./build.sh [--push] [--arch amd64|aarch64]
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

echo "→ Staging index.html into ha-addon/static/"
mkdir -p "$SCRIPT_DIR/static"
cp "$REPO_ROOT/index.html" "$SCRIPT_DIR/static/index.html"

echo "→ Building Docker image..."
docker build \
  --build-arg BUILD_FROM="ghcr.io/hassio-addons/base:latest" \
  -t house-light-studio-addon:dev \
  "$SCRIPT_DIR"

echo "✓ Build complete: house-light-studio-addon:dev"
echo ""
echo "Run locally:"
echo "  docker run --rm -p 8099:8099 -p 8765:8765 \\"
echo "    -e MQTT_HOST=192.168.1.x -e MQTT_PORT=1883 \\"
echo "    -v \$(pwd)/data:/data \\"
echo "    house-light-studio-addon:dev"
