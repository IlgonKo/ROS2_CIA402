#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker/ros/compose.yaml"
ENV_FILE="${PROJECT_ROOT}/.env"

cd "${PROJECT_ROOT}"

if [[ -f "${ENV_FILE}" ]]; then
  docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" stop ros_bridge
  docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" rm -f ros_bridge
else
  docker compose -f "${COMPOSE_FILE}" stop ros_bridge
  docker compose -f "${COMPOSE_FILE}" rm -f ros_bridge
fi

docker rm -f ros2_cia402_bridge 2>/dev/null || true

echo "Stopped ROS Bridge container."
