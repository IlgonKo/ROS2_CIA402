#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${PYSOEM_CONTAINER_NAME:-ros_cia402_axis_server}"
DISPLAY_VALUE="${DISPLAY:-:0}"

if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
  echo "Container '${CONTAINER_NAME}' is not running."
  echo "Start it first:"
  echo "  bash scripts/host/start.sh"
  exit 1
fi

if command -v xhost >/dev/null 2>&1; then
  xhost +local:root >/dev/null
fi

exec docker exec \
  -e DISPLAY="${DISPLAY_VALUE}" \
  -e PYSOEM_SERVER_HOST="${PYSOEM_SERVER_HOST:-127.0.0.1}" \
  "${CONTAINER_NAME}" \
  python3 -B /workspace/axis_server/control_panel.py
