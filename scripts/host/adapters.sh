#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker/axis_server/compose.yaml"

cd "${PROJECT_ROOT}"
docker compose -f "${COMPOSE_FILE}" run --rm --no-deps axis_server \
  python3 -B /workspace/diagnostics/list_pysoem_adapters.py
