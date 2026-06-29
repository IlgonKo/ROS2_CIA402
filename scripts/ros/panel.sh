#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker/ros/compose.yaml"
ENV_FILE="${PROJECT_ROOT}/.env"
DISPLAY_VALUE="${DISPLAY:-:0}"
BUILD_PANEL=0

case "${1:-}" in
  "")
    ;;
  --build)
    BUILD_PANEL=1
    ;;
  *)
    echo "Usage: bash scripts/ros/panel.sh [--build]"
    exit 2
    ;;
esac

cd "${PROJECT_ROOT}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}"
  echo "Create it from .env.example first."
  echo "  cp .env.example .env"
  exit 1
fi

if [[ "${BUILD_PANEL}" == "1" ]]; then
  echo "Building ROS Control Panel image"
  docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build ros_control_panel
fi

if command -v xhost >/dev/null 2>&1; then
  xhost +local:root >/dev/null
fi

exec docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" --profile panel run --rm \
  -e DISPLAY="${DISPLAY_VALUE}" \
  ros_control_panel
