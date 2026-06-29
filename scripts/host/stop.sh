#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker/axis_server/compose.yaml"
ENV_FILE="${PROJECT_ROOT}/.env"

cd "${PROJECT_ROOT}"

if [[ -f "${ENV_FILE}" ]]; then
  docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" stop axis_server
  docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" rm -f axis_server
else
  docker compose -f "${COMPOSE_FILE}" stop axis_server
  docker compose -f "${COMPOSE_FILE}" rm -f axis_server
fi
docker rm -f ros_cia402_axis_server 2>/dev/null || true
docker rm -f ros2_cia402_pysoem_host 2>/dev/null || true

echo "Stopped Axis Server container."
