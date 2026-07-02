import argparse
import json
import os
from pathlib import Path
import select
import socket
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cia402.virtual_servo import VirtualCiA402Servo
from axis_server.cmmt_error_catalog import load_cmmt_error_catalog
from ethercat.mock_master import MockMaster
from ethercat.mock_slave import MockSlave
from ethercat.pysoem_master import PySOEMMaster
from motion.axis import Axis


DEFAULT_CYCLE_TIME = float(os.environ.get("PYSOEM_CYCLE_TIME", "0.01"))
DEFAULT_SPIN_WAIT_TIME = float(os.environ.get("PYSOEM_SPIN_WAIT_TIME", "0.00015"))
DERIVED_VELOCITY_ALPHA = float(
    os.environ.get("PYSOEM_DERIVED_VELOCITY_ALPHA", "0.2")
)
FEEDBACK_PERIOD = 0.05
STATUS_LOG_PERIOD = float(os.environ.get("PYSOEM_STATUS_LOG_PERIOD", "1.0"))
CYCLE_STATS_PERIOD = float(os.environ.get("PYSOEM_CYCLE_STATS_PERIOD", "1.0"))
PROFILE_POSITION_MODE = 1
HOMING_MODE = 6
CSP_MODE = 8
CSV_MODE = 9
PP_BASE_CONTROLWORD = 0x000F
PP_NEW_SETPOINT_CONTROLWORD = 0x003F
PP_SETPOINT_ACK_BIT = 12
PP_SETPOINT_ACK_MASK = 1 << PP_SETPOINT_ACK_BIT
PP_HANDSHAKE_MAX_CYCLES = 100
HOMING_START_BIT = 1 << 4
HOMING_REFERENCED_MASK = 1 << 15
HOMING_ERROR_MASK = 1 << 13
HOMING_MIN_MONITOR_TIME = 0.05
CMMT_MAIN_GROUPS = {
    1: "Current",
    2: "Voltage",
    3: "Temperature",
    5: "Motion",
    6: "Configuration/parameterization",
    7: "Monitoring",
    8: "Communication",
    9: "Safety engineering",
    10: "Internal hardware",
    11: "Software",
    12: "Maintenance",
    13: "Various",
    16: "External device",
    17: "Security (data)",
    18: "Encoder",
}
CMMT_SUBGROUPS = {
    (1, 1): "Short circuit",
    (1, 2): "I2t",
    (1, 3): "Braking resistor",
    (2, 1): "Supply",
    (2, 2): "DC link circuit",
    (2, 3): "Principal voltage",
    (2, 4): "Encoder supply",
    (3, 1): "Device",
    (3, 2): "Output stage",
    (3, 3): "Motor",
    (5, 1): "Homing",
    (5, 2): "Motion control",
    (5, 3): "Interpolation",
    (6, 0): "No allocation",
    (6, 2): "Critical limits",
    (6, 5): "Parameter set",
    (7, 1): "Limitations",
    (7, 2): "Motion monitoring",
    (7, 3): "Critical limits",
    (7, 4): "Zero angle detection",
    (7, 5): "Analogue input",
    (7, 11): "Friction",
    (8, 0): "No allocation",
    (8, 3): "PROFINET",
    (8, 4): "EtherCAT",
    (8, 6): "EtherNet",
    (8, 9): "PROFIdrive",
    (8, 12): "CiA 402",
    (8, 13): "EtherNet/IP",
    (8, 14): "MP",
    (9, 0): "No allocation",
    (9, 1): "STO",
    (9, 2): "SBC",
    (10, 1): "Module error",
    (11, 0): "No allocation",
    (11, 1): "Exception",
    (11, 2): "Task",
    (11, 3): "File system",
    (11, 4): "Firmware update",
    (11, 5): "Device configuration",
    (11, 6): "LibRTE",
    (11, 7): "Warm start",
    (11, 8): "Version management",
    (12, 1): "Operating time",
    (13, 1): "Diagnostics",
    (13, 2): "Auto-tuning",
    (16, 1): "CDSB",
    (17, 1): "User login",
    (18, 0): "No allocation",
    (18, 1): "EnDat",
    (18, 2): "Hiperface",
    (18, 3): "Quadrature incremental encoder",
    (18, 4): "Nikon A",
    (18, 5): "BiSS C",
    (18, 6): "Sin/Cos",
    (18, 7): "ProfiDrive",
}
CMMT_ERROR_CATALOG = load_cmmt_error_catalog()
MOTION_MODES = {
    "pp": PROFILE_POSITION_MODE,
    "csp": CSP_MODE,
    "csv": CSV_MODE,
}


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
        "--backend",
        choices=["mock", "pysoem"],
        default=os.environ.get("AXIS_SERVER_BACKEND", "pysoem").lower(),
        help="Device backend. pysoem drives real EtherCAT slaves; mock uses VirtualCiA402Servo.",
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
            "Optional CMMT EtherCAT sync mode written via 0x212E before OP. "
            "0=FreeRun, 1=sync with process data, 2=DC Sync0. "
            "Cycle time follows --cycle-time."
        ),
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
        help="Profile position jerk written to 0x60A4:01 as UDINT.",
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
    return parser.parse_args()


def create_master(args, motion_limits):
    sync_mode = parse_optional_sync_mode(args.sync_mode)

    if args.backend == "mock":
        slaves = []
        for axis_index, limits in enumerate(motion_limits):
            servo = VirtualCiA402Servo(cycle_time=args.cycle_time)
            servo.set_motion_limits(
                limits["max_velocity"],
                limits["acceleration"],
                limits["deceleration"],
            )
            axis = Axis(f"A{axis_index}", servo)
            slaves.append(MockSlave(axis))

        master = MockMaster(
            slaves,
            cycle_time=args.cycle_time,
            csp_counts_per_unit=1.0,
        )
        for axis_index, limits in enumerate(motion_limits):
            master.set_axis_motion_limits(
                axis_index,
                limits["max_velocity"],
                limits["acceleration"],
                limits["deceleration"],
                limits["jerk"],
            )
        return master

    return PySOEMMaster(
        interface_name=args.interface,
        slave_count=args.axis_count,
        cycle_time=args.cycle_time,
        motion_limits=motion_limits,
        csp_counts_per_unit=args.csp_counts_per_unit,
        sync_mode=sync_mode,
    )


def parse_optional_sync_mode(raw_value):
    value = str(raw_value).strip()
    if value == "":
        return None

    sync_mode = int(value, 0)
    if sync_mode not in (0, 1, 2):
        raise ValueError(
            f"Unsupported sync mode {sync_mode}; expected 0, 1, 2, or empty."
        )
    return sync_mode


class CycleStats:
    def __init__(self):
        self.values = {}
        self.last_tx_time = None

    def add(self, name, seconds):
        bucket = self.values.setdefault(
            name,
            {
                "count": 0,
                "sum": 0.0,
                "min": None,
                "max": None,
            },
        )
        bucket["count"] += 1
        bucket["sum"] += seconds
        bucket["min"] = seconds if bucket["min"] is None else min(bucket["min"], seconds)
        bucket["max"] = seconds if bucket["max"] is None else max(bucket["max"], seconds)

    def add_tx_time(self, tx_time):
        if self.last_tx_time is not None:
            self.add("tx_gap", tx_time - self.last_tx_time)
        self.last_tx_time = tx_time

    def report_and_reset(self):
        parts = []
        for name in sorted(self.values):
            bucket = self.values[name]
            if bucket["count"] == 0:
                continue
            average = bucket["sum"] / bucket["count"]
            parts.append(
                f"{name}_ms="
                f"min:{bucket['min'] * 1000.0:.3f} "
                f"avg:{average * 1000.0:.3f} "
                f"max:{bucket['max'] * 1000.0:.3f} "
                f"n:{bucket['count']}"
            )

        self.values = {}
        return " | ".join(parts)


