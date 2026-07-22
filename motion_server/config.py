import argparse
import os
from pathlib import Path

from device import available_device_names, get_device_profile


def load_env_defaults(env_path, override=False):
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if override:
            os.environ[key] = value
        else:
            os.environ.setdefault(key, value)


def env_value(name, default="", legacy_name=None):
    value = os.environ.get(name)
    if value is not None:
        return value
    if legacy_name:
        legacy_value = os.environ.get(legacy_name)
        if legacy_value is not None:
            return legacy_value
    return default


def load_project_env_defaults():
    project_root = Path(
        env_value(
            "MOTION_SERVER_PROJECT_ROOT",
            Path(__file__).resolve().parents[1],
            "AXIS_SERVER_PROJECT_ROOT",
        )
    ).resolve()
    load_env_defaults(project_root / ".env")

    backend = env_value(
        "MOTION_SERVER_BACKEND",
        "pysoem",
        "AXIS_SERVER_BACKEND",
    ).strip().lower()
    if backend == "mock":
        virtual_env_file = os.environ.get(
            "VIRTUAL_SERVO_DRIVE_ENV_FILE",
            "device/virtual_servo_drive/.env",
        )
        virtual_env_path = Path(virtual_env_file)
        if not virtual_env_path.is_absolute():
            virtual_env_path = project_root / virtual_env_path
        load_env_defaults(virtual_env_path, override=True)


load_project_env_defaults()


MOTION_SERVER_MODES = ("basic", "advanced")
MOTION_SERVER_MODE = env_value(
    "MOTION_SERVER_MODE",
    "basic",
    "AXIS_SERVER_MODE",
).strip().lower()
DEFAULT_CYCLE_TIME = float(os.environ.get("PYSOEM_CYCLE_TIME", "0.01"))
DEFAULT_SPIN_WAIT_TIME = float(os.environ.get("PYSOEM_SPIN_WAIT_TIME", "0.00015"))
DERIVED_VELOCITY_ALPHA = float(
    os.environ.get("PYSOEM_DERIVED_VELOCITY_ALPHA", "0.2")
)
FEEDBACK_PERIOD = 0.05
STATUS_LOG_PERIOD = float(os.environ.get("PYSOEM_STATUS_LOG_PERIOD", "1.0"))
AXIS_SERVER_COMMAND_LOGS = env_value(
    "MOTION_SERVER_COMMAND_LOGS",
    "0",
    "AXIS_SERVER_COMMAND_LOGS",
).strip() == "1"
AXIS_SERVER_STATUS_LOGS = env_value(
    "MOTION_SERVER_STATUS_LOGS",
    "0",
    "AXIS_SERVER_STATUS_LOGS",
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
DEVICE_PROFILE = get_device_profile("cmmt")
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
def parse_args(argv=None):
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
        default=env_value(
            "MOTION_SERVER_BACKEND",
            "pysoem",
            "AXIS_SERVER_BACKEND",
        ).lower(),
        help="Device backend. pysoem drives real EtherCAT slaves; mock uses VirtualCiA402Servo.",
    )
    parser.add_argument(
        "--mock-axis-types",
        default=os.environ.get("MOCK_AXIS_TYPES", ""),
        help=(
            "Comma-separated virtual axis types for mock backend: "
            "linear or rotary. A single value is repeated for all axes."
        ),
    )
    parser.add_argument(
        "--mock-axis-user-units",
        default=os.environ.get("MOCK_AXIS_USER_UNITS", ""),
        help=(
            "Comma-separated mock 0x216E:01 user position units. "
            "Overrides --mock-axis-types. Examples: 0x0100 linear m, "
            "0x4100 rotary deg, 0x1000 rotary rad, 0xB400 rotary rev."
        ),
    )
    parser.add_argument(
        "--bus",
        default=os.environ.get("PYSOEM_BUS", "cmmt"),
        help=(
            "Comma-separated EtherCAT bus layout. Entries without a prefix "
            "are motion axes. Use io:<profile> or device:<profile> for "
            "non-motion slaves, for example cmmt,cmmt,io:cpx_ap_i_ec."
        ),
    )
    parser.add_argument(
        "--server-mode",
        choices=MOTION_SERVER_MODES,
        default=MOTION_SERVER_MODE,
        help=(
            "Motion Server feature mode. basic exposes point/profile motion and "
            "parameter APIs; advanced enables cyclic trajectory commands."
        ),
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument(
        "--port",
        type=int,
        default=int(env_value("MOTION_SERVER_PORT", "15000", "AXIS_SERVER_PORT")),
    )
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
    args = parser.parse_args(argv)
    bus_config = parse_bus_config(args.bus)
    args.device_profile_names = bus_config["device_profile_names"]
    args.axis_slave_indices = bus_config["axis_slave_indices"]
    args.axis_count = len(args.axis_slave_indices)
    if args.axis_count < 1:
        parser.error("--bus must contain at least one motion axis")
    if args.csp_profile == "quintic" and args.jerk <= 0.0:
        parser.error("--csp-profile quintic requires --jerk > 0")
    return args


def parse_bus_config(raw_bus):
    raw_bus = str(raw_bus or "").strip()
    if not raw_bus:
        raise ValueError("PYSOEM_BUS must not be empty")

    available = set(available_device_names())
    device_profile_names = []
    axis_slave_indices = []

    for raw_entry in raw_bus.split(","):
        entry = raw_entry.strip().lower()
        if not entry:
            continue

        role = "axis"
        profile_name = entry
        if ":" in entry:
            role, profile_name = [
                part.strip()
                for part in entry.split(":", 1)
            ]

        if role in {"axis", "drive"}:
            is_motion_axis = True
        elif role in {"io", "device", "slave"}:
            is_motion_axis = False
        else:
            raise ValueError(
                f"Unsupported PYSOEM_BUS role {role!r}; "
                "use axis:<profile> or io:<profile>"
            )

        if profile_name not in available:
            raise ValueError(
                f"Unsupported PYSOEM_BUS profile {profile_name!r}. "
                f"Supported profiles: {', '.join(available_device_names())}"
            )

        slave_index = len(device_profile_names)
        device_profile_names.append(profile_name)
        if is_motion_axis:
            axis_slave_indices.append(slave_index)

    if not device_profile_names:
        raise ValueError("PYSOEM_BUS does not contain any devices")

    return {
        "device_profile_names": device_profile_names,
        "axis_slave_indices": axis_slave_indices,
    }


def required_rxpdo_fields_for_mode(mode_name, csp_velocity_offset_enabled=False):
    fields = list(COMMON_RXPDO_FIELDS)
    fields.extend(MODE_RXPDO_FIELDS.get(mode_name, ()))
    if mode_name == "csp" and csp_velocity_offset_enabled:
        fields.append("velocity_offset")
    return tuple(dict.fromkeys(fields))


def required_txpdo_fields_for_entry():
    return tuple(dict.fromkeys(COMMON_TXPDO_FIELDS))


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
    txpdo_fields = required_txpdo_fields_for_entry()
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


def status_log(*args, **kwargs):
    if AXIS_SERVER_STATUS_LOGS:
        kwargs.setdefault("flush", True)
        print(*args, **kwargs)
