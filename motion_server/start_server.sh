#!/usr/bin/env bash
set -euo pipefail

INTERFACE="${PYSOEM_INTERFACE:-enp1s0}"
BACKEND="${MOTION_SERVER_BACKEND:-pysoem}"
SERVER_MODE="${MOTION_SERVER_MODE:-basic}"
BUS="${MOTION_SERVER_BUS:-cmmt_as}"
PORT="${MOTION_SERVER_PORT:-15000}"
CYCLE_TIME="${PYSOEM_CYCLE_TIME:-0.01}"
SPIN_WAIT_TIME="${PYSOEM_SPIN_WAIT_TIME:-0.00015}"
CPUSET="${MOTION_SERVER_CPUSET:-}"
SYNC_MODE="${PYSOEM_SYNC_MODE:-0}"
DC_ENABLED="${PYSOEM_DC_ENABLED:-0}"
DC_SYNC0_SHIFT_TIME_NS="${PYSOEM_DC_SYNC0_SHIFT_TIME_NS:-0}"
DC_PHASE_LOCK="${PYSOEM_DC_PHASE_LOCK:-0}"
DC_ABSOLUTE_SHIFT="${PYSOEM_DC_ABSOLUTE_SHIFT:-0}"
DC_PHASE_OFFSET_NS="${PYSOEM_DC_PHASE_OFFSET_NS:-800000}"
DC_PHASE_KP="${PYSOEM_DC_PHASE_KP:-0.05}"
DC_PHASE_KI="${PYSOEM_DC_PHASE_KI:-0.0005}"
DC_PHASE_MAX_CORRECTION="${PYSOEM_DC_PHASE_MAX_CORRECTION:-0.001}"
MAX_VELOCITY="${MOTION_SERVER_MAX_VELOCITY:-50.0}"
ACCELERATION="${MOTION_SERVER_ACCELERATION:-100.0}"
DECELERATION="${MOTION_SERVER_DECELERATION:-100.0}"
JERK="${MOTION_SERVER_JERK:-1000.0}"
PP_JERK="${MOTION_SERVER_PP_JERK:-100000}"
CSP_PROFILE="${MOTION_SERVER_CSP_PROFILE:-quintic}"
CSP_INTERPOLATION_MODE="${MOTION_SERVER_CSP_INTERPOLATION_MODE:-1}"
CSP_VELOCITY_OFFSET="${MOTION_SERVER_CSP_VELOCITY_OFFSET:-0}"
DERIVED_VELOCITY_ALPHA="${MOTION_SERVER_DERIVED_VELOCITY_ALPHA:-0.2}"
MOTION_MODE="${MOTION_SERVER_MOTION_MODE:-pp}"
COMMAND_LOGS="${MOTION_SERVER_COMMAND_LOGS:-0}"
STATUS_LOGS="${MOTION_SERVER_STATUS_LOGS:-0}"

echo "Starting Axis Server"
echo "Backend=${BACKEND}"
echo "ServerMode=${SERVER_MODE}"
echo "Bus=${BUS}"
echo "Interface=${INTERFACE}"
echo "Port=${PORT}"
echo "CycleTime=${CYCLE_TIME}"
echo "SpinWaitTime=${SPIN_WAIT_TIME}"
echo "CpuSet=${CPUSET:-all}"
echo "SyncMode=${SYNC_MODE}"
echo "DcEnabled=${DC_ENABLED}"
echo "DcSync0ShiftTimeNs=${DC_SYNC0_SHIFT_TIME_NS}"
echo "DcPhaseLock=${DC_PHASE_LOCK}"
echo "DcAbsoluteShift=${DC_ABSOLUTE_SHIFT}"
echo "DcPhaseOffsetNs=${DC_PHASE_OFFSET_NS}"
echo "DcPhaseKp=${DC_PHASE_KP}"
echo "DcPhaseKi=${DC_PHASE_KI}"
echo "DcPhaseMaxCorrection=${DC_PHASE_MAX_CORRECTION}"
echo "CspProfile=${CSP_PROFILE}"
echo "CspInterpolationMode=${CSP_INTERPOLATION_MODE}"
echo "CspVelocityOffset=${CSP_VELOCITY_OFFSET}"
echo "DerivedVelocityAlpha=${DERIVED_VELOCITY_ALPHA}"
echo "MotionMode=${MOTION_MODE}"
echo "CommandLogs=${COMMAND_LOGS}"
echo "StatusLogs=${STATUS_LOGS}"

SERVER_CMD=(
  python3 -B /workspace/motion_server/server.py
  "${INTERFACE}" \
  --backend "${BACKEND}" \
  --server-mode "${SERVER_MODE}" \
  --bus "${BUS}" \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --cycle-time "${CYCLE_TIME}" \
  --spin-wait-time "${SPIN_WAIT_TIME}" \
  --sync-mode "${SYNC_MODE}" \
  --dc-sync0-shift-time "${DC_SYNC0_SHIFT_TIME_NS}" \
  --dc-phase-offset "${DC_PHASE_OFFSET_NS}" \
  --dc-phase-kp "${DC_PHASE_KP}" \
  --dc-phase-ki "${DC_PHASE_KI}" \
  --dc-phase-max-correction "${DC_PHASE_MAX_CORRECTION}" \
  --max-velocity "${MAX_VELOCITY}" \
  --acceleration "${ACCELERATION}" \
  --deceleration "${DECELERATION}" \
  --jerk "${JERK}" \
  --pp-jerk "${PP_JERK}" \
  --csp-profile "${CSP_PROFILE}" \
  --csp-interpolation-mode "${CSP_INTERPOLATION_MODE}" \
  --derived-velocity-alpha "${DERIVED_VELOCITY_ALPHA}" \
  --motion-mode "${MOTION_MODE}"
)

if [[ "${DC_ENABLED}" == "1" ]]; then
  SERVER_CMD+=(--dc-enabled)
fi

if [[ "${DC_PHASE_LOCK}" == "1" ]]; then
  SERVER_CMD+=(--dc-phase-lock)
fi

if [[ "${DC_ABSOLUTE_SHIFT}" == "1" ]]; then
  SERVER_CMD+=(--dc-absolute-shift)
fi

if [[ "${CSP_VELOCITY_OFFSET}" == "1" ]]; then
  SERVER_CMD+=(--csp-velocity-offset)
fi

if [[ -n "${CPUSET}" ]]; then
  exec taskset -c "${CPUSET}" "${SERVER_CMD[@]}"
fi

exec "${SERVER_CMD[@]}"