def exchange(master, cycles=1, cycle_stats=None, sleep_after=True):
    for _ in range(cycles):
        exchange_start = time.monotonic()
        if cycle_stats is not None:
            cycle_stats.add_tx_time(exchange_start)
        master.send_processdata()
        master.receive_processdata()
        pdo_done = time.monotonic()
        if sleep_after:
            time.sleep(master.cycle_time)
        exchange_done = time.monotonic()
        if cycle_stats is not None:
            cycle_stats.add("pdo_io", pdo_done - exchange_start)
            cycle_stats.add("exchange", exchange_done - exchange_start)


def axis_count(master):
    return len(master.slaves)


def faulted_axes(master):
    return [
        index
        for index, slave in enumerate(master.slaves)
        if slave.txpdo.statusword & 0x0008
    ]


def wait_status_all(master, expected_status, max_cycles=None, timeout_s=2.0):
    deadline = None
    if timeout_s is not None:
        deadline = time.monotonic() + float(timeout_s)

    cycles = 0
    while True:
        exchange(master)
        if all(
            (slave.txpdo.statusword & 0x006F) == expected_status
            for slave in master.slaves
        ):
            return True
        cycles += 1

        if max_cycles is not None and cycles >= max_cycles:
            return False
        if deadline is not None and time.monotonic() >= deadline:
            return False

        if max_cycles is None and deadline is None:
            return False


def read_drive_diagnostics(master, axis_index):
    diagnostics = {}

    try:
        diagnostics["statusword"] = master.sdo_read_uint16(axis_index, 0x6041, 0)
    except Exception as exc:
        diagnostics["statusword"] = f"read failed: {exc}"

    try:
        diagnostics["error_code"] = master.sdo_read_uint32(axis_index, 0x2145, 0x0C)
    except Exception as exc:
        diagnostics["error_code"] = f"read failed: {exc}"

    diagnostics["error_code_text"] = format_cmmt_error_code(
        diagnostics["error_code"]
    )

    try:
        diagnostics["mode_display"] = master.sdo_read_int8(axis_index, 0x6061, 0)
    except Exception as exc:
        diagnostics["mode_display"] = f"read failed: {exc}"

    return diagnostics


def read_all_diagnostics(master):
    return [
        read_drive_diagnostics(master, axis_index)
        for axis_index in range(axis_count(master))
    ]


def format_diagnostics(diagnostics):
    def format_value(value, width=None):
        if isinstance(value, int) and width is not None:
            return f"0x{value:0{width}X}"

        return str(value)

    return (
        f"SDO_SW={format_value(diagnostics['statusword'], 4)} "
        f"ERR={diagnostics['error_code_text']} "
        f"MODE_DISP={diagnostics['mode_display']}"
    )


def format_cmmt_error_code(error_code):
    if not isinstance(error_code, int):
        return "read fail"
    if error_code == 0:
        return "No error"

    catalog_entry = CMMT_ERROR_CATALOG.get(error_code)
    if catalog_entry is not None:
        return format_cmmt_catalog_entry(catalog_entry)

    main_group = (error_code >> 24) & 0xFF
    subgroup = (error_code >> 16) & 0xFF
    error_number = error_code & 0xFFFF
    if main_group or subgroup:
        main_text = CMMT_MAIN_GROUPS.get(main_group, "Unknown main group")
        subgroup_text = CMMT_SUBGROUPS.get(
            (main_group, subgroup),
            "Unknown subgroup",
        )
        return (
            f"Error {error_number} | "
            f"{main_group:02d} {main_text} / "
            f"{subgroup:02d} {subgroup_text}"
        )

    return f"Error {error_number} | CMMT 16-bit error number"


def format_cmmt_catalog_entry(entry):
    parts = [
        f"{entry['id']} {entry['message']}",
    ]
    if entry.get("description"):
        parts.append(entry["description"])
    if entry.get("remedy"):
        parts.append(f"Remedy: {entry['remedy']}")
    if entry.get("classification"):
        parts.append(f"Classification: {entry['classification']}")
    return " | ".join(parts)


def format_axis_diagnostics(diagnostics_list):
    return " | ".join(
        f"A{index}:{format_diagnostics(diagnostics)}"
        for index, diagnostics in enumerate(diagnostics_list)
    )


def mode_code(mode_name):
    if mode_name == "homing":
        return HOMING_MODE
    return MOTION_MODES[mode_name]


def configure_motion_mode(master, mode_name, axis_index=None):
    code = mode_code(mode_name)
    configure_mode_code(master, code, axis_index)


def configure_mode_code(master, code, axis_index=None):

    axis_indices = (
        range(axis_count(master))
        if axis_index is None
        else [axis_index]
    )
    if axis_index is None:
        master.set_mode_of_operation_all(code)

    for current_axis in axis_indices:
        master.slaves[current_axis].rxpdo.mode_of_operation = code
        master.sdo_write_int8(current_axis, 0x6060, 0, code)
    exchange(master, cycles=5)


def initialize_drive(master, motion_mode, pp_jerk):
    master.connect()
    configure_motion_mode(master, motion_mode)
    for axis_index in range(axis_count(master)):
        write_profile_jerk(master, axis_index, pp_jerk)
        write_profile_motion_limits(master, axis_index)

    exchange(master, cycles=10)
    master.sync_trajectory_to_actual_positions()

    if faulted_axes(master):
        master.set_controlword_all(0x0080)
        wait_status_all(master, 0x0040, timeout_s=2.0)
        master.set_controlword_all(0x0000)
        exchange(master, cycles=10)

    for controlword, expected_status in [
        (0x0006, 0x0021),
        (0x0007, 0x0023),
        (0x000F, 0x0027),
    ]:
        master.set_controlword_all(controlword)
        if not wait_status_all(master, expected_status, timeout_s=2.0):
            statuswords = [
                f"0x{slave.txpdo.statusword:04X}"
                for slave in master.slaves
            ]
            print(
                f"Failed to reach CiA402 status 0x{expected_status:04X}. "
                f"Statuswords={statuswords}; continuing startup.",
                flush=True,
            )


def feedback_message(master, state, client_id=None):
    owner = state.get("command_authority_owner")
    return {
        "type": "feedback",
        "target_positions": state["target_positions"],
        "actual_positions": [
            float(slave.txpdo.actual_position)
            for slave in master.slaves
        ],
        "actual_velocities": [
            float(slave.txpdo.actual_velocity)
            for slave in master.slaves
        ],
        "derived_velocities": state["derived_velocities"],
        "command_positions": [
            float(generator.command_position)
            for generator in master.trajectory_generators
        ],
        "command_velocities": [
            float(generator.command_velocity)
            for generator in master.trajectory_generators
        ],
        "statuswords": [
            int(slave.txpdo.statusword)
            for slave in master.slaves
        ],
        "motion_limits": flatten_motion_limits(state["motion_limits"]),
        "software_position_limits": flatten_software_position_limits(
            state["software_position_limits"]
        ),
        "motion_mode": state["motion_mode"],
        "motion_modes": state["motion_modes"],
        "csp_counts_per_unit": master.csp_counts_per_unit,
        "position_counts_per_unit": state["position_counts_per_unit"],
        "capabilities": state["capabilities"],
        "trajectory": state["trajectory"],
        "homing": public_homing_state(state),
        "diagnostics": master.last_diagnostics,
        "command_authority": {
            "owner": owner,
            "owned_by_this_client": owner is not None and owner == client_id,
            "available": owner is None,
        },
    }


def flatten_motion_limits(motion_limits):
    return [
        float(value)
        for axis_limits in motion_limits
        for value in axis_limits
    ]


def flatten_software_position_limits(software_position_limits):
    return [
        float(value)
        for axis_limits in software_position_limits
        for value in axis_limits
    ]


def actual_positions(master):
    return [
        float(slave.txpdo.actual_position)
        for slave in master.slaves
    ]


def hold_axis_at_actual_position(master, state, axis_index):
    actual_position = float(master.slaves[axis_index].txpdo.actual_position)
    state["target_positions"][axis_index] = actual_position
    master.slaves[axis_index].rxpdo.target_position = int(actual_position)
    if hasattr(master, "sync_trajectory_to_actual_position"):
        master.sync_trajectory_to_actual_position(axis_index)


