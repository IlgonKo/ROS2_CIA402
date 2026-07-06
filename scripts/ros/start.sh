#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker/ros/compose.yaml"
ENV_FILE="${PROJECT_ROOT}/.env"
source "${PROJECT_ROOT}/scripts/env.sh"
BUILD_ROS=0

case "${1:-}" in
  "")
    ;;
  --build)
    BUILD_ROS=1
    ;;
  *)
    echo "Usage: bash scripts/ros/start.sh [--build]"
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

COMPOSE_ENV_FILE="$(prepare_compose_env_file "${PROJECT_ROOT}")"

echo "Using env file: ${ENV_FILE}"
echo "Using compose env file: ${COMPOSE_ENV_FILE}"
grep -E '^(AXIS_SERVER_HOST|AXIS_SERVER_PORT|ROS_BRIDGE_AUTO_REQUEST_AUTHORITY|PYSOEM_AXIS_COUNT|PYSOEM_DEVICE|ROS2_CIA402_AXIS_NAMES|PYSOEM_CSP_COUNTS_PER_UNIT)=' "${COMPOSE_ENV_FILE}" || true

if [[ "${BUILD_ROS}" == "1" ]]; then
  echo "Building ROS Bridge image"
  docker compose -f "${COMPOSE_FILE}" --env-file "${COMPOSE_ENV_FILE}" build ros_bridge
fi

docker compose -f "${COMPOSE_FILE}" --env-file "${COMPOSE_ENV_FILE}" up -d ros_bridge

echo "ROS Bridge started in background."
echo "Logs:"
echo "  docker logs -f ros2_cia402_bridge"
