#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker/axis_server/compose.yaml"
ENV_FILE="${PROJECT_ROOT}/.env"
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
  echo "Create it from .env.example, then edit AXIS_SERVER_BACKEND and PYSOEM_AXIS_COUNT."
  echo "  cp .env.example .env"
  exit 1
fi

echo "Using env file: ${ENV_FILE}"
grep -E '^(AXIS_SERVER_BACKEND|PYSOEM_AXIS_COUNT|PYSOEM_INTERFACE)=' "${ENV_FILE}" || true

echo "Stopping existing Axis Server containers"
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" down --remove-orphans
docker rm -f ros_cia402_axis_server 2>/dev/null || true
docker rm -f ros2_cia402_pysoem_host 2>/dev/null || true

if [[ "${BUILD_SERVER}" == "1" ]]; then
  echo "Building Axis Server image"
  docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build axis_server
fi

echo "Starting Axis Server container"
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d axis_server

echo "Started in background."
echo "Logs:"
echo "  docker logs -f ros_cia402_axis_server"