def hold_faulted_axes(master, state):
    changed = False
    for axis_index in faulted_axes(master):
        actual_position = float(master.slaves[axis_index].txpdo.actual_position)
        state["target_positions"][axis_index] = actual_position
        master.slaves[axis_index].rxpdo.target_position = int(actual_position)
        changed = True

    if changed:
        master.set_target_positions(state["target_positions"])


def inactive_trajectory_state(result="idle"):
    return {
        "active": False,
        "state": result,
        "axes": [],
        "segment": 0,
        "time_from_start": 0.0,
        "points": [],
        "start_time": None,
        "message": "",
    }


def ensure_csp_mode(master, state, axis_indices):
    changed = False
    for axis_index in axis_indices:
        if state["motion_modes"][axis_index] != "csp":
            hold_axis_at_actual_position(master, state, axis_index)
            configure_motion_mode(master, "csp", axis_index)
            state["motion_modes"][axis_index] = "csp"
            changed = True

    if changed:
        state["motion_mode"] = (
            "csp"
            if len(set(state["motion_modes"])) == 1
            else "mixed"
        )
        master.set_target_positions(state["target_positions"])


def reject_trajectory(state, message):
    state["trajectory"] = inactive_trajectory_state("rejected")
    state["trajectory"]["message"] = message
    print(f"Ignored trajectory_command: {message}", flush=True)


def handle_trajectory_command(message, master, state):
    raw_axes = message.get("axes", [])
    axes = [int(axis) for axis in raw_axes] if raw_axes else list(range(axis_count(master)))
    try:
        points = normalize_trajectory_points(message.get("points", []), axes)
    except (TypeError, ValueError) as exc:
        reject_trajectory(state, str(exc))
        return

    if any(axis < 0 or axis >= axis_count(master) for axis in axes):
        reject_trajectory(state, f"Invalid trajectory axes: {axes}")
        return
    if not points:
        reject_trajectory(state, "trajectory_command requires at least one point")
        return

    faults = faulted_axes(master)
    if faults:
        hold_faulted_axes(master, state)
        master.sync_trajectory_to_actual_positions()
        reject_trajectory(state, f"faulted_axes={faults}")
        return

    ensure_csp_mode(master, state, axes)

    if len(points) == 1:
        current = [
            float(master.slaves[axis_index].txpdo.actual_position)
            for axis_index in axes
        ]
        target = points[0]["positions"]
        duration = estimate_trajectory_duration(master, axes, current, target)
        points = [
            {
                "positions": current,
                "velocities": [0.0 for _ in axes],
                "time_from_start": 0.0,
            },
            {
                "positions": target,
                "velocities": [0.0 for _ in axes],
                "time_from_start": duration,
            },
        ]

    validation_error = validate_trajectory_limits(master, axes, points)
    if validation_error:
        reject_trajectory(state, validation_error)
        return

    for local_index, axis_index in enumerate(axes):
        master.trajectory_generators[axis_index].set_timed_trajectory(
            axis_timed_points(points, local_index)
        )
        master.slaves[axis_index].rxpdo.mode_of_operation = CSP_MODE
        master.slaves[axis_index].rxpdo.controlword = 0x000F

    state["trajectory"] = {
        "active": True,
        "state": "running",
        "axes": axes,
        "segment": 0,
        "time_from_start": 0.0,
        "points": points,
        "start_time": time.monotonic(),
        "message": "",
    }
    print(
        "Received trajectory_command: "
        f"axes={axes} points={len(points)} "
        f"duration={points[-1]['time_from_start']:.3f}",
        flush=True,
    )


def axis_timed_points(points, local_index):
    axis_points = []
    for point in points:
        axis_point = {
            "position": point["positions"][local_index],
            "time_from_start": point["time_from_start"],
        }
        if "velocities" in point:
            axis_point["velocity"] = point["velocities"][local_index]
        if "accelerations" in point:
            axis_point["acceleration"] = point["accelerations"][local_index]
        axis_points.append(axis_point)
    return axis_points


def normalize_trajectory_points(raw_points, axes):
    points = []
    expected = len(axes)
    for point_index, raw_point in enumerate(raw_points):
        positions = [float(value) for value in raw_point.get("positions", [])]
        if len(positions) < expected:
            raise ValueError(
                f"point {point_index} positions length {len(positions)} "
                f"is smaller than axes length {expected}"
            )

        point = {
            "positions": positions[:expected],
            "time_from_start": float(raw_point.get("time_from_start", 0.0)),
        }
        velocities = raw_point.get("velocities", None)
        if velocities is not None:
            if len(velocities) < expected:
                raise ValueError(
                    f"point {point_index} velocities length {len(velocities)} "
                    f"is smaller than axes length {expected}"
                )
            point["velocities"] = [
                float(value)
                for value in velocities[:expected]
            ]
        accelerations = raw_point.get("accelerations", None)
        if accelerations is not None:
            if len(accelerations) < expected:
                raise ValueError(
                    f"point {point_index} accelerations length {len(accelerations)} "
                    f"is smaller than axes length {expected}"
                )
            point["accelerations"] = [
                float(value)
                for value in accelerations[:expected]
            ]
        points.append(point)

    previous_time = -1e-9
    for point_index, point in enumerate(points):
        point_time = point["time_from_start"]
        if point_time < previous_time:
            raise ValueError(
                f"point {point_index} time_from_start is not monotonic"
            )
        previous_time = point_time
    return points


def estimate_trajectory_duration(master, axes, current, target):
    duration = 0.0
    for axis_index, start, end in zip(axes, current, target):
        distance = abs(float(end) - float(start))
        max_velocity = max(
            float(master.slaves[axis_index].motion_limits.max_velocity)
            * master.csp_counts_per_unit,
            1e-9,
        )
        acceleration_limit = max(
            float(master.slaves[axis_index].motion_limits.acceleration)
            * master.csp_counts_per_unit,
            1e-9,
        )
        deceleration_limit = max(
            float(master.slaves[axis_index].motion_limits.deceleration)
            * master.csp_counts_per_unit,
            1e-9,
        )
        accel_limit = min(acceleration_limit, deceleration_limit)
        duration = max(
            duration,
            1.5 * distance / max_velocity,
            (6.0 * distance / accel_limit) ** 0.5,
        )
    return max(duration, master.cycle_time)


def validate_trajectory_limits(master, axes, points):
    for previous, current in zip(points, points[1:]):
        dt = current["time_from_start"] - previous["time_from_start"]
        if dt <= 0.0:
            return "trajectory segment time must be greater than zero"

        for local_index, axis_index in enumerate(axes):
            start = previous["positions"][local_index]
            end = current["positions"][local_index]
            required_velocity = abs(end - start) / dt
            velocity_limit = (
                float(master.slaves[axis_index].motion_limits.max_velocity)
                * master.csp_counts_per_unit
            )
            acceleration_limit = (
                float(master.slaves[axis_index].motion_limits.acceleration)
                * master.csp_counts_per_unit
            )
            deceleration_limit = (
                float(master.slaves[axis_index].motion_limits.deceleration)
                * master.csp_counts_per_unit
            )
            if required_velocity > velocity_limit + 1e-9:
                return (
                    f"axis {axis_index} velocity limit exceeded: "
                    f"required={required_velocity:.3f} limit={velocity_limit:.3f}"
                )

            for point in (previous, current):
                velocities = point.get("velocities")
                if velocities is not None:
                    required = abs(velocities[local_index])
                    if required > velocity_limit + 1e-9:
                        return (
                            f"axis {axis_index} waypoint velocity limit exceeded: "
                            f"required={required:.3f} limit={velocity_limit:.3f}"
                        )

                accelerations = point.get("accelerations")
                if accelerations is not None:
                    required_accel = accelerations[local_index]
                    accel_limit = (
                        acceleration_limit
                        if required_accel >= 0.0
                        else deceleration_limit
                    )
                    if abs(required_accel) > accel_limit + 1e-9:
                        return (
                            f"axis {axis_index} waypoint acceleration limit exceeded: "
                            f"required={required_accel:.3f} limit={accel_limit:.3f}"
                        )

            if "velocities" in previous or "velocities" in current:
                start_velocity = previous.get(
                    "velocities",
                    [0.0 for _ in previous["positions"]],
                )[local_index]
                end_velocity = current.get(
                    "velocities",
                    [0.0 for _ in current["positions"]],
                )[local_index]
                a2 = (
                    3.0 * (end - start) / dt
                    - 2.0 * start_velocity
                    - end_velocity
                ) / dt
                a3 = (
                    2.0 * (start - end) / dt
                    + start_velocity
                    + end_velocity
                ) / (dt * dt)
                for accel in (2.0 * a2, 2.0 * a2 + 6.0 * a3 * dt):
                    accel_limit = acceleration_limit if accel >= 0.0 else deceleration_limit
                    if abs(accel) > accel_limit + 1e-9:
                        return (
                            f"axis {axis_index} segment acceleration limit exceeded: "
                            f"required={accel:.3f} limit={accel_limit:.3f}"
                        )
    return ""


