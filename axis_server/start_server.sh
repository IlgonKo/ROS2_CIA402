#!/usr/bin/env bash
set -euo pipefail

INTERFACE="${PYSOEM_INTERFACE:-enp1s0}"
BACKEND="${AXIS_SERVER_BACKEND:-pysoem}"
AXIS_COUNT="${PYSOEM_AXIS_COUNT:-1}"
PORT="${PYSOEM_AXIS_SERVER_PORT:-15000}"
CYCLE_TIME="${PYSOEM_CYCLE_TIME:-0.01}"
MAX_VELOCITY="${PYSOEM_MAX_VELOCITY:-50.0}"
ACCELERATION="${PYSOEM_ACCELERATION:-100.0}"
DECELERATION="${PYSOEM_DECELERATION:-100.0}"
CSP_COUNTS_PER_UNIT="${PYSOEM_CSP_COUNTS_PER_UNIT:-1.0}"
DERIVED_VELOCITY_ALPHA="${PYSOEM_DERIVED_VELOCITY_ALPHA:-0.2}"
MOTION_MODE="${PYSOEM_MOTION_MODE:-pp}"

echo "Starting Axis Server"
echo "Backend=${BACKEND}"
echo "Interface=${INTERFACE}"
echo "AxisCount=${AXIS_COUNT}"
echo "Port=${PORT}"
echo "CycleTime=${CYCLE_TIME}"
echo "MaxVelocity=${MAX_VELOCITY}"
echo "Acceleration=${ACCELERATION}"
echo "Deceleration=${DECELERATION}"
echo "CspCountsPerUnit=${CSP_COUNTS_PER_UNIT}"
echo "DerivedVelocityAlpha=${DERIVED_VELOCITY_ALPHA}"
echo "MotionMode=${MOTION_MODE}"

exec python3 -B /workspace/axis_server/server.py \
  "${INTERFACE}" \
  --backend "${BACKEND}" \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --cycle-time "${CYCLE_TIME}" \
  --max-velocity "${MAX_VELOCITY}" \
  --acceleration "${ACCELERATION}" \
  --deceleration "${DECELERATION}" \
  --csp-counts-per-unit "${CSP_COUNTS_PER_UNIT}" \
  --derived-velocity-alpha "${DERIVED_VELOCITY_ALPHA}" \
  --axis-count "${AXIS_COUNT}" \
  --motion-mode "${MOTION_MODE}"
