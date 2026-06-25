#!/usr/bin/env bash
set -euo pipefail

INTERFACE="${PYSOEM_INTERFACE:-enp1s0}"
BACKEND="${AXIS_SERVER_BACKEND:-pysoem}"
AXIS_COUNT="${PYSOEM_AXIS_COUNT:-1}"
PORT="${PYSOEM_AXIS_SERVER_PORT:-15000}"
CYCLE_TIME="${PYSOEM_CYCLE_TIME:-0.01}"
CSP_COUNTS_PER_UNIT="${PYSOEM_CSP_COUNTS_PER_UNIT:-1.0}"
DERIVED_VELOCITY_ALPHA="${PYSOEM_DERIVED_VELOCITY_ALPHA:-0.2}"
MOTION_MODE="${PYSOEM_MOTION_MODE:-pp}"
START_PANEL="${PYSOEM_START_CONTROL_PANEL:-1}"

SERVER_PID=""
PANEL_PID=""

cleanup() {
  if [[ -n "${PANEL_PID}" ]]; then
    kill "${PANEL_PID}" 2>/dev/null || true
  fi
  if [[ -n "${SERVER_PID}" ]]; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

echo "Starting Axis Server"
echo "Backend=${BACKEND}"
echo "Interface=${INTERFACE}"
echo "AxisCount=${AXIS_COUNT}"
echo "Port=${PORT}"
echo "CycleTime=${CYCLE_TIME}"
echo "CspCountsPerUnit=${CSP_COUNTS_PER_UNIT}"
echo "DerivedVelocityAlpha=${DERIVED_VELOCITY_ALPHA}"
echo "MotionMode=${MOTION_MODE}"

python3 -B /workspace/axis_server/server.py \
  "${INTERFACE}" \
  --backend "${BACKEND}" \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --cycle-time "${CYCLE_TIME}" \
  --csp-counts-per-unit "${CSP_COUNTS_PER_UNIT}" \
  --derived-velocity-alpha "${DERIVED_VELOCITY_ALPHA}" \
  --axis-count "${AXIS_COUNT}" \
  --motion-mode "${MOTION_MODE}" &
SERVER_PID="$!"

sleep 1

if [[ "${START_PANEL}" == "1" ]]; then
  if [[ -n "${DISPLAY:-}" && -d /tmp/.X11-unix ]]; then
    echo "Starting Axis Server Control Panel"
    python3 -B /workspace/axis_server/control_panel.py &
    PANEL_PID="$!"
  else
    echo "Skipping Control Panel: DISPLAY or /tmp/.X11-unix is not available"
  fi
fi

wait "${SERVER_PID}"
