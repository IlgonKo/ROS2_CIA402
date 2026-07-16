import argparse
import os
from pathlib import Path

from device import available_device_names, get_device_profile


def load_project_env_defaults():
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(
            key.strip(),
            value.strip().strip('"').strip("'"),
        )


load_project_env_defaults()


AXIS_SERVER_MODES = ("basic", "advanced")
AXIS_SERVER_MODE = os.environ.get("AXIS_SERVER_MODE", "basic").strip().lower()
DEFAULT_CYCLE_TIME = float(os.environ.get("PYSOEM_CYCLE_TIME", "0.01"))
DEFAULT_SPIN_WAIT_TIME = float(os.environ.get("PYSOEM_SPIN_WAIT_TIME", "0.00015"))
DERIVED_VELOCITY_ALPHA = float(
    os.environ.get("PYSOEM_DERIVED_VELOCITY_ALPHA", "0.2")
)
FEEDBACK_PERIOD = 0.05
STATUS_LOG_PERIOD = float(os.environ.get("PYSOEM_STATUS_LOG_PERIOD", "1.0"))
AXIS_SERVER_COMMAND_LOGS = os.environ.get(
    "AXIS_SERVER_COMMAND_LOGS",
    "0",
).strip() == "1"
CYCLE_STATS_LOGS = os.environ.get("PYSOEM_CYCLE_STATS_LOGS", "1").strip() == "1"
CYCLE_STATS_PERIOD = float(os.environ.get("PYSOEM_CYCLE_STATS_PERIOD", "1.0"))
TX_HISTORY_LENGTH = int(os.environ.get("PYSOEM_TX_HISTORY_LENGTH", "16"))
TRAJECTORY_DEBUG_LOGS = os.environ.get(
    "PYSOEM_TRAJECTORY_DEBUG_LOGS",
    "0",
).strip() == "1"
TRAJECTORY_SNAPSHOT_LOGS = os.environ.get(
    "PYSOEM_TRAJECTORY_SNAPSHOT_LOGS",
    "0",
).strip() == "1"
ROS_BRIDGE_COMMAND_LOGS = os.environ.get(
    "ROS_BRIDGE_COMMAND_LOGS",
    "0",
).strip() == "1"
VELOCITY_ANOMALY_LOGS = os.environ.get(
    "PYSOEM_VELOCITY_ANOMALY_LOGS",
    "0",
).strip() == "1"
CSP_COMMAND_STEP_LOGS = os.environ.get(
    "PYSOEM_CSP_COMMAND_STEP_LOGS",
    "0",
).strip() == "1"
VELOCITY_ANOMALY_THRESHOLD = float(
    os.environ.get("PYSOEM_VELOCITY_ANOMALY_THRESHOLD", "15.0")
)
VELOCITY_JUMP_THRESHOLD = float(
    os.environ.get("PYSOEM_VELOCITY_JUMP_THRESHOLD", "15.0")
)
VELOCITY_ANOMALY_LOG_PERIOD = float(
    os.environ.get("PYSOEM_VELOCITY_ANOMALY_LOG_PERIOD", "0.05")
)
POSITION_FEEDBACK_LAG_LOGS = os.environ.get(
    "PYSOEM_POSITION_FEEDBACK_LAG_LOGS",
    "0",
).strip() == "1"
POSITION_FEEDBACK_LAG_LOG_PERIOD = float(
    os.environ.get("PYSOEM_POSITION_FEEDBACK_LAG_LOG_PERIOD", "0.2")
)
CSP_COMMAND_STEP_THRESHOLD = float(
    os.environ.get("PYSOEM_CSP_COMMAND_STEP_THRESHOLD", "250.0")
)
CSP_COMMAND_STEP_ERROR_THRESHOLD = float(
    os.environ.get("PYSOEM_CSP_COMMAND_STEP_ERROR_THRESHOLD", "75.0")
)
DEVICE_PROFILE = get_device_profile(os.environ.get("PYSOEM_DEVICE", "cmmt"))
PROFILE_POSITION_MODE = DEVICE_PROFILE.PROFILE_POSITION_MODE
PROFILE_VELOCITY_MODE = DEVICE_PROFILE.PROFILE_VELOCITY_MODE
JOG_MODE = DEVICE_PROFILE.JOG_MODE
HOMING_MODE = DEVICE_PROFILE.HOMING_MODE
CSP_MODE = DEVICE_PROFILE.CSP_MODE
PP_BASE_CONTROLWORD = DEVICE_PROFILE.PP_BASE_CONTROLWORD
PP_NEW_SETPOINT_CONTROLWORD = DEVICE_PROFILE.PP_NEW_SETPOINT_CONTROLWORD
PP_SETPOINT_ACK_MASK = DEVICE_PROFILE.PP_SETPOINT_ACK_MASK
PP_HANDSHAKE_MAX_CYCLES = DEVICE_PROFILE.PP_HANDSHAKE_MAX_CYCLES
HOMING_START_BIT = DEVICE_PROFILE.HOMING_START_BIT
HOMING_REFERENCED_MASK = DEVICE_PROFILE.HOMING_REFERENCED_MASK
HOMING_ERROR_MASK = DEVICE_PROFILE.HOMING_ERROR_MASK
HOMING_MIN_MONITOR_TIME = 0.05
MOTION_MODES = DEVICE_PROFILE.MOTION_MODES

