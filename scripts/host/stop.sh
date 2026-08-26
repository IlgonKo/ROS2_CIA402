#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker/motion_server/compose.yaml"
ENV_FILE="${PROJECT_ROOT}/.env"
source "${PROJECT_ROOT}/scripts/env.sh"

cd "${PROJECT_ROOT}"

if [[ -f "${ENV_FILE}" ]]; then
  COMPOSE_ENV_FILE="$(prepare_compose_env_file "${PROJECT_ROOT}")"
  docker compose -f "${COMPOSE_FILE}" --env-file "${COMPOSE_ENV_FILE}" stop motion_server
  docker compose -f "${COMPOSE_FILE}" --env-file "${COMPOSE_ENV_FILE}" rm -f motion_server
else
  docker compose -f "${COMPOSE_FILE}" stop motion_server
  docker compose -f "${COMPOSE_FILE}" rm -f motion_server
fi
echo "Stopped Motion Server container."