def handle_trajectory_stop(message, master, state):
    mode = str(message.get("mode", "controlled")).strip().lower()
    if mode != "controlled":
        state["trajectory"] = inactive_trajectory_state("stop_rejected")
        state["trajectory"]["message"] = f"Unsupported stop mode: {mode}"
        print(f"Ignored unsupported trajectory_stop mode: {mode}", flush=True)
        return

    state["trajectory"] = inactive_trajectory_state("stopped")
    axes = list(range(axis_count(master)))
    ensure_csp_mode(master, state, axes)
    positions = actual_positions(master)
    state["target_positions"] = positions
    master.set_target_positions(positions)
    master.sync_trajectory_to_actual_positions()
    command_csp_positions(master, positions, axes)
    print(
        "Received trajectory_stop: "
        f"mode={mode} hold_positions={positions}",
        flush=True,
    )


def handle_trajectory_status(client, master, state):
    message = feedback_message(master, state, client["id"])
    message["type"] = "trajectory_status"
    send_client_message(client, message)


def inactive_homing_state(result="idle"):
    return {
        "active": False,
        "state": result,
        "axes": [],
        "start_time": None,
        "message": "",
        "per_axis": [],
    }


def parse_axis_indices(message, master, command_name):
    if "axes" in message:
        axes = [parse_int_field(value) for value in message.get("axes", [])]
    elif "axis" in message:
        axes = [parse_int_field(message.get("axis"))]
    else:
        axes = list(range(axis_count(master)))

    if not axes:
        raise ValueError(f"{command_name} requires at least one axis")
    invalid_axes = [
        axis_index
        for axis_index in axes
        if axis_index < 0 or axis_index >= axis_count(master)
    ]
    if invalid_axes:
        raise ValueError(f"{command_name} invalid axes: {invalid_axes}")
    return axes


def homing_axis_status(master, axis_index):
    statusword = int(master.slaves[axis_index].txpdo.statusword)
    return {
        "axis": axis_index,
        "statusword": statusword,
        "statusword_hex": f"0x{statusword:04X}",
        "operation_enabled": (statusword & 0x006F) == 0x0027,
        "target_reached": bool(statusword & (1 << 10)),
        "referenced": bool(statusword & HOMING_REFERENCED_MASK),
        "homing_error": bool(statusword & HOMING_ERROR_MASK),
        "fault": bool(statusword & 0x0008),
        "error": bool(statusword & HOMING_ERROR_MASK),
        "warning": bool(statusword & (1 << 7)),
        "actual_position": float(master.slaves[axis_index].txpdo.actual_position),
        "mode_display": int(master.slaves[axis_index].txpdo.mode_of_operation_display),
    }


def homing_status_message(master, state):
    homing = public_homing_state(state)
    axes = homing["axes"] or list(range(axis_count(master)))
    homing["per_axis"] = [
        homing_axis_status(master, axis_index)
        for axis_index in axes
    ]
    return {
        "type": "homing_status",
        "homing": homing,
    }


def public_homing_state(state):
    homing = dict(state["homing"])
    homing.pop("original_motion_modes", None)
    homing.pop("initial_referenced", None)
    homing.pop("referenced_seen_low", None)
    return homing


def send_homing_status(client, master, state):
    send_client_message(client, homing_status_message(master, state))


def update_motion_mode_summary(state):
    modes = state["motion_modes"]
    state["motion_mode"] = modes[0] if len(set(modes)) == 1 else "mixed"


def set_homing_start_bit(master, axis_indices, enabled):
    for axis_index in axis_indices:
        slave = master.slaves[axis_index]
        controlword = int(slave.rxpdo.controlword)
        if enabled:
            controlword |= HOMING_START_BIT
        else:
            controlword &= ~HOMING_START_BIT
        slave.rxpdo.controlword = controlword


def finish_homing(master, state, result, message):
    homing = state.get("homing", {})
    axes = homing.get("axes", [])
    if not axes:
        return

    set_homing_start_bit(master, axes, False)
    exchange(master, cycles=2)

    original_modes = homing.get("original_motion_modes", {})
    for axis_index in axes:
        original_mode = original_modes.get(axis_index)
        if original_mode in MOTION_MODES:
            configure_motion_mode(master, original_mode, axis_index)
            state["motion_modes"][axis_index] = original_mode

    update_motion_mode_summary(state)
    homing["active"] = False
    homing["state"] = result
    homing["message"] = message
    print(
        "Homing finished: "
        f"state={result} axes={axes} message={message} "
        f"modes={state['motion_modes']} "
        f"controlwords={[f'0x{master.slaves[index].rxpdo.controlword:04X}' for index in axes]}",
        flush=True,
    )


def handle_homing_start(message, master, state, client):
    try:
        axis_indices = parse_axis_indices(message, master, "homing_start")
    except (TypeError, ValueError) as exc:
        state["homing"] = inactive_homing_state("rejected")
        state["homing"]["message"] = str(exc)
        send_homing_status(client, master, state)
        print(f"Ignored homing_start: {exc}", flush=True)
        return

    original_modes = {
        axis_index: state["motion_modes"][axis_index]
        for axis_index in axis_indices
    }
    for axis_index in axis_indices:
        configure_mode_code(master, HOMING_MODE, axis_index)
        state["motion_modes"][axis_index] = "homing"
    update_motion_mode_summary(state)

    initial_referenced = {
        axis_index: bool(
            master.slaves[axis_index].txpdo.statusword & HOMING_REFERENCED_MASK
        )
        for axis_index in axis_indices
    }
    referenced_seen_low = {
        axis_index: not referenced
        for axis_index, referenced in initial_referenced.items()
    }

    for axis_index in axis_indices:
        slave = master.slaves[axis_index]
        slave.rxpdo.controlword = int(slave.rxpdo.controlword) | HOMING_START_BIT
    exchange(master, cycles=2)

    state["homing"] = {
        "active": True,
        "state": "running",
        "axes": axis_indices,
        "start_time": time.monotonic(),
        "message": "",
        "per_axis": [],
        "original_motion_modes": original_modes,
        "initial_referenced": initial_referenced,
        "referenced_seen_low": referenced_seen_low,
    }
    send_homing_status(client, master, state)
    print(
        "Received homing_start: "
        f"axes={axis_indices} "
        f"original_modes={original_modes} "
        f"initial_referenced={initial_referenced} "
        f"controlwords={[f'0x{master.slaves[index].rxpdo.controlword:04X}' for index in axis_indices]}",
        flush=True,
    )


def handle_homing_stop(message, master, state, client):
    try:
        axis_indices = parse_axis_indices(message, master, "homing_stop")
    except (TypeError, ValueError) as exc:
        state["homing"]["message"] = str(exc)
        send_homing_status(client, master, state)
        print(f"Ignored homing_stop: {exc}", flush=True)
        return

    if state.get("homing", {}).get("active"):
        finish_homing(master, state, "stopped", "Homing stopped by command.")
    else:
        set_homing_start_bit(master, axis_indices, False)
        exchange(master, cycles=2)
        state["homing"] = inactive_homing_state("stopped")
        state["homing"]["axes"] = axis_indices
    send_homing_status(client, master, state)


