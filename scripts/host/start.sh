#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker/axis_server/compose.yaml"

cd "${PROJECT_ROOT}"

if command -v xhost >/dev/null 2>&1; then
  xhost +local:root >/dev/null || true
fi

echo "Stopping existing PySOEM axis server container"
docker compose -f "${COMPOSE_FILE}" down --remove-orphans
docker rm -f ros_cia402_axis_server 2>/dev/null || true
docker rm -f ros2_cia402_pysoem_host 2>/dev/null || true

echo "Starting PySOEM axis server container"
docker compose -f "${COMPOSE_FILE}" up -d --build axis_server

echo "Started in background."
echo "Logs:"
echo "  docker logs -f ros_cia402_axis_server"
