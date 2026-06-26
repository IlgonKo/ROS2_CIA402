#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker/axis_server/compose.yaml"
ENV_FILE="${PROJECT_ROOT}/.env"
SERVER_CONTAINER_NAME="${PYSOEM_CONTAINER_NAME:-ros_cia402_axis_server}"
DISPLAY_VALUE="${DISPLAY:-:0}"
BUILD_PANEL=0

case "${1:-}" in
  "")
    ;;
  --build)
    BUILD_PANEL=1
    ;;
  *)
    echo "Usage: bash scripts/host/panel.sh [--build]"
    exit 2
    ;;
esac

if ! docker ps --format '{{.Names}}' | grep -qx "${SERVER_CONTAINER_NAME}"; then
  echo "Container '${SERVER_CONTAINER_NAME}' is not running."
  echo "Start it first:"
  echo "  bash scripts/host/start.sh"
  exit 1
fi

if command -v xhost >/dev/null 2>&1; then
  xhost +local:root >/dev/null
fi

cd "${PROJECT_ROOT}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}"
  echo "Create it from .env.example, then edit AXIS_SERVER_BACKEND and PYSOEM_AXIS_COUNT."
  echo "  cp .env.example .env"
  exit 1
fi

if [[ "${BUILD_PANEL}" == "1" ]]; then
  docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build axis_panel
fi

exec docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" run --rm \
  -e DISPLAY="${DISPLAY_VALUE}" \
  -e PYSOEM_SERVER_HOST="${PYSOEM_SERVER_HOST:-127.0.0.1}" \
  axis_panel