def handle_homing_status(client, master, state):
    send_homing_status(client, master, state)


def update_homing_state(master, state):
    homing = state.get("homing", {})
    if not homing.get("active"):
        return

    axes = homing.get("axes", [])
    statuses = [
        homing_axis_status(master, axis_index)
        for axis_index in axes
    ]
    homing["per_axis"] = statuses

    status_by_axis = {
        status["axis"]: status
        for status in statuses
    }
    referenced_seen_low = homing.setdefault("referenced_seen_low", {})
    for axis_index, status in status_by_axis.items():
        if not status["referenced"]:
            referenced_seen_low[axis_index] = True

    if any(status["homing_error"] for status in statuses):
        finish_homing(master, state, "error", "Homing error bit is set.")
        return

    elapsed = time.monotonic() - float(homing.get("start_time") or time.monotonic())
    monitor_ready = elapsed >= HOMING_MIN_MONITOR_TIME
    completion_ready = (
        bool(statuses)
        and monitor_ready
        and all(
            status_by_axis[axis_index]["referenced"]
            and bool(referenced_seen_low.get(axis_index, False))
            for axis_index in axes
        )
    )
    if completion_ready:
        finish_homing(master, state, "complete", "Axis referenced.")


def handle_sdo_read(message, master, client):
    data_type = str(message.get("data_type", "uint32")).strip().lower()
    try:
        axis_index = parse_int_field(message.get("axis", 0))
        index = parse_int_field(message.get("index"), 0)
        subindex = parse_int_field(message.get("subindex", 0))
    except (TypeError, ValueError) as exc:
        send_client_message(
            client,
            {
                "type": "sdo_read",
                "ok": False,
                "axis": message.get("axis", 0),
                "index": message.get("index"),
                "subindex": message.get("subindex", 0),
                "data_type": data_type,
                "error": f"Invalid SDO address: {exc}",
            },
        )
        return

    if axis_index < 0 or axis_index >= axis_count(master):
        send_client_message(
            client,
            {
                "type": "sdo_read",
                "ok": False,
                "axis": axis_index,
                "index": index,
                "subindex": subindex,
                "data_type": data_type,
                "error": f"Invalid axis index: {axis_index}",
            },
        )
        return

    readers = {
        "uint8": master.sdo_read_uint8,
        "int8": master.sdo_read_int8,
        "uint16": master.sdo_read_uint16,
        "int32": master.sdo_read_int32,
        "uint32": master.sdo_read_uint32,
        "udint": master.sdo_read_uint32,
    }
    reader = readers.get(data_type)
    if reader is None:
        send_client_message(
            client,
            {
                "type": "sdo_read",
                "ok": False,
                "axis": axis_index,
                "index": index,
                "subindex": subindex,
                "data_type": data_type,
                "error": f"Unsupported SDO data type: {data_type}",
            },
        )
        return

    try:
        value = reader(axis_index, index, subindex)
    except Exception as exc:
        send_client_message(
            client,
            {
                "type": "sdo_read",
                "ok": False,
                "axis": axis_index,
                "index": index,
                "subindex": subindex,
                "data_type": data_type,
                "error": str(exc),
            },
        )
        return

    send_client_message(
        client,
        {
            "type": "sdo_read",
            "ok": True,
            "axis": axis_index,
            "index": index,
            "subindex": subindex,
            "data_type": data_type,
            "value": int(value),
            "hex": f"0x{int(value) & 0xFFFFFFFF:08X}",
        },
    )


def parse_int_field(value, base=0):
    if isinstance(value, int):
        return value
    return int(str(value), base)


def update_active_trajectory(master, state):
    trajectory = state.get("trajectory", {})
    if not trajectory.get("active"):
        return

    axes = trajectory["axes"]
    points = trajectory["points"]
    positions = list(state["target_positions"])
    elapsed = 0.0
    active = False
    segment = 0

    for axis_index in axes:
        generator = master.trajectory_generators[axis_index]
        positions[axis_index] = generator.command_position
        elapsed = max(elapsed, generator.timed_elapsed)
        segment = max(segment, generator.timed_segment)
        active = active or generator.timed_active

    state["target_positions"] = positions
    trajectory["time_from_start"] = elapsed
    trajectory["segment"] = segment

    if not active or elapsed >= points[-1]["time_from_start"]:
        for local_index, axis_index in enumerate(axes):
            generator = master.trajectory_generators[axis_index]
            final_position = points[-1]["positions"][local_index]
            generator.command_position = final_position
            generator.target_position = final_position
            generator.command_velocity = 0.0
            generator.command_acceleration = 0.0
            generator.clear_timed_trajectory()
            master.slaves[axis_index].rxpdo.target_position = int(round(final_position))
            positions[axis_index] = final_position
        state["target_positions"] = positions
        trajectory["active"] = False
        trajectory["state"] = "complete"
        trajectory["segment"] = max(0, len(points) - 2)


def handle_manual_move_absolute(message, master, state):
    positions = [
        float(value)
        for value in message.get("positions", [])
    ]
    if len(positions) < axis_count(master):
        print(
            "Ignored manual_move_absolute because command length is too short. "
            f"expected={axis_count(master)} got={len(positions)}",
            flush=True,
        )
        return

    faults = faulted_axes(master)
    if faults:
        hold_faulted_axes(master, state)
        master.sync_trajectory_to_actual_positions()
        print(
            "Ignored manual_move_absolute because at least one drive is faulted. "
            f"faulted_axes={faults} "
            f"statuswords={[f'0x{slave.txpdo.statusword:04X}' for slave in master.slaves]}",
            flush=True,
        )
        return

    state["target_positions"] = positions[:axis_count(master)]
    pp_axes = [
        axis_index
        for axis_index, mode_name in enumerate(state["motion_modes"])
        if mode_name == "pp"
    ]
    csp_axes = [
        axis_index
        for axis_index, mode_name in enumerate(state["motion_modes"])
        if mode_name == "csp"
    ]
    csv_axes = [
        axis_index
        for axis_index, mode_name in enumerate(state["motion_modes"])
        if mode_name == "csv"
    ]
    if csv_axes:
        print(
            "Ignored manual_move_absolute for CSV axes. "
            f"csv_axes={csv_axes}",
            flush=True,
        )
    if pp_axes:
        command_profile_positions(master, state["target_positions"], pp_axes)
    if csp_axes:
        command_csp_positions(master, state["target_positions"], csp_axes)

    print(
        "Received manual_move_absolute: "
        f"modes={state['motion_modes']} "
        f"targets={state['target_positions']} "
        f"current_actual={actual_positions(master)}",
        flush=True,
    )


def handle_manual_move_relative(message, master, state):
    try:
        axis_index = int(message.get("axis"))
        distance = float(message.get("distance"))
    except (TypeError, ValueError):
        print(
            f"Ignored invalid manual_move_relative command: {message}",
            flush=True,
        )
        return

    if axis_index < 0 or axis_index >= axis_count(master):
        print(
            f"Ignored manual_move_relative for invalid axis: {axis_index}",
            flush=True,
        )
        return

    positions = actual_positions(master)
    positions[axis_index] += distance
    print(
        "Received manual_move_relative: "
        f"axis={axis_index} distance={distance:.3f} target={positions[axis_index]:.3f}",
        flush=True,
    )
    handle_manual_move_absolute({"positions": positions}, master, state)


def handle_manual_stop(message, master, state):
    mode = str(message.get("mode", "controlled")).strip().lower()
    if mode != "controlled":
        print(f"Ignored unsupported manual_stop mode: {mode}", flush=True)
        return

    if state.get("homing", {}).get("active"):
        finish_homing(master, state, "stopped", "Homing stopped by manual_stop.")

    state["trajectory"] = inactive_trajectory_state("manual_stop")
    positions = actual_positions(master)
    state["target_positions"] = positions
    master.set_target_positions(positions)
    master.sync_trajectory_to_actual_positions()
    for axis_index, motion_mode in enumerate(state["motion_modes"]):
        if motion_mode == "pp":
            command_profile_positions(master, positions, [axis_index])
        elif motion_mode == "csp":
            command_csp_positions(master, positions, [axis_index])

    print(
        "Received manual_stop: "
        f"mode={mode} hold_positions={positions}",
        flush=True,
    )


