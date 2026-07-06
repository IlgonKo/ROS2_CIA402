import argparse
from collections import deque
import json
import math
import os
from pathlib import Path
import select
import socket
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from device import available_device_names, get_device_profile
from device.cmmt.virtual_servo import VirtualCiA402Servo
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
HOMING_MODE = DEVICE_PROFILE.HOMING_MODE
CSP_MODE = DEVICE_PROFILE.CSP_MODE
CSV_MODE = DEVICE_PROFILE.CSV_MODE
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
    "csp": (
        "target_position",
    ),
    "csv": (
        "target_velocity",
    ),
    "homing": (),
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
        "--backend",
        choices=["mock", "pysoem"],
        default=os.environ.get("AXIS_SERVER_BACKEND", "pysoem").lower(),
        help="Device backend. pysoem drives real EtherCAT slaves; mock uses VirtualCiA402Servo.",
    )
    parser.add_argument(
        "--device",
        choices=available_device_names(),
        default=DEVICE_PROFILE.name,
        help="Connected drive device profile.",
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
            csp_velocity_offset_enabled=args.csp_velocity_offset,
            csp_command_step_threshold=args.csp_command_step_threshold,
            csp_command_step_error_threshold=(
                args.csp_command_step_error_threshold
            ),
        )
        for axis_index, limits in enumerate(motion_limits):
            master.set_axis_motion_limits(
                axis_index,
                limits["max_velocity"],
                limits["acceleration"],
                limits["deceleration"],
                limits["jerk"],
            )
        require_pdo_fields_for_mode(master, args.motion_mode)
        require_txpdo_fields(master)
        return master

    return PySOEMMaster(
        interface_name=args.interface,
        slave_count=args.axis_count,
        cycle_time=args.cycle_time,
        motion_limits=motion_limits,
        device_profile=get_device_profile(args.device),
        csp_counts_per_unit=args.csp_counts_per_unit,
        sync_mode=sync_mode,
        dc_enabled=args.dc_enabled,
        dc_sync0_shift_time=args.dc_sync0_shift_time,
        txpdo_setpoint_entry=args.txpdo_setpoint_entry,
        csp_velocity_offset_enabled=args.csp_velocity_offset,
        csp_command_step_threshold=args.csp_command_step_threshold,
        csp_command_step_error_threshold=args.csp_command_step_error_threshold,
    )


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


def require_pdo_fields_for_mode(master, mode_name, axis_index=None):
    axis_indices = (
        range(axis_count(master))
        if axis_index is None
        else [axis_index]
    )
    rxpdo_fields = required_rxpdo_fields_for_mode(
        mode_name,
        getattr(master, "csp_velocity_offset_enabled", False),
    )
    for current_axis in axis_indices:
        require_pdo_fields(
            master.slaves[current_axis].rxpdo,
            rxpdo_fields,
            context=f"Axis {current_axis} RxPDO {mode_name.upper()}",
        )


def require_txpdo_fields(master):
    txpdo_fields = required_txpdo_fields_for_entry(
        getattr(master, "txpdo_setpoint_entry", False),
    )
    for axis_index, slave in enumerate(master.slaves):
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
        self.latest = {}
        self.last_tx_time = None

    def add(self, name, seconds):
        self.latest[name] = seconds
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
        self.latest = {}
        return " | ".join(parts)


class DcPhaseLock:
    def __init__(
        self,
        enabled,
        cycle_time,
        phase_offset_ns,
        kp,
        ki,
        max_correction,
    ):
        self.enabled = bool(enabled)
        self.cycle_time_ns = max(1, int(round(float(cycle_time) * 1_000_000_000.0)))
        self.phase_offset_ns = int(phase_offset_ns)
        self.kp = float(kp)
        self.ki = float(ki)
        self.max_correction = abs(float(max_correction))
        self.integral_error_s = 0.0
        self.correction_s = 0.0

    def target_phase_ns(self):
        return (self.cycle_time_ns - self.phase_offset_ns) % self.cycle_time_ns

    def correction(self):
        return self.correction_s if self.enabled else 0.0

    def update(self, dc_time_ns, stats):
        if dc_time_ns is None:
            return

        phase_error_ns = self._wrapped_phase_error_ns(dc_time_ns)
        phase_error_s = phase_error_ns / 1_000_000_000.0
        stats.add("dc_phase_error", phase_error_s)

        if not self.enabled:
            self.integral_error_s = 0.0
            self.correction_s = 0.0
            stats.add("dc_phase_correction", 0.0)
            return

        self.integral_error_s += phase_error_s
        self.integral_error_s = self._clamp(
            self.integral_error_s,
            -self.max_correction,
            self.max_correction,
        )
        self.correction_s = -(
            self.kp * phase_error_s
            + self.ki * self.integral_error_s
        )
        self.correction_s = self._clamp(
            self.correction_s,
            -self.max_correction,
            self.max_correction,
        )

        stats.add("dc_phase_correction", self.correction_s)

    def _wrapped_phase_error_ns(self, dc_time_ns):
        actual_phase = int(dc_time_ns) % self.cycle_time_ns
        error = actual_phase - self.target_phase_ns()
        half_cycle = self.cycle_time_ns // 2
        if error > half_cycle:
            error -= self.cycle_time_ns
        elif error < -half_cycle:
            error += self.cycle_time_ns
        return error

    @staticmethod
    def _clamp(value, minimum, maximum):
        return max(minimum, min(maximum, value))


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


