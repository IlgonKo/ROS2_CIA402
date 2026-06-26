#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker/ros/compose.yaml"
ENV_FILE="${PROJECT_ROOT}/.env"

cd "${PROJECT_ROOT}"

if [[ -f "${ENV_FILE}" ]]; then
  docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" down --remove-orphans
else
  docker compose -f "${COMPOSE_FILE}" down --remove-orphans
fi

docker rm -f ros2_cia402_bridge 2>/dev/null || true
docker rm -f ros2_cia402_control_panel 2>/dev/null || true
docker rm -f ros2_cia402_moveit 2>/dev/null || true

echo "Stopped ROS Bridge/Control Panel/MoveIt containers."