def handle_motion_limits(message, master, state):
    limits = message.get("limits", [])
    if not limits:
        return

    for axis_index, axis_limits in enumerate(limits[:axis_count(master)]):
        if len(axis_limits) < 3:
            continue

        max_velocity = float(axis_limits[0])
        acceleration = float(axis_limits[1])
        deceleration = float(axis_limits[2])
        jerk = float(axis_limits[3]) if len(axis_limits) > 3 else 0.0

        state["motion_limits"][axis_index] = [
            max_velocity,
            acceleration,
            deceleration,
            jerk,
        ]
        master.set_axis_motion_limits(
            axis_index,
            max_velocity,
            acceleration,
            deceleration,
            jerk,
        )
        master.slaves[axis_index].rxpdo.profile_velocity = int(max_velocity)
        write_profile_motion_limits(master, axis_index)

    print(f"Received motion_limits: {state['motion_limits']}", flush=True)


def handle_software_position_limits(message, master, state):
    limits = message.get("limits", [])
    if not limits:
        return

    for axis_index, axis_limits in enumerate(limits[:axis_count(master)]):
        if len(axis_limits) < 2:
            continue

        negative_limit = int(round(float(axis_limits[0])))
        positive_limit = int(round(float(axis_limits[1])))
        if negative_limit > positive_limit:
            print(
                "Ignored software_position_limits because negative limit is "
                f"greater than positive limit. axis={axis_index} "
                f"negative={negative_limit} positive={positive_limit}",
                flush=True,
            )
            continue

        write_software_position_limits(
            master,
            axis_index,
            negative_limit,
            positive_limit,
        )
        state["software_position_limits"][axis_index] = read_software_position_limits(
            master,
            axis_index,
        )

    print(
        f"Received software_position_limits: {state['software_position_limits']}",
        flush=True,
    )


def handle_motion_mode(message, master, state):
    requested_mode = str(message.get("mode", "")).strip().lower()
    if requested_mode not in MOTION_MODES:
        print(f"Ignored invalid motion mode: {requested_mode}", flush=True)
        return

    axis_value = message.get("axis", None)
    if axis_value is None:
        axis_indices = list(range(axis_count(master)))
    else:
        try:
            axis_index = int(axis_value)
        except (TypeError, ValueError):
            print(f"Ignored motion mode for invalid axis: {axis_value}", flush=True)
            return
        if axis_index < 0 or axis_index >= axis_count(master):
            print(f"Ignored motion mode for invalid axis: {axis_index}", flush=True)
            return
        axis_indices = [axis_index]

    if all(state["motion_modes"][axis_index] == requested_mode for axis_index in axis_indices):
        return

    for axis_index in axis_indices:
        hold_axis_at_actual_position(master, state, axis_index)
    master.set_target_positions(state["target_positions"])

    if requested_mode == "csv":
        for axis_index in axis_indices:
            state["target_velocities"][axis_index] = 0.0
            master.slaves[axis_index].rxpdo.target_velocity = 0

    for axis_index in axis_indices:
        configure_motion_mode(master, requested_mode, axis_index)
        state["motion_modes"][axis_index] = requested_mode

    state["motion_mode"] = (
        requested_mode
        if len(set(state["motion_modes"])) == 1
        else "mixed"
    )
    print(
        f"Motion mode changed axes={axis_indices} "
        f"to {requested_mode.upper()} modes={state['motion_modes']}",
        flush=True,
    )


def handle_target_velocities(message, master, state):
    velocities = [
        float(value)
        for value in message.get("velocities", [])
    ]
    if len(velocities) < axis_count(master):
        print(
            "Ignored target_velocities because command length is too short. "
            f"expected={axis_count(master)} got={len(velocities)}",
            flush=True,
        )
        return

    if state["motion_mode"] != "csv":
        configure_motion_mode(master, "csv")
        state["motion_mode"] = "csv"

    state["target_velocities"] = velocities[:axis_count(master)]
    for axis_index, velocity in enumerate(state["target_velocities"]):
        slave = master.slaves[axis_index]
        slave.rxpdo.mode_of_operation = CSV_MODE
        slave.rxpdo.target_velocity = int(velocity)
        slave.rxpdo.controlword = 0x000F

    print(f"Received target_velocities: {state['target_velocities']}", flush=True)


def handle_alarm_ack(master, state):
    print(
        "Received alarm_ack: pulsing fault reset bit only",
        flush=True,
    )
    original_controlwords = [
        int(slave.rxpdo.controlword)
        for slave in master.slaves
    ]

    for slave, controlword in zip(master.slaves, original_controlwords):
        slave.rxpdo.controlword = controlword & ~0x0080
    exchange(master, cycles=2)

    for slave, controlword in zip(master.slaves, original_controlwords):
        slave.rxpdo.controlword = controlword | 0x0080
    exchange(master, cycles=2)

    for slave, controlword in zip(master.slaves, original_controlwords):
        slave.rxpdo.controlword = controlword & ~0x0080
    exchange(master, cycles=2)

    print(
        "Alarm ack fault reset pulse complete. "
        f"controlwords={[f'0x{slave.rxpdo.controlword:04X}' for slave in master.slaves]}",
        flush=True,
    )


def is_operation_enabled_controlword(controlword):
    return (int(controlword) & 0x008F) in {0x000F, 0x001F}


def handle_controlword(message, master, state):
    try:
        controlword = int(str(message.get("controlword")), 0)
    except (TypeError, ValueError):
        print(f"Ignored invalid controlword: {message.get('controlword')}", flush=True)
        return

    axis_value = message.get("axis", None)
    if axis_value is None:
        axis_indices = list(range(axis_count(master)))
        for slave in master.slaves:
            slave.rxpdo.controlword = controlword
        target_text = "all axes"
    else:
        try:
            axis_index = int(axis_value)
        except (TypeError, ValueError):
            print(f"Ignored controlword for invalid axis: {axis_value}", flush=True)
            return

        if axis_index < 0 or axis_index >= axis_count(master):
            print(f"Ignored controlword for invalid axis: {axis_index}", flush=True)
            return

        axis_indices = [axis_index]
        master.slaves[axis_index].rxpdo.controlword = controlword
        target_text = f"axis {axis_index}"

    if not is_operation_enabled_controlword(controlword):
        for axis_index in axis_indices:
            hold_axis_at_actual_position(master, state, axis_index)
        master.set_target_positions(state["target_positions"])

    print(
        f"Manual controlword applied to {target_text}: 0x{controlword:04X}",
        flush=True,
    )


COMMAND_MESSAGE_TYPES = {
    "trajectory_command",
    "trajectory_stop",
    "homing_start",
    "homing_stop",
    "manual_move_absolute",
    "manual_move_relative",
    "manual_stop",
    "motion_limits",
    "software_position_limits",
    "motion_mode",
    "target_velocities",
    "alarm_ack",
    "controlword",
}


def handle_command_authority_request(client, state):
    owner = state.get("command_authority_owner")
    if owner is None or owner == client["id"]:
        state["command_authority_owner"] = client["id"]
        send_client_message(
            client,
            {
                "type": "command_authority",
                "granted": True,
                "owner": client["id"],
                "message": "Command authority granted.",
            },
        )
        print(f"Command authority granted to client {client['id']}", flush=True)
        return

    send_client_message(
        client,
        {
            "type": "command_authority",
            "granted": False,
            "owner": owner,
            "message": f"Command authority is already held by client {owner}.",
        },
    )
    print(
        f"Command authority denied to client {client['id']}; owner={owner}",
        flush=True,
    )


def handle_command_authority_release(client, state):
    owner = state.get("command_authority_owner")
    if owner == client["id"]:
        state["command_authority_owner"] = None
        message = "Command authority released."
        print(f"Command authority released by client {client['id']}", flush=True)
    else:
        message = "This client does not hold command authority."

    send_client_message(
        client,
        {
            "type": "command_authority",
            "granted": False,
            "owner": state.get("command_authority_owner"),
            "message": message,
        },
    )