def exchange_prepared(master, cycle_stats=None):
    exchange_start = time.monotonic()
    if cycle_stats is not None:
        cycle_stats.add_tx_time(exchange_start)
    master.send_prepared_processdata()
    master.receive_processdata()
    exchange_done = time.monotonic()
    if cycle_stats is not None:
        cycle_stats.add("pdo_io", exchange_done - exchange_start)
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
    return DEVICE_PROFILE.read_diagnostics(master, axis_index)


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


def format_axis_diagnostics(diagnostics_list):
    return " | ".join(
        f"A{index}:{format_diagnostics(diagnostics)}"
        for index, diagnostics in enumerate(diagnostics_list)
    )


def mode_code(mode_name):
    return DEVICE_PROFILE.mode_code(mode_name)


def configure_motion_mode(master, mode_name, axis_index=None):
    require_pdo_fields_for_mode(master, mode_name, axis_index)
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
        DEVICE_PROFILE.configure_mode_code(master, current_axis, code)
    exchange(master, cycles=5)


def initialize_drive(master, motion_mode, pp_jerk, csp_interpolation_mode):
    master.connect()
    require_txpdo_fields(master)
    write_csp_interpolation_modes(master, csp_interpolation_mode)
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


def write_csp_interpolation_modes(master, csp_interpolation_mode):
    value = int(csp_interpolation_mode)
    if value <= 0:
        return

    for axis_index in range(axis_count(master)):
        try:
            readback = DEVICE_PROFILE.write_csp_interpolation_mode(
                master,
                axis_index,
                value,
            )
            print(
                "Axis "
                f"{axis_index}: CSP interpolation mode "
                f"set to {value} readback={readback}",
                flush=True,
            )
        except Exception as exc:
            print(
                "Axis "
                f"{axis_index}: failed to set CSP interpolation mode "
                f"to {value}; continuing ({exc})",
                flush=True,
            )


