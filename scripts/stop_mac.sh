#!/usr/bin/env bash
# Avatar — stop and remove the running container (macOS / Linux).
set -euo pipefail

CONTAINER="avatar"

command -v docker >/dev/null 2>&1 || { echo "Docker not found."; exit 1; }

if [ -n "$(docker ps -aq -f name="^${CONTAINER}$")" ]; then
  echo "Stopping and removing '${CONTAINER}'..."
  docker rm -f "$CONTAINER" >/dev/null
  echo "Stopped."
else
  echo "No '${CONTAINER}' container is running."
fi