def client_has_command_authority(client, state):
    return state.get("command_authority_owner") == client["id"]


def reject_command_without_authority(client, message, state):
    owner = state.get("command_authority_owner")
    send_client_message(
        client,
        {
            "type": "command_rejected",
            "command": message.get("type"),
            "owner": owner,
            "message": (
                "Command authority is required."
                if owner is None
                else f"Command authority is held by client {owner}."
            ),
        },
    )


def handle_message(message, master, state, client):
    message_type = message.get("type")

    if message_type == "command_authority_request":
        handle_command_authority_request(client, state)
        return

    if message_type == "command_authority_release":
        handle_command_authority_release(client, state)
        return

    if (
        message_type in COMMAND_MESSAGE_TYPES and
        not client_has_command_authority(client, state)
    ):
        reject_command_without_authority(client, message, state)
        return

    if message_type == "trajectory_status":
        handle_trajectory_status(client, master, state)
    elif message_type == "homing_status":
        handle_homing_status(client, master, state)
    elif message_type == "sdo_read":
        handle_sdo_read(message, master, client)
    elif message_type == "trajectory_command":
        handle_trajectory_command(message, master, state)
    elif message_type == "trajectory_stop":
        handle_trajectory_stop(message, master, state)
    elif message_type == "homing_start":
        handle_homing_start(message, master, state, client)
    elif message_type == "homing_stop":
        handle_homing_stop(message, master, state, client)
    elif message_type == "manual_move_absolute":
        handle_manual_move_absolute(message, master, state)
    elif message_type == "manual_move_relative":
        handle_manual_move_relative(message, master, state)
    elif message_type == "manual_stop":
        handle_manual_stop(message, master, state)
    elif message_type == "motion_limits":
        handle_motion_limits(message, master, state)
    elif message_type == "software_position_limits":
        handle_software_position_limits(message, master, state)
    elif message_type == "motion_mode":
        handle_motion_mode(message, master, state)
    elif message_type == "target_velocities":
        handle_target_velocities(message, master, state)
    elif message_type == "alarm_ack":
        handle_alarm_ack(master, state)
    elif message_type == "controlword":
        handle_controlword(message, master, state)


def send_client_message(client, message):
    client["conn"].sendall((json.dumps(message) + "\n").encode("utf-8"))


def service_client(client, master, state):
    conn = client["conn"]
    readable, _, _ = select.select([conn], [], [], 0.0)
    if not readable:
        return True

    chunk = conn.recv(4096)
    if not chunk:
        return False

    client["buffer"] += chunk.decode("utf-8")
    while "\n" in client["buffer"]:
        line, client["buffer"] = client["buffer"].split("\n", 1)
        if line.strip():
            handle_message(json.loads(line), master, state, client)

    return True


def send_feedback_if_due(client, master, state):
    now = time.monotonic()
    if now - client["last_feedback_time"] < FEEDBACK_PERIOD:
        return

    send_client_message(
        client,
        feedback_message(master, state, client["id"]),
    )
    client["last_feedback_time"] = now


def close_client(client, state):
    client_id = client["id"]
    if state.get("command_authority_owner") == client_id:
        state["command_authority_owner"] = None
        print(
            f"Command authority released because client {client_id} disconnected",
            flush=True,
        )
    try:
        client["conn"].close()
    except OSError:
        pass
    print(f"Client disconnected: id={client_id}", flush=True)


def update_derived_velocities(master, state, now):
    positions = actual_positions(master)
    previous_time = state.get("derived_velocity_time")
    previous_positions = state.get("derived_velocity_positions")

    if previous_time is None or previous_positions is None:
        state["derived_velocities"] = [0.0 for _ in positions]
    else:
        dt = max(now - previous_time, 1e-9)
        raw_velocities = [
            (position - previous_position) / dt
            for position, previous_position in zip(positions, previous_positions)
        ]
        alpha = state["derived_velocity_alpha"]
        state["derived_velocities"] = [
            previous_velocity * (1.0 - alpha) + raw_velocity * alpha
            for previous_velocity, raw_velocity in zip(
                state["derived_velocities"],
                raw_velocities,
            )
        ]

    state["derived_velocity_time"] = now
    state["derived_velocity_positions"] = positions


def log_status_if_due(master, state, last_status_log_time):
    if STATUS_LOG_PERIOD <= 0.0:
        return last_status_log_time

    now = time.monotonic()
    if now - last_status_log_time < STATUS_LOG_PERIOD:
        return last_status_log_time

    axis_statuses = []
    for axis_index, slave in enumerate(master.slaves):
        axis_statuses.append(
            f"A{axis_index}:"
            f"MODE={state['motion_modes'][axis_index].upper()} "
            f"SW=0x{slave.txpdo.statusword:04X} "
            f"TP={slave.rxpdo.target_position:.3f} "
            f"CMD={state['target_positions'][axis_index]:.3f} "
            f"CSP_CV={master.trajectory_generators[axis_index].command_velocity:.3f} "
            f"CSP_CP={master.trajectory_generators[axis_index].command_position:.3f} "
            f"AP={slave.txpdo.actual_position} "
            f"AV={slave.txpdo.actual_velocity} "
            f"DV={state['derived_velocities'][axis_index]:.3f} "
            f"{format_diagnostics(master.last_diagnostics[axis_index])}"
        )

    print(
        "Axis status: "
        f"WKC={master.wkc}/{master.expected_wkc()} "
        + " | ".join(axis_statuses),
        flush=True,
    )
    return now


def command_profile_positions(master, target_positions, axis_indices):
    for axis_index in axis_indices:
        target_position = target_positions[axis_index]
        slave = master.slaves[axis_index]
        slave.rxpdo.mode_of_operation = PROFILE_POSITION_MODE
        slave.rxpdo.target_position = int(target_position)
        slave.rxpdo.profile_velocity = int(slave.motion_limits.max_velocity)
        write_profile_motion_limits(master, axis_index)

    pp_setpoint_handshake(master, axis_indices)


def pp_setpoint_handshake(master, axis_indices):
    for axis_index in axis_indices:
        master.slaves[axis_index].rxpdo.controlword = PP_BASE_CONTROLWORD
    ack_cleared_before = wait_pp_setpoint_ack(
        master,
        axis_indices,
        expected=False,
        max_cycles=PP_HANDSHAKE_MAX_CYCLES,
    )

    for axis_index in axis_indices:
        master.slaves[axis_index].rxpdo.controlword = PP_NEW_SETPOINT_CONTROLWORD
    ack_set = wait_pp_setpoint_ack(
        master,
        axis_indices,
        expected=True,
        max_cycles=PP_HANDSHAKE_MAX_CYCLES,
    )

    for axis_index in axis_indices:
        master.slaves[axis_index].rxpdo.controlword = PP_BASE_CONTROLWORD
    ack_cleared_after = wait_pp_setpoint_ack(
        master,
        axis_indices,
        expected=False,
        max_cycles=PP_HANDSHAKE_MAX_CYCLES,
    )

    if not (ack_cleared_before and ack_set and ack_cleared_after):
        print(
            "PP set-point handshake did not complete cleanly. "
            f"axes={axis_indices} "
            f"ack_cleared_before={ack_cleared_before} "
            f"ack_set={ack_set} "
            f"ack_cleared_after={ack_cleared_after} "
            f"statuswords={[f'0x{master.slaves[index].txpdo.statusword:04X}' for index in axis_indices]}",
            flush=True,
        )


def wait_pp_setpoint_ack(master, axis_indices, expected, max_cycles):
    for _ in range(max_cycles):
        exchange(master)
        if all(
            bool(master.slaves[axis_index].txpdo.statusword & PP_SETPOINT_ACK_MASK)
            == expected
            for axis_index in axis_indices
        ):
            return True

    return False


