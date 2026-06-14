#!/usr/bin/env bash
# Avatar — build and run the single container (macOS / Linux).
# Stops any existing 'avatar' container, rebuilds the image, then runs it on :8000
# with the project-root .env. Open http://localhost:8000 (admin at /admin).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

IMAGE="avatar"
CONTAINER="avatar"
PORT="8000"

command -v docker >/dev/null 2>&1 || { echo "Docker not found — install Docker and ensure it's running."; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker daemon is not running — start Docker Desktop first."; exit 1; }

if [ ! -f "$REPO_ROOT/.env" ]; then
  echo "Missing .env at repo root ($REPO_ROOT/.env). Copy .env.example to .env and fill it in."
  exit 1
fi

# 1. Stop and remove any existing container (ignore if absent).
if [ -n "$(docker ps -aq -f name="^${CONTAINER}$")" ]; then
  echo "Stopping existing '${CONTAINER}' container..."
  docker rm -f "$CONTAINER" >/dev/null
fi

# 2. Rebuild the image.
echo "Building image '${IMAGE}'..."
docker build -t "$IMAGE" -f "$REPO_ROOT/Dockerfile" "$REPO_ROOT"

# 3. Run it with the root .env.
echo "Starting '${CONTAINER}' on http://localhost:${PORT} ..."
docker run -d \
  --name "$CONTAINER" \
  -p "${PORT}:8000" \
  --env-file "$REPO_ROOT/.env" \
  --restart unless-stopped \
  "$IMAGE"

echo "Avatar is running:"
echo "  Visitor: http://localhost:${PORT}"
echo "  Admin:   http://localhost:${PORT}/admin"
echo "Logs: docker logs -f ${CONTAINER}   |   Stop: ./scripts/stop_mac.sh"