COMMON_RXPDO_FIELDS = (
    "controlword",
    "mode_of_operation",
)
COMMON_TXPDO_FIELDS = (
    "statusword",
    "mode_of_operation_display",
    "actual_position",
    "actual_velocity",
)
MODE_RXPDO_FIELDS = {
    "pp": (
        "target_position",
        "profile_velocity",
    ),
    "pv": (
        "target_velocity",
    ),
    "csp": (
        "target_position",
    ),
    "homing": (),
    "jog": (),
}
TXPDO_SETPOINT_ENTRY_FIELDS = (
    "setpoint_position",
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="TCP JSON-lines Axis Server for CiA402 axes."
    )
    parser.add_argument(
        "interface",
        nargs="?",
        default=os.environ.get("PYSOEM_INTERFACE", "enp1s0"),
        help="PySOEM adapter, for example enp1s0 on Linux or \\Device\\NPF_{...} on Windows.",
    )
    parser.add_argument(
        "--list-adapters",
        action="store_true",
        help="List PySOEM/Npcap adapter names and exit.",
    )
    parser.add_argument(
        "--backend",
        choices=["mock", "pysoem"],
        default=os.environ.get("AXIS_SERVER_BACKEND", "pysoem").lower(),
        help="Device backend. pysoem drives real EtherCAT slaves; mock uses VirtualCiA402Servo.",
    )
    parser.add_argument(
        "--device",
        choices=available_device_names(),
        default=DEVICE_PROFILE.name,
        help="Default drive profile used when --device-profiles is empty.",
    )
    parser.add_argument(
        "--device-profiles",
        default=os.environ.get("PYSOEM_DEVICE_PROFILES", ""),
        help=(
            "Comma-separated EtherCAT slave profiles in bus order. "
            "Empty repeats --device for each motion axis."
        ),
    )
    parser.add_argument(
        "--axis-slave-indices",
        default=os.environ.get("PYSOEM_AXIS_SLAVE_INDICES", ""),
        help=(
            "Comma-separated EtherCAT slave indices for motion axes. "
            "Empty uses 0..axis-count-1."
        ),
    )
    parser.add_argument(
        "--server-mode",
        choices=AXIS_SERVER_MODES,
        default=AXIS_SERVER_MODE,
        help=(
            "Axis Server feature mode. basic exposes point/profile motion and "
            "parameter APIs; advanced enables cyclic trajectory commands."
        ),
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=15000)
    parser.add_argument(
        "--cycle-time",
        type=float,
        default=DEFAULT_CYCLE_TIME,
        help="Process-data cycle time in seconds.",
    )
    parser.add_argument(
        "--spin-wait-time",
        type=float,
        default=DEFAULT_SPIN_WAIT_TIME,
        help=(
            "Busy-wait window before each process-data cycle in seconds. "
            "Use 0.0 to sleep until the cycle deadline."
        ),
    )
    parser.add_argument(
        "--sync-mode",
        default=os.environ.get("PYSOEM_SYNC_MODE", "0"),
        help=(
            "Optional drive EtherCAT sync mode configured before OP. "
            "0=FreeRun, 1=sync with process data, 2=DC Sync0. "
            "Cycle time follows --cycle-time."
        ),
    )
    parser.add_argument(
        "--dc-enabled",
        action="store_true",
        default=os.environ.get("PYSOEM_DC_ENABLED", "0").strip() == "1",
        help="Enable EtherCAT distributed clocks and Sync0 before OP.",
    )
    parser.add_argument(
        "--dc-sync0-shift-time",
        type=int,
        default=int(os.environ.get("PYSOEM_DC_SYNC0_SHIFT_TIME_NS", "0")),
        help="SYNC0 shift time in nanoseconds when DC is enabled.",
    )
    parser.add_argument(
        "--dc-phase-lock",
        action="store_true",
        default=os.environ.get("PYSOEM_DC_PHASE_LOCK", "0").strip() == "1",
        help=(
            "Lock the master PDO send phase to EtherCAT DC Sync0. "
            "Use --dc-absolute-shift to select absolute scheduling; otherwise "
            "PI correction is used."
        ),
    )
    parser.add_argument(
        "--dc-absolute-shift",
        action="store_true",
        default=os.environ.get("PYSOEM_DC_ABSOLUTE_SHIFT", "0").strip() == "1",
        help=(
            "Schedule each PDO send from the current EtherCAT DC phase instead "
            "of using PI correction on a host-clock periodic deadline."
        ),
    )
    parser.add_argument(
        "--dc-phase-offset",
        type=int,
        default=int(os.environ.get("PYSOEM_DC_PHASE_OFFSET_NS", "800000")),
        help="Target PDO send phase offset before Sync0 in nanoseconds.",
    )
    parser.add_argument(
        "--dc-phase-kp",
        type=float,
        default=float(os.environ.get("PYSOEM_DC_PHASE_KP", "0.05")),
        help="Proportional gain for DC phase lock.",
    )
    parser.add_argument(
        "--dc-phase-ki",
        type=float,
        default=float(os.environ.get("PYSOEM_DC_PHASE_KI", "0.0005")),
        help="Integral gain for DC phase lock.",
    )
    parser.add_argument(
        "--dc-phase-max-correction",
        type=float,
        default=float(os.environ.get("PYSOEM_DC_PHASE_MAX_CORRECTION", "0.001")),
        help="Maximum absolute host wake-up correction in seconds.",
    )
    parser.add_argument(
        "--axis-count",
        type=int,
        default=int(os.environ.get("PYSOEM_AXIS_COUNT", "1")),
    )
    parser.add_argument(
        "--max-velocity",
        type=float,
        default=float(os.environ.get("PYSOEM_MAX_VELOCITY", "50.0")),
    )
    parser.add_argument(
        "--acceleration",
        type=float,
        default=float(os.environ.get("PYSOEM_ACCELERATION", "100.0")),
    )
    parser.add_argument(
        "--deceleration",
        type=float,
        default=float(os.environ.get("PYSOEM_DECELERATION", "100.0")),
    )
    parser.add_argument(
        "--jerk",
        type=float,
        default=float(os.environ.get("PYSOEM_JERK", "1000.0")),
        help="CSP S-curve jerk limit in user units per second cubed.",
    )
    parser.add_argument(
        "--pp-jerk",
        type=int,
        default=int(os.environ.get("PYSOEM_PP_JERK", "100000")),
        help="Profile position jerk configured on the drive.",
    )
    parser.add_argument(
        "--csp-counts-per-unit",
        type=float,
        default=float(os.environ.get("PYSOEM_CSP_COUNTS_PER_UNIT", "1.0")),
        help=(
            "Scale PP/user velocity units to CSP position counts. "
            "Example: 1000 count/mm -> 1000.0."
        ),
    )
    parser.add_argument(
        "--csp-profile",
        choices=["trapezoid", "quintic"],
        type=lambda value: value.strip().lower(),
        default=os.environ.get(
            "PYSOEM_CSP_PROFILE",
            "quintic",
        ).strip().lower(),
        help=(
            "CSP profile used by Point Move and position-only Trajectory Move. "
            "trapezoid uses velocity/accel/decel limits; quintic uses the "
            "smooth polynomial profile and jerk limit. Trajectory Move with "
            "complete velocity data uses cubic spline, and complete "
            "velocity/acceleration data uses quintic spline."
        ),
    )
    parser.add_argument(
        "--csp-command-step-threshold",
        type=float,
        default=CSP_COMMAND_STEP_THRESHOLD,
        help=(
            "Log CSP command position steps at or above this threshold "
            "in counts. Set 0 to disable."
        ),
    )
    parser.add_argument(
        "--csp-command-step-error-threshold",
        type=float,
        default=CSP_COMMAND_STEP_ERROR_THRESHOLD,
        help=(
            "Log CSP command position steps whose sent step differs from "
            "the command-velocity-derived expected step by this many counts. "
            "Set 0 to disable."
        ),
    )
    parser.add_argument(
        "--txpdo-setpoint-entry",
        action="store_true",
        default=os.environ.get("PYSOEM_TXPDO_SETPOINT_ENTRY", "0").strip() == "1",
        help=(
            "Use CMMT TxPDO setpoint entry layout. "
            "0/default uses TxPDO.MAPPING_ENTRIES; 1 uses "
            "TxPDO.SETPOINT_REPLACE_ENTRIES."
        ),
    )
    parser.add_argument(
        "--csp-interpolation-mode",
        type=int,
        default=int(os.environ.get("PYSOEM_CSP_INTERPOLATION_MODE", "1")),
        help=(
            "Device CSP interpolation mode. "
            "For CMMT: 1=CSP, 4=CSP-V, 5=CSP-T, 6=CSP-VT."
        ),
    )
    parser.add_argument(
        "--csp-velocity-offset",
        action="store_true",
        default=os.environ.get("PYSOEM_CSP_VELOCITY_OFFSET", "0").strip() == "1",
        help=(
            "Send CSP command velocity as 0x60B1 velocity offset in user units. "
            "Use with CSP interpolation mode CSP-V."
        ),
    )
    parser.add_argument(
        "--derived-velocity-alpha",
        type=float,
        default=DERIVED_VELOCITY_ALPHA,
        help="Low-pass filter alpha for derived velocity. Use 1.0 to disable.",
    )
    parser.add_argument(
        "--motion-mode",
        choices=sorted(MOTION_MODES),
        default=os.environ.get("PYSOEM_MOTION_MODE", "pp").lower(),
    )
    args = parser.parse_args()
    if args.csp_profile == "quintic" and args.jerk <= 0.0:
        parser.error("--csp-profile quintic requires --jerk > 0")
    return args


