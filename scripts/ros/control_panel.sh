#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker/ros/compose.yaml"
ENV_FILE="${PROJECT_ROOT}/.env"
BUILD_ROS=0

case "${1:-}" in
  "")
    ;;
  --build)
    BUILD_ROS=1
    ;;
  *)
    echo "Usage: bash scripts/ros/control_panel.sh [--build]"
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

if [[ "${BUILD_ROS}" == "1" ]]; then
  echo "Building ROS Control Panel image"
  docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build ros_control_panel
fi

exec docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" run --rm ros_control_panel