def feedback_message(master, state, client_id=None):
    owner = state.get("command_authority_owner")
    return {
        "type": "feedback",
        "drive_initialized": bool(state.get("drive_initialized", True)),
        "initialization_error": state.get("initialization_error", ""),
        "target_positions": state["target_positions"],
        "actual_positions": [
            float(slave.txpdo.actual_position)
            for slave in master.slaves
        ],
        "actual_velocities": [
            float(slave.txpdo.actual_velocity)
            for slave in master.slaves
        ],
        "setpoint_positions": [
            float(slave.txpdo.setpoint_position)
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
            master.slaves[axis_index].rxpdo.mode_of_operation = CSP_MODE
            master.slaves[axis_index].rxpdo.controlword = 0x000F
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


def same_trajectory_target(active_trajectory, axes, points, tolerance=1e-6):
    if not active_trajectory.get("active"):
        return False
    if active_trajectory.get("axes") != axes:
        return False

    active_points = active_trajectory.get("points") or []
    if not active_points or not points:
        return False

    active_target = active_points[-1].get("positions", [])
    target = points[-1].get("positions", [])
    if len(active_target) != len(target):
        return False

    return all(
        abs(float(active_value) - float(target_value)) <= tolerance
        for active_value, target_value in zip(active_target, target)
    )


def trajectory_debug_snapshot(master, state, axes):
    snapshots = []
    trajectory = state.get("trajectory", {})
    for axis_index in axes:
        generator = master.trajectory_generators[axis_index]
        timed_start = None
        timed_end = None
        if generator.timed_points:
            timed_start = generator.timed_points[0]
            timed_end = generator.timed_points[-1]
        snapshots.append(
            {
                "axis": axis_index,
                "rxpdo_target": int(master.slaves[axis_index].rxpdo.target_position),
                "actual": int(master.slaves[axis_index].txpdo.actual_position),
                "command": round(float(generator.command_position), 3),
                "target": round(float(generator.target_position), 3),
                "velocity": round(float(generator.command_velocity), 3),
                "timed_active": bool(generator.timed_active),
                "timed_elapsed": round(float(generator.timed_elapsed), 6),
                "timed_segment": int(generator.timed_segment),
                "timed_start": timed_start,
                "timed_end": timed_end,
            }
        )
    return {
        "trajectory_active": bool(trajectory.get("active", False)),
        "trajectory_state": trajectory.get("state"),
        "trajectory_time": round(float(trajectory.get("time_from_start", 0.0)), 6),
        "axes": snapshots,
    }


def log_trajectory_debug(label, master, state, axes, extra=None):
    if not TRAJECTORY_DEBUG_LOGS:
        return

    payload = trajectory_debug_snapshot(master, state, axes)
    if extra:
        payload.update(extra)
    print(
        f"Trajectory debug {label}: {json.dumps(payload, sort_keys=True)}",
        flush=True,
    )


def log_trajectory_snapshot(label, master, state, axes, points=None, extra=None):
    if not TRAJECTORY_SNAPSHOT_LOGS:
        return

    scale = max(float(getattr(master, "csp_counts_per_unit", 1.0)), 1e-9)
    axis_parts = []
    for axis_index in axes:
        slave = master.slaves[axis_index]
        generator = master.trajectory_generators[axis_index]
        command_position = float(generator.command_position)
        actual_position = float(slave.txpdo.actual_position)
        command_velocity = float(generator.command_velocity) / scale
        axis_parts.append(
            "A"
            f"{axis_index}:"
            f"SW=0x{int(slave.txpdo.statusword):04X},"
            f"MD={int(slave.txpdo.mode_of_operation_display)},"
            f"AP={actual_position:.3f},"
            f"AV={float(slave.txpdo.actual_velocity):.3f},"
            f"CP={command_position:.3f},"
            f"CV={command_velocity:.3f},"
            f"GAP={command_position - actual_position:.3f}"
        )

    now = time.monotonic()
    last_complete_time = state.get("last_trajectory_complete_time")
    since_complete = (
        "None"
        if last_complete_time is None
        else f"{now - last_complete_time:.3f}"
    )
    duration = None
    target = None
    if points:
        duration = points[-1].get("time_from_start")
        target = points[-1].get("positions")

    details = [
        f"seq={state.get('trajectory_sequence', 0)}",
        f"since_complete_s={since_complete}",
        f"duration={duration}",
        f"target={target}",
    ]
    if extra:
        details.extend(f"{key}={value}" for key, value in extra.items())

    print(
        f"Trajectory snapshot {label}: "
        f"{' '.join(details)} "
        f"{' | '.join(axis_parts)}",
        flush=True,
    )


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
    log_trajectory_debug(
        "before_command",
        master,
        state,
        axes,
        {
            "raw_points": points,
        },
    )

    if len(points) == 1:
        current = [
            float(master.trajectory_generators[axis_index].command_position)
            for axis_index in axes
        ]
        current_velocities = [
            float(master.trajectory_generators[axis_index].command_velocity)
            for axis_index in axes
        ]
        target = points[0]["positions"]
        duration = estimate_trajectory_duration(master, axes, current, target)
        points = [
            {
                "positions": current,
                "velocities": current_velocities,
                "accelerations": [0.0 for _ in axes],
                "time_from_start": 0.0,
            },
            {
                "positions": target,
                "velocities": [0.0 for _ in axes],
                "accelerations": [0.0 for _ in axes],
                "time_from_start": duration,
            },
        ]

        log_trajectory_debug(
            "expanded_single_point",
            master,
            state,
            axes,
            {
                "expanded_points": points,
            },
        )

    if same_trajectory_target(state.get("trajectory", {}), axes, points):
        print(
            "Ignored duplicate active trajectory_command: "
            f"axes={axes} target={points[-1]['positions']}",
            flush=True,
        )
        return

    points = retime_trajectory_to_motion_limits(master, axes, points)

    validation_error = validate_trajectory_limits(master, axes, points)
    if validation_error:
        reject_trajectory(state, validation_error)
        return

    log_trajectory_snapshot("start_request", master, state, axes, points)

    for local_index, axis_index in enumerate(axes):
        master.trajectory_generators[axis_index].set_timed_trajectory(
            axis_timed_points(points, local_index)
        )
        master.slaves[axis_index].rxpdo.mode_of_operation = CSP_MODE
        master.slaves[axis_index].rxpdo.controlword = 0x000F

    log_trajectory_debug(
        "after_set_timed_trajectory",
        master,
        state,
        axes,
        {
            "points": points,
        },
    )

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
    state["trajectory_sequence"] = state.get("trajectory_sequence", 0) + 1
    log_trajectory_snapshot("start_active", master, state, axes, points)
    if ROS_BRIDGE_COMMAND_LOGS:
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


def retime_trajectory_to_motion_limits(master, axes, points):
    if len(points) < 2:
        return points

    retimed_points = [
        {
            key: (list(value) if isinstance(value, list) else value)
            for key, value in point.items()
        }
        for point in points
    ]
    adjusted = False
    current_time = float(retimed_points[0]["time_from_start"])
    retimed_points[0]["time_from_start"] = current_time

    for point_index in range(1, len(retimed_points)):
        previous = retimed_points[point_index - 1]
        current = retimed_points[point_index]
        requested_dt = (
            float(points[point_index]["time_from_start"])
            - float(points[point_index - 1]["time_from_start"])
        )
        required_dt = max(requested_dt, master.cycle_time)

        for local_index, axis_index in enumerate(axes):
            required_dt = max(
                required_dt,
                required_segment_duration_for_axis(
                    master,
                    axis_index,
                    previous,
                    current,
                    local_index,
                    required_dt,
                ),
            )

        if required_dt > requested_dt + 1e-9:
            adjusted = True
        current_time += required_dt
        current["time_from_start"] = current_time

    if adjusted and ROS_BRIDGE_COMMAND_LOGS:
        print(
            "Retimed trajectory to motion limits: "
            f"requested_duration={points[-1]['time_from_start']:.6f} "
            f"retimed_duration={retimed_points[-1]['time_from_start']:.6f}",
            flush=True,
        )

    return retimed_points


def required_segment_duration_for_axis(
    master,
    axis_index,
    previous,
    current,
    local_index,
    initial_dt,
):
    distance = abs(
        float(current["positions"][local_index])
        - float(previous["positions"][local_index])
    )
    if distance <= 1e-9:
        return max(float(initial_dt), master.cycle_time)

    velocity_limit = max(
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
        float(initial_dt),
        1.875 * distance / velocity_limit,
        math.sqrt(5.773502691896258 * distance / accel_limit),
        master.cycle_time,
    )

    if "velocities" not in previous and "velocities" not in current:
        return duration

    for _ in range(24):
        peak_velocity, peak_acceleration = sample_segment_peaks(
            previous,
            current,
            local_index,
            duration,
        )
        velocity_ratio = peak_velocity / velocity_limit
        acceleration_ratio = peak_acceleration / accel_limit
        ratio = max(velocity_ratio, math.sqrt(acceleration_ratio), 1.0)
        if ratio <= 1.0001:
            return duration
        duration *= min(max(ratio, 1.02), 2.0)

    return duration


def sample_segment_peaks(previous, current, local_index, duration):
    duration = max(float(duration), 1e-9)
    p0 = float(previous["positions"][local_index])
    p1 = float(current["positions"][local_index])
    v0 = trajectory_point_value(previous, "velocities", local_index, 0.0)
    v1 = trajectory_point_value(current, "velocities", local_index, 0.0)
    a0 = trajectory_point_value(previous, "accelerations", local_index, 0.0)
    a1 = trajectory_point_value(current, "accelerations", local_index, 0.0)

    duration2 = duration * duration
    duration3 = duration2 * duration
    duration4 = duration3 * duration
    duration5 = duration4 * duration
    c1 = v0
    c2 = a0 / 2.0
    c3 = (
        20.0 * (p1 - p0)
        - (8.0 * v1 + 12.0 * v0) * duration
        - (3.0 * a0 - a1) * duration2
    ) / (2.0 * duration3)
    c4 = (
        30.0 * (p0 - p1)
        + (14.0 * v1 + 16.0 * v0) * duration
        + (3.0 * a0 - 2.0 * a1) * duration2
    ) / (2.0 * duration4)
    c5 = (
        12.0 * (p1 - p0)
        - (6.0 * v1 + 6.0 * v0) * duration
        - (a0 - a1) * duration2
    ) / (2.0 * duration5)

    peak_velocity = 0.0
    peak_acceleration = 0.0
    for sample_index in range(65):
        t = duration * sample_index / 64.0
        velocity = (
            c1
            + 2.0 * c2 * t
            + 3.0 * c3 * t * t
            + 4.0 * c4 * t * t * t
            + 5.0 * c5 * t * t * t * t
        )
        acceleration = (
            2.0 * c2
            + 6.0 * c3 * t
            + 12.0 * c4 * t * t
            + 20.0 * c5 * t * t * t
        )
        peak_velocity = max(peak_velocity, abs(velocity))
        peak_acceleration = max(peak_acceleration, abs(acceleration))

    return peak_velocity, peak_acceleration


def trajectory_point_value(point, key, local_index, default):
    values = point.get(key)
    if values is None:
        return default
    return float(values[local_index])


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
        log_trajectory_snapshot(
            "complete_before_clear",
            master,
            state,
            axes,
            points,
            {
                "elapsed": f"{elapsed:.6f}",
                "active": active,
            },
        )
        log_trajectory_debug(
            "before_complete",
            master,
            state,
            axes,
            {
                "elapsed": elapsed,
                "duration": points[-1]["time_from_start"],
                "active": active,
                "final_positions": points[-1]["positions"],
            },
        )
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
        state["last_trajectory_complete_time"] = time.monotonic()
        log_trajectory_snapshot(
            "complete",
            master,
            state,
            axes,
            points,
            {"elapsed": f"{elapsed:.6f}"},
        )
        log_trajectory_debug(
            "after_complete",
            master,
            state,
            axes,
            {
                "elapsed": elapsed,
                "duration": points[-1]["time_from_start"],
                "final_positions": points[-1]["positions"],
            },
        )


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

    previous_target_positions = list(state["target_positions"])
    state["target_positions"] = positions[:axis_count(master)]
    pp_axes = [
        axis_index
        for axis_index, mode_name in enumerate(state["motion_modes"])
        if (
            mode_name == "pp"
            and state["target_positions"][axis_index]
            != previous_target_positions[axis_index]
        )
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
        if master.slaves[axis_index].rxpdo.has_field("profile_velocity"):
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
        require_pdo_fields_for_mode(master, requested_mode, axis_index)

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
    else:
        require_pdo_fields_for_mode(master, "csv")

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
    force = bool(client.get("last_message_force", False))
    if owner is None or owner == client["id"] or force:
        previous_owner = owner
        state["command_authority_owner"] = client["id"]
        send_client_message(
            client,
            {
                "type": "command_authority",
                "granted": True,
                "owner": client["id"],
                "message": (
                    "Command authority granted."
                    if previous_owner in (None, client["id"])
                    else f"Command authority taken from client {previous_owner}."
                ),
            },
        )
        if previous_owner not in (None, client["id"]):
            print(
                "Command authority force-granted to "
                f"client {client['id']}; previous_owner={previous_owner}",
                flush=True,
            )
        else:
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


def reject_command_when_not_initialized(client, message, state):
    send_client_message(
        client,
        {
            "type": "command_rejected",
            "command": message.get("type"),
            "message": (
                "Axis Server is running, but EtherCAT drive initialization "
                f"failed: {state.get('initialization_error', 'unknown error')}"
            ),
        },
    )


def handle_message(message, master, state, client):
    message_type = message.get("type")

    if message_type == "command_authority_request":
        client["last_message_force"] = bool(message.get("force", False))
        handle_command_authority_request(client, state)
        client["last_message_force"] = False
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

    if (
        message_type in COMMAND_MESSAGE_TYPES
        and not state.get("drive_initialized", True)
    ):
        reject_command_when_not_initialized(client, message, state)
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


def format_latest_cycle_value(cycle_stats, name):
    value = cycle_stats.latest.get(name)
    if value is None:
        return "None"
    return f"{value * 1000.0:.3f}"


def velocity_anomaly_dc_snapshot(master, state, cycle_stats):
    cycle_time_ns = max(1, int(round(float(master.cycle_time) * 1_000_000_000.0)))
    phase_offset_ns = int(state.get("dc_phase_offset_ns", 0))
    target_phase_ns = (cycle_time_ns - phase_offset_ns) % cycle_time_ns
    tx_dc_time_ns = getattr(master, "last_tx_dc_time_ns", None)
    direct_tx_dc_time_ns = getattr(master, "last_direct_tx_dc_time_ns", None)
    actual_phase_ns = None
    phase_error_ns = None
    if tx_dc_time_ns is not None:
        actual_phase_ns = int(tx_dc_time_ns) % cycle_time_ns
        phase_error_ns = actual_phase_ns - target_phase_ns
        half_cycle_ns = cycle_time_ns // 2
        if phase_error_ns > half_cycle_ns:
            phase_error_ns -= cycle_time_ns
        elif phase_error_ns < -half_cycle_ns:
            phase_error_ns += cycle_time_ns

    direct_phase_ns = None
    if direct_tx_dc_time_ns is not None:
        direct_phase_ns = int(direct_tx_dc_time_ns) % cycle_time_ns

    def ns_to_ms(value):
        return "None" if value is None else f"{value / 1_000_000.0:.3f}"

    return (
        f"dc_phase_ms={format_latest_cycle_value(cycle_stats, 'dc_phase_error')} "
        f"dc_corr_ms={format_latest_cycle_value(cycle_stats, 'dc_phase_correction')} "
        f"tx_prepare_ms={format_latest_cycle_value(cycle_stats, 'tx_prepare')} "
        f"send_call_ms={format_latest_cycle_value(cycle_stats, 'send_call')} "
        f"pdo_io_ms={format_latest_cycle_value(cycle_stats, 'pdo_io')} "
        f"tx_gap_ms={format_latest_cycle_value(cycle_stats, 'tx_gap')} "
        f"tx_phase_ms={ns_to_ms(actual_phase_ns)} "
        f"target_phase_ms={ns_to_ms(target_phase_ns)} "
        f"phase_err_calc_ms={ns_to_ms(phase_error_ns)} "
        f"direct_tx_phase_ms={ns_to_ms(direct_phase_ns)} "
        f"dc_tx_est_delta_ms={format_latest_cycle_value(cycle_stats, 'dc_tx_estimation_delta')}"
    )


def record_tx_history(master, state, cycle_stats):
    history = state.get("tx_history")
    if history is None:
        return

    scale = max(float(getattr(master, "csp_counts_per_unit", 1.0)), 1e-9)
    cycle_time_ns = max(1, int(round(float(master.cycle_time) * 1_000_000_000.0)))
    tx_dc_time_ns = getattr(master, "last_tx_dc_time_ns", None)
    tx_phase_ms = None
    if tx_dc_time_ns is not None:
        tx_phase_ms = (int(tx_dc_time_ns) % cycle_time_ns) / 1_000_000.0

    history.append(
        {
            "time": time.monotonic(),
            "targets": [
                int(slave.rxpdo.target_position)
                for slave in master.slaves
            ],
            "modes": [
                int(slave.rxpdo.mode_of_operation)
                for slave in master.slaves
            ],
            "command_velocities": [
                float(generator.command_velocity) / scale
                for generator in master.trajectory_generators
            ],
            "tx_gap_ms": cycle_stats.latest.get("tx_gap", 0.0) * 1000.0,
            "tx_phase_ms": tx_phase_ms,
        }
    )


def format_tx_history_for_axes(state, axes, sample_count=10):
    history = list(state.get("tx_history") or [])
    if not history:
        return "TX_HISTORY=None"

    samples = history[-sample_count:]
    parts = []
    for axis_index in axes:
        previous_target = None
        entries = []
        for sample in samples:
            target = sample["targets"][axis_index]
            delta = None if previous_target is None else target - previous_target
            previous_target = target
            phase = sample.get("tx_phase_ms")
            phase_text = "None" if phase is None else f"{phase:.3f}"
            entries.append(
                f"{target}/{delta if delta is not None else 'NA'}"
                f"@{phase_text}"
            )
        parts.append(f"A{axis_index}=[" + ",".join(entries) + "]")

    return "TX_HISTORY " + " ".join(parts)


def position_feedback_lag(state, axis_index, feedback_position):
    history = list(state.get("tx_history") or [])
    if not history:
        return None

    best = None
    last_index = len(history) - 1
    for sample_index, sample in enumerate(history):
        target = int(sample["targets"][axis_index])
        error = float(feedback_position) - float(target)
        candidate = {
            "lag": last_index - sample_index,
            "target": target,
            "error": error,
            "abs_error": abs(error),
            "tx_phase_ms": sample.get("tx_phase_ms"),
        }
        if best is None or candidate["abs_error"] < best["abs_error"]:
            best = candidate

    return best


def format_position_feedback_lag(master, state, axes):
    parts = []
    for axis_index in axes:
        generator = master.trajectory_generators[axis_index]
        feedback_position = float(master.slaves[axis_index].txpdo.actual_position)
        command_position = float(generator.command_position)
        command_diff = feedback_position - command_position
        lag = position_feedback_lag(state, axis_index, feedback_position)
        if lag is None:
            parts.append(
                f"A{axis_index}:FB={feedback_position:.0f},"
                f"CP={command_position:.3f},DIFF={command_diff:.3f},LAG=None"
            )
            continue

        phase = lag.get("tx_phase_ms")
        phase_text = "None" if phase is None else f"{phase:.3f}"
        parts.append(
            f"A{axis_index}:FB={feedback_position:.0f},"
            f"CP={command_position:.3f},"
            f"DIFF={command_diff:.3f},"
            f"LAG={lag['lag']},"
            f"LAG_TARGET={lag['target']},"
            f"LAG_ERR={lag['error']:.3f},"
            f"LAG_PHASE_MS={phase_text}"
        )

    return "POS_FB_LAG " + " | ".join(parts)


def log_position_feedback_lag(master, state):
    if not POSITION_FEEDBACK_LAG_LOGS:
        return

    now = time.monotonic()
    last_log_time = state.get("position_feedback_lag_last_log_time", 0.0)
    if now - last_log_time < POSITION_FEEDBACK_LAG_LOG_PERIOD:
        return

    axes = list(state.get("trajectory", {}).get("axes", []))
    if not axes:
        return

    print(
        "Position feedback lag: "
        f"trajectory_state={state.get('trajectory', {}).get('state')} "
        f"trajectory_time={state.get('trajectory', {}).get('time_from_start', 0.0):.3f} "
        f"{format_position_feedback_lag(master, state, axes)}",
        flush=True,
    )
    state["position_feedback_lag_last_log_time"] = now


def log_velocity_anomalies(master, state, cycle_stats):
    if not VELOCITY_ANOMALY_LOGS:
        return

    now = time.monotonic()
    last_log_time = state.get("velocity_anomaly_last_log_time", 0.0)
    if now - last_log_time < VELOCITY_ANOMALY_LOG_PERIOD:
        return

    previous_actual = state.get("velocity_anomaly_previous_actual")
    current_actual = [
        float(slave.txpdo.actual_velocity)
        for slave in master.slaves
    ]
    state["velocity_anomaly_previous_actual"] = current_actual
    if previous_actual is None:
        return

    active_axes = set(state.get("trajectory", {}).get("axes", []))
    dc_phase_values = cycle_stats.values.get("dc_phase_error", {})
    latest_dc_phase_ms = None
    if dc_phase_values.get("count"):
        latest_dc_phase_ms = (
            dc_phase_values["sum"] / dc_phase_values["count"]
        ) * 1000.0

    anomalies = []
    anomaly_axes = []
    for axis_index, actual_velocity in enumerate(current_actual):
        if axis_index not in active_axes:
            continue

        generator = master.trajectory_generators[axis_index]
        command_velocity = (
            float(generator.command_velocity)
            / max(float(master.csp_counts_per_unit), 1e-9)
        )
        velocity_error = actual_velocity - command_velocity
        velocity_jump = actual_velocity - previous_actual[axis_index]
        if (
            abs(velocity_error) < VELOCITY_ANOMALY_THRESHOLD
            and abs(velocity_jump) < VELOCITY_JUMP_THRESHOLD
        ):
            continue

        anomalies.append(
            "A"
            f"{axis_index}:"
            f"AV={actual_velocity:.3f},"
            f"CV={command_velocity:.3f},"
            f"ERR={velocity_error:.3f},"
            f"JUMP={velocity_jump:.3f},"
            f"AP={master.slaves[axis_index].txpdo.actual_position},"
            f"SP={master.slaves[axis_index].txpdo.setpoint_position},"
            f"CP={generator.command_position:.3f},"
            f"TP={generator.target_position:.3f}"
        )
        anomaly_axes.append(axis_index)

    if anomalies:
        print(
            "Velocity anomaly: "
            f"{' | '.join(anomalies)} "
            f"trajectory_state={state.get('trajectory', {}).get('state')} "
            f"trajectory_time={state.get('trajectory', {}).get('time_from_start', 0.0):.3f} "
            f"dc_phase_avg_ms={latest_dc_phase_ms} "
            f"{format_position_feedback_lag(master, state, anomaly_axes)} "
            f"{velocity_anomaly_dc_snapshot(master, state, cycle_stats)} "
            f"{format_tx_history_for_axes(state, anomaly_axes)}",
            flush=True,
        )
        state["velocity_anomaly_last_log_time"] = now


def log_csp_command_step_anomalies(master, state):
    if not CSP_COMMAND_STEP_LOGS:
        return

    trajectory = state.get("trajectory", {})
    scale = max(float(getattr(master, "csp_counts_per_unit", 1.0)), 1e-9)
    events = getattr(master, "last_csp_command_steps", [])
    for event in events:
        axis_index = int(event["axis"])
        generator = master.trajectory_generators[axis_index]
        timed_start = None
        timed_end = None
        if generator.timed_points:
            timed_start = generator.timed_points[0]
            timed_end = generator.timed_points[-1]
        actual_position = master.slaves[axis_index].txpdo.actual_position
        print(
            "CSP command step anomaly: "
            f"axis={axis_index} "
            f"previous_sent_position={event['previous_sent_position']} "
            f"sent_position={event['sent_position']} "
            f"sent_step={event['sent_step']} "
            f"expected_step={event['expected_step']:.3f} "
            f"step_error={event['step_error']:.3f} "
            f"previous_command_position={event['previous_command_position']:.3f} "
            f"command_position={event['command_position']:.3f} "
            f"command_step={event['command_step']:.3f} "
            f"command_velocity={event['command_velocity'] / scale:.3f} "
            f"actual_position={actual_position} "
            f"position_gap={event['command_position'] - actual_position:.3f} "
            f"target_position={generator.target_position:.3f} "
            f"timed_active={generator.timed_active} "
            f"timed_elapsed={generator.timed_elapsed:.6f} "
            f"timed_segment={generator.timed_segment} "
            f"timed_start={timed_start} "
            f"timed_end={timed_end} "
            f"trajectory_state={trajectory.get('state')} "
            f"trajectory_time={trajectory.get('time_from_start', 0.0):.3f}",
            flush=True,
        )

    output_events = getattr(master, "last_csp_output_steps", [])
    for event in output_events:
        axis_index = int(event["axis"])
        generator = master.trajectory_generators[axis_index]
        actual_position = master.slaves[axis_index].txpdo.actual_position
        print(
            "CSP output buffer step anomaly: "
            f"axis={axis_index} "
            f"previous_output_target={event['previous_output_target']} "
            f"output_target={event['output_target']} "
            f"output_step={event['output_step']} "
            f"rxpdo_target={event['rxpdo_target']} "
            f"expected_step={event['expected_step']:.3f} "
            f"step_error={event['step_error']:.3f} "
            f"command_position={event['command_position']:.3f} "
            f"command_velocity={event['command_velocity'] / scale:.3f} "
            f"actual_position={actual_position} "
            f"position_gap={event['command_position'] - actual_position:.3f} "
            f"target_position={generator.target_position:.3f} "
            f"timed_active={generator.timed_active} "
            f"timed_elapsed={generator.timed_elapsed:.6f} "
            f"timed_segment={generator.timed_segment} "
            f"trajectory_state={trajectory.get('state')} "
            f"trajectory_time={trajectory.get('time_from_start', 0.0):.3f}",
            flush=True,
        )


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
            f"SP={slave.txpdo.setpoint_position} "
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
        require_pdo_fields_for_mode(master, "pp", axis_index)
        target_position = target_positions[axis_index]
        slave = master.slaves[axis_index]
        slave.rxpdo.mode_of_operation = PROFILE_POSITION_MODE
        slave.rxpdo.target_position = int(target_position)
        slave.rxpdo.profile_velocity = int(slave.motion_limits.max_velocity)

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
        slave = master.slaves[axis_index]
        slave.rxpdo.mode_of_operation = CSP_MODE
        slave.rxpdo.controlword = 0x000F

    master.set_target_positions(target_positions)


def write_profile_motion_limits(master, axis_index):
    limits = master.slaves[axis_index].motion_limits
    DEVICE_PROFILE.write_profile_motion_limits(master, axis_index, limits)


def write_profile_jerk(master, axis_index, pp_jerk):
    value = max(0, int(pp_jerk))
    try:
        DEVICE_PROFILE.write_profile_jerk(master, axis_index, value)
        print(
            f"Axis {axis_index}: PP jerk set to {value}",
            flush=True,
        )
    except Exception as exc:
        print(
            f"Axis {axis_index}: failed to set PP jerk "
            f"to {value}; continuing ({exc})",
            flush=True,
        )


def read_software_position_limits(master, axis_index):
    return DEVICE_PROFILE.read_software_position_limits(master, axis_index)


def read_all_software_position_limits(master):
    limits = []
    for axis_index in range(axis_count(master)):
        try:
            limits.append(read_software_position_limits(master, axis_index))
        except Exception as exc:
            print(
                f"Axis {axis_index}: failed to read software position limits "
                f"({exc})",
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
    DEVICE_PROFILE.write_software_position_limits(
        master,
        axis_index,
        negative_limit,
        positive_limit,
    )


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


def dc_absolute_cycle_deadline(master, dc_phase_lock):
    now_monotonic_ns = time.monotonic_ns()
    dc_now_ns = master.estimate_dc_time_ns(now_monotonic_ns)
    phase_ns = int(dc_now_ns) % dc_phase_lock.cycle_time_ns
    wait_ns = dc_phase_lock.target_phase_ns() - phase_ns
    if wait_ns <= 0:
        wait_ns += dc_phase_lock.cycle_time_ns

    deadline = (now_monotonic_ns + wait_ns) / 1_000_000_000.0
    return deadline, wait_ns / 1_000_000_000.0


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
    dc_phase_lock_enabled = bool(state.get("dc_phase_lock", False))
    dc_absolute_shift = (
        dc_phase_lock_enabled
        and bool(state.get("dc_absolute_shift", False))
    )
    dc_phase_lock = DcPhaseLock(
        dc_phase_lock_enabled,
        master.cycle_time,
        state.get("dc_phase_offset_ns", 800000),
        state.get("dc_phase_kp", 0.05),
        state.get("dc_phase_ki", 0.0005),
        state.get("dc_phase_max_correction", 0.001),
    )

    while True:
        if dc_absolute_shift:
            hold_faulted_axes(master, state)
            update_active_trajectory(master, state)
            master.prepare_processdata()

            next_cycle_time, dc_schedule_wait = dc_absolute_cycle_deadline(
                master,
                dc_phase_lock,
            )
            cycle_stats.add("dc_schedule_wait", dc_schedule_wait)

        wait_until_cycle_time(next_cycle_time, spin_wait_time)

        cycle_start_time = time.monotonic()
        if last_cycle_start_time is not None:
            cycle_stats.add("loop", cycle_start_time - last_cycle_start_time)
        last_cycle_start_time = cycle_start_time
        deadline_late = cycle_start_time - next_cycle_time
        if deadline_late > 0.0:
            cycle_stats.add("deadline_late", deadline_late)

        if dc_absolute_shift:
            exchange_prepared(master, cycle_stats=cycle_stats)
        else:
            hold_faulted_axes(master, state)
            update_active_trajectory(master, state)
            exchange(master, cycle_stats=cycle_stats, sleep_after=False)

        direct_tx_dc_time_ns = getattr(master, "last_direct_tx_dc_time_ns", None)
        estimated_tx_dc_time_ns = getattr(master, "last_tx_dc_time_ns", None)
        if direct_tx_dc_time_ns is not None and estimated_tx_dc_time_ns is not None:
            cycle_stats.add(
                "dc_tx_estimation_delta",
                (estimated_tx_dc_time_ns - direct_tx_dc_time_ns) / 1_000_000_000.0,
            )
        tx_prepare_duration_ns = getattr(master, "last_tx_prepare_duration_ns", None)
        if tx_prepare_duration_ns is not None:
            cycle_stats.add("tx_prepare", tx_prepare_duration_ns / 1_000_000_000.0)
        send_call_duration_ns = getattr(master, "last_send_call_duration_ns", None)
        if send_call_duration_ns is not None:
            cycle_stats.add("send_call", send_call_duration_ns / 1_000_000_000.0)
        dc_phase_lock.update(getattr(master, "last_tx_dc_time_ns", None), cycle_stats)
        record_tx_history(master, state, cycle_stats)
        update_homing_state(master, state)
        log_csp_command_step_anomalies(master, state)
        log_position_feedback_lag(master, state)
        log_velocity_anomalies(master, state, cycle_stats)

        if not dc_absolute_shift:
            next_cycle_time += master.cycle_time + dc_phase_lock.correction()
            if cycle_start_time - next_cycle_time > master.cycle_time:
                next_cycle_time = cycle_start_time + master.cycle_time

        now = time.monotonic()
        if clients and now - last_feedback_update_time >= FEEDBACK_PERIOD:
            update_derived_velocities(master, state, now)
            last_feedback_update_time = now

        if (
            CYCLE_STATS_LOGS
            and CYCLE_STATS_PERIOD > 0.0
            and now - last_cycle_stats_log_time >= CYCLE_STATS_PERIOD
        ):
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


def run_degraded_server_loop(server, master, state):
    server.setblocking(False)
    clients = []
    next_client_id = 1
    last_status_log_time = time.monotonic()

    print(
        "Axis server is running in initialization-error state: "
        f"{state.get('initialization_error', '')}",
        flush=True,
    )

    while True:
        readable, _, _ = select.select([server], [], [], 0.05)
        if server in readable:
            conn, addr = server.accept()
            conn.setblocking(False)
            client = {
                "id": next_client_id,
                "conn": conn,
                "addr": addr,
                "buffer": "",
                "last_feedback_time": 0.0,
                "last_message_force": False,
            }
            clients.append(client)
            next_client_id += 1
            print(f"Client connected: id={client['id']} addr={addr}", flush=True)

        for client in list(clients):
            try:
                if not service_client(client, master, state):
                    close_client(client, state)
                    clients.remove(client)
                    continue
                send_feedback_if_due(client, master, state)
            except (ConnectionError, OSError, json.JSONDecodeError) as exc:
                print(
                    f"Client error: id={client['id']} error={exc}",
                    flush=True,
                )
                close_client(client, state)
                clients.remove(client)

        last_status_log_time = log_status_if_due(
            master,
            state,
            last_status_log_time,
        )


def default_diagnostics(axis_count_value, error_message=""):
    text = error_message or "not initialized"
    return [
        {
            "statusword": 0,
            "error_code": 0,
            "error_code_text": text,
            "mode_display": 0,
        }
        for _ in range(axis_count_value)
    ]


def initial_server_state(
    args,
    positions,
    software_position_limits,
    initialized=True,
    initialization_error="",
):
    return {
        "drive_initialized": bool(initialized),
        "initialization_error": initialization_error,
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
        "trajectory_sequence": 0,
        "last_trajectory_complete_time": None,
        "tx_history": deque(maxlen=max(1, TX_HISTORY_LENGTH)),
        "homing": inactive_homing_state(),
        "command_authority_owner": None,
        "spin_wait_time": max(0.0, args.spin_wait_time),
        "dc_phase_lock": args.dc_phase_lock,
        "dc_absolute_shift": args.dc_absolute_shift,
        "dc_phase_offset_ns": args.dc_phase_offset,
        "dc_phase_kp": args.dc_phase_kp,
        "dc_phase_ki": args.dc_phase_ki,
        "dc_phase_max_correction": args.dc_phase_max_correction,
    }


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
        drive_initialized = False
        try:
            initialize_drive(
                master,
                args.motion_mode,
                args.pp_jerk,
                args.csp_interpolation_mode,
            )
            drive_initialized = True
        except Exception as exc:
            initialization_error = str(exc)
            print(
                "Drive initialization failed; keeping Axis Server online: "
                f"{initialization_error}",
                flush=True,
            )
            master.close()
            master.last_diagnostics = default_diagnostics(
                args.axis_count,
                initialization_error,
            )
            software_position_limits = [
                [0.0, 0.0]
                for _ in range(args.axis_count)
            ]
            positions = [0.0 for _ in range(args.axis_count)]
            state = initial_server_state(
                args,
                positions,
                software_position_limits,
                initialized=False,
                initialization_error=initialization_error,
            )
        else:
            for slave in master.slaves:
                if slave.rxpdo.has_field("profile_velocity"):
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
                f"dc_phase_lock={args.dc_phase_lock} "
                f"dc_absolute_shift={args.dc_absolute_shift} "
                f"dc_phase_offset_ns={args.dc_phase_offset} "
                f"dc_phase_kp={args.dc_phase_kp} "
                f"dc_phase_ki={args.dc_phase_ki} "
                f"txpdo_setpoint_entry={args.txpdo_setpoint_entry} "
                f"csp_interpolation_mode={args.csp_interpolation_mode} "
                f"csp_velocity_offset={args.csp_velocity_offset} "
                f"derived_velocity_alpha={args.derived_velocity_alpha} "
                f"statuswords={[f'0x{slave.txpdo.statusword:04X}' for slave in master.slaves]} "
                f"software_position_limits={software_position_limits} "
                f"AP={positions}",
                flush=True,
            )
            state = initial_server_state(
                args,
                positions,
                software_position_limits,
                initialized=True,
            )

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((args.host, args.port))
            server.listen(1)
            print(
                f"Axis server listening on {args.host}:{args.port} "
                f"backend={args.backend} axes={args.axis_count}",
                flush=True,
            )
            if drive_initialized:
                run_server_loop(server, master, state)
            else:
                run_degraded_server_loop(server, master, state)

    finally:
        master.close()


if __name__ == "__main__":
    main()