def required_rxpdo_fields_for_mode(mode_name, csp_velocity_offset_enabled=False):
    fields = list(COMMON_RXPDO_FIELDS)
    fields.extend(MODE_RXPDO_FIELDS.get(mode_name, ()))
    if mode_name == "csp" and csp_velocity_offset_enabled:
        fields.append("velocity_offset")
    return tuple(dict.fromkeys(fields))


def required_txpdo_fields_for_entry(setpoint_entry_enabled=False):
    if setpoint_entry_enabled:
        fields = [
            field for field in COMMON_TXPDO_FIELDS
            if field != "actual_position"
        ]
        fields.extend(TXPDO_SETPOINT_ENTRY_FIELDS)
    else:
        fields = list(COMMON_TXPDO_FIELDS)
    return tuple(dict.fromkeys(fields))


def require_pdo_fields_for_mode(runtime, mode_name, axis_index=None):
    axis_indices = (
        range(len(runtime.slaves))
        if axis_index is None
        else [axis_index]
    )
    rxpdo_fields = required_rxpdo_fields_for_mode(
        mode_name,
        getattr(runtime, "csp_velocity_offset_enabled", False),
    )
    for current_axis in axis_indices:
        require_pdo_fields(
            runtime.slaves[current_axis].rxpdo,
            rxpdo_fields,
            context=f"Axis {current_axis} RxPDO {mode_name.upper()}",
        )


def require_txpdo_fields(runtime):
    txpdo_fields = required_txpdo_fields_for_entry(
        getattr(runtime, "txpdo_setpoint_entry", False),
    )
    for axis_index, slave in enumerate(runtime.slaves):
        require_pdo_fields(
            slave.txpdo,
            txpdo_fields,
            context=f"Axis {axis_index} TxPDO",
        )


def require_pdo_fields(pdo, fields, context):
    missing = [field for field in fields if not pdo.has_field(field)]
    if missing:
        raise RuntimeError(
            f"{context} is missing required PDO field(s): "
            f"{', '.join(missing)}"
        )
