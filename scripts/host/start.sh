#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker/motion_server/compose.yaml"
ENV_FILE="${PROJECT_ROOT}/.env"
source "${PROJECT_ROOT}/scripts/env.sh"
BUILD_SERVER=0

case "${1:-}" in
  "")
    ;;
  --build)
    BUILD_SERVER=1
    ;;
  *)
    echo "Usage: bash scripts/host/start.sh [--build]"
    exit 2
    ;;
esac

cd "${PROJECT_ROOT}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}"
  echo "Create it from .env.example, then edit MOTION_SERVER_BACKEND and MOTION_SERVER_BUS."
  echo "  cp .env.example .env"
  exit 1
fi

COMPOSE_ENV_FILE="$(prepare_compose_env_file "${PROJECT_ROOT}")"

echo "Using env file: ${ENV_FILE}"
echo "Using compose env file: ${COMPOSE_ENV_FILE}"
grep -E '^(MOTION_SERVER_BACKEND|MOTION_SERVER_BUS|MOTION_SERVER_DEVICE_CONFIG_ROOT|PYSOEM_INTERFACE|MOCK_AXIS_TYPES|MOCK_AXIS_USER_UNITS)=' "${COMPOSE_ENV_FILE}" || true

echo "Stopping existing Motion Server containers"
docker compose -f "${COMPOSE_FILE}" --env-file "${COMPOSE_ENV_FILE}" stop motion_server
docker compose -f "${COMPOSE_FILE}" --env-file "${COMPOSE_ENV_FILE}" rm -f motion_server
docker rm -f ros_cia402_motion_server 2>/dev/null || true
docker rm -f ros2_cia402_pysoem_host 2>/dev/null || true

if [[ "${BUILD_SERVER}" == "1" ]]; then
  echo "Building Motion Server image"
  docker compose -f "${COMPOSE_FILE}" --env-file "${COMPOSE_ENV_FILE}" build motion_server
fi

echo "Starting Motion Server container"
docker compose -f "${COMPOSE_FILE}" --env-file "${COMPOSE_ENV_FILE}" up -d motion_server

echo "Started in background."
echo "Logs:"
echo "  docker logs -f ros_cia402_motion_server"