def command_csp_positions(master, target_positions, axis_indices):
    for axis_index in axis_indices:
        target_position = target_positions[axis_index]
        slave = master.slaves[axis_index]
        slave.rxpdo.mode_of_operation = CSP_MODE
        slave.rxpdo.controlword = 0x000F
        slave.rxpdo.target_position = int(target_position)

    master.set_target_positions(target_positions)


def write_profile_motion_limits(master, axis_index):
    limits = master.slaves[axis_index].motion_limits
    master.sdo_write_uint32(
        axis_index,
        0x6081,
        0,
        max(0, int(limits.max_velocity)),
    )
    master.sdo_write_uint32(
        axis_index,
        0x6083,
        0,
        max(0, int(limits.acceleration)),
    )
    master.sdo_write_uint32(
        axis_index,
        0x6084,
        0,
        max(0, int(limits.deceleration)),
    )


def write_profile_jerk(master, axis_index, pp_jerk):
    value = max(0, int(pp_jerk))
    try:
        master.sdo_write_uint32(axis_index, 0x60A4, 1, value)
        print(
            f"Axis {axis_index}: PP jerk 0x60A4:01 set to {value}",
            flush=True,
        )
    except Exception as exc:
        print(
            f"Axis {axis_index}: failed to set PP jerk 0x60A4:01 "
            f"to {value}; continuing ({exc})",
            flush=True,
        )


def read_software_position_limits(master, axis_index):
    return [
        master.sdo_read_int32(axis_index, 0x607D, 1),
        master.sdo_read_int32(axis_index, 0x607D, 2),
    ]


def read_all_software_position_limits(master):
    limits = []
    for axis_index in range(axis_count(master)):
        try:
            limits.append(read_software_position_limits(master, axis_index))
        except Exception as exc:
            print(
                f"Axis {axis_index}: failed to read software position limits "
                f"0x607D:01/02 ({exc})",
                flush=True,
            )
            limits.append([0, 0])

    return limits


def write_software_position_limits(
    master,
    axis_index,
    negative_limit,
    positive_limit,
):
    master.sdo_write_int32(axis_index, 0x607D, 1, negative_limit)
    master.sdo_write_int32(axis_index, 0x607D, 2, positive_limit)


def allocate_client_id(clients):
    used_ids = {client["id"] for client in clients}
    client_id = 1
    while client_id in used_ids:
        client_id += 1
    return client_id


def wait_until_cycle_time(target_time, spin_wait_time):
    spin_wait_time = max(0.0, float(spin_wait_time))
    sleep_until = target_time - spin_wait_time

    now = time.monotonic()
    if now < sleep_until:
        time.sleep(sleep_until - now)

    while time.monotonic() < target_time:
        pass


def run_server_loop(server, master, state):
    server.setblocking(False)
    clients = []
    last_feedback_update_time = 0.0
    last_status_log_time = 0.0
    cycle_stats = CycleStats()
    last_cycle_start_time = None
    last_cycle_stats_log_time = time.monotonic()
    next_cycle_time = time.monotonic()
    spin_wait_time = float(state.get("spin_wait_time", 0.0))

    while True:
        wait_until_cycle_time(next_cycle_time, spin_wait_time)

        cycle_start_time = time.monotonic()
        if last_cycle_start_time is not None:
            cycle_stats.add("loop", cycle_start_time - last_cycle_start_time)
        last_cycle_start_time = cycle_start_time
        deadline_late = cycle_start_time - next_cycle_time
        if deadline_late > 0.0:
            cycle_stats.add("deadline_late", deadline_late)
        next_cycle_time += master.cycle_time
        if cycle_start_time - next_cycle_time > master.cycle_time:
            next_cycle_time = cycle_start_time + master.cycle_time

        hold_faulted_axes(master, state)
        update_active_trajectory(master, state)
        exchange(master, cycle_stats=cycle_stats, sleep_after=False)
        update_homing_state(master, state)

        now = time.monotonic()
        if clients and now - last_feedback_update_time >= FEEDBACK_PERIOD:
            update_derived_velocities(master, state, now)
            last_feedback_update_time = now

        if now - last_cycle_stats_log_time >= CYCLE_STATS_PERIOD:
            report = cycle_stats.report_and_reset()
            if report:
                print(f"EtherCAT cycle stats: {report}", flush=True)
            last_cycle_stats_log_time = now

        while True:
            try:
                conn, addr = server.accept()
                conn.setblocking(False)
                client_id = allocate_client_id(clients)
                client = {
                    "id": client_id,
                    "addr": addr,
                    "conn": conn,
                    "buffer": "",
                    "last_feedback_time": 0.0,
                }
                clients.append(client)
                print(
                    f"Client connected: id={client['id']} addr={addr}",
                    flush=True,
                )
            except BlockingIOError:
                break

        for client in list(clients):
            try:
                if not service_client(client, master, state):
                    close_client(client, state)
                    clients.remove(client)
                    continue
                send_feedback_if_due(client, master, state)
            except OSError as exc:
                print(
                    f"Client connection error: id={client['id']} error={exc}",
                    flush=True,
                )
                close_client(client, state)
                clients.remove(client)

        last_status_log_time = log_status_if_due(
            master,
            state,
            last_status_log_time,
        )


def main():
    args = parse_args()
    if args.axis_count < 1:
        raise ValueError("--axis-count must be at least 1")

    motion_limits = [
        {
            "max_velocity": args.max_velocity,
            "acceleration": args.acceleration,
            "deceleration": args.deceleration,
            "jerk": args.jerk,
        }
        for _ in range(args.axis_count)
    ]
    master = create_master(args, motion_limits)

    try:
        initialize_drive(
            master,
            args.motion_mode,
            args.pp_jerk,
        )
        for slave in master.slaves:
            slave.rxpdo.profile_velocity = int(args.max_velocity)

        master.last_diagnostics = read_all_diagnostics(master)
        software_position_limits = read_all_software_position_limits(master)
        positions = actual_positions(master)
        print(
            "Drive initialized. "
            f"backend={args.backend} "
            f"axes={args.axis_count} "
            f"cycle_time={args.cycle_time} "
            f"spin_wait_time={args.spin_wait_time} "
            f"csp_counts_per_unit={args.csp_counts_per_unit} "
            f"jerk={args.jerk} "
            f"pp_jerk={args.pp_jerk} "
            f"derived_velocity_alpha={args.derived_velocity_alpha} "
            f"statuswords={[f'0x{slave.txpdo.statusword:04X}' for slave in master.slaves]} "
            f"software_position_limits={software_position_limits} "
            f"AP={positions}",
            flush=True,
        )
        state = {
            "target_positions": positions,
            "target_velocities": [0.0 for _ in range(args.axis_count)],
            "derived_velocities": [0.0 for _ in range(args.axis_count)],
            "derived_velocity_positions": positions,
            "derived_velocity_time": None,
            "derived_velocity_alpha": max(
                0.0,
                min(1.0, args.derived_velocity_alpha),
            ),
            "motion_limits": [
                [
                    args.max_velocity,
                    args.acceleration,
                    args.deceleration,
                    args.jerk,
                ]
                for _ in range(args.axis_count)
            ],
            "software_position_limits": software_position_limits,
            "motion_mode": args.motion_mode,
            "motion_modes": [
                args.motion_mode
                for _ in range(args.axis_count)
            ],
            "position_counts_per_unit": (
                args.csp_counts_per_unit
                if args.backend == "pysoem"
                else 1.0
            ),
            "capabilities": {
                "position_loop_gain": args.backend == "mock",
                "profile_motion_limits": True,
                "software_position_limits": True,
                "csp_trajectory_feedback": True,
            },
            "trajectory": inactive_trajectory_state(),
            "homing": inactive_homing_state(),
            "command_authority_owner": None,
            "spin_wait_time": max(0.0, args.spin_wait_time),
        }

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((args.host, args.port))
            server.listen(1)
            print(
                f"Axis server listening on {args.host}:{args.port} "
                f"backend={args.backend} axes={args.axis_count}",
                flush=True,
            )
            run_server_loop(server, master, state)

    finally:
        master.close()


if __name__ == "__main__":
    main()
