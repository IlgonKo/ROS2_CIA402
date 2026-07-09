from collections import deque
import json
import os
from pathlib import Path
import select
import socket
import sys
import time

PROJECT_ROOT = Path(
    os.environ.get("AXIS_SERVER_PROJECT_ROOT", Path(__file__).resolve().parents[1])
).resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from axis_server.config import (
    AXIS_SERVER_COMMAND_LOGS,
    CSP_MODE,
    CYCLE_STATS_LOGS,
    CYCLE_STATS_PERIOD,
    DEVICE_PROFILE,
    FEEDBACK_PERIOD,
    HOMING_ERROR_MASK,
    HOMING_MIN_MONITOR_TIME,
    HOMING_MODE,
    HOMING_REFERENCED_MASK,
    HOMING_START_BIT,
    JOG_MODE,
    MOTION_MODES,
    PP_BASE_CONTROLWORD,
    PP_HANDSHAKE_MAX_CYCLES,
    PP_NEW_SETPOINT_CONTROLWORD,
    PP_SETPOINT_ACK_MASK,
    PROFILE_POSITION_MODE,
    PROFILE_VELOCITY_MODE,
    TX_HISTORY_LENGTH,
    parse_args,
    require_pdo_fields_for_mode,
    require_txpdo_fields,
)
from axis_server.diagnostics import (
    log_csp_command_step_anomalies,
    log_position_feedback_lag,
    log_status_if_due,
    log_trajectory_debug,
    log_trajectory_snapshot,
    log_velocity_anomalies,
    record_tx_history,
)
from axis_server.trajectory_commands import handle_trajectory_command
from device import get_device_profile
from device.cmmt.virtual_servo import VirtualCiA402Servo
from ethercat.distributed_clock import (
    DcPhaseLock,
    absolute_cycle_deadline as dc_absolute_cycle_deadline,
)
from ethercat.mock_master import MockMaster
from ethercat.mock_slave import MockSlave
from ethercat.pysoem_master import PySOEMMaster
from motion.axis import Axis

INT32_MIN = -(2 ** 31)
INT32_MAX = 2 ** 31 - 1
UINT32_MAX = 2 ** 32 - 1

# Public command sets


COMMAND_MESSAGE_TYPES = {
    "system/stop",
    "system/reset",
    "axis/enable",
    "axis/disable",
    "axis/reset",
    "axis/home",
    "axis/stop",
    "axis/move_abs",
    "axis/move_rel",
    "axis/move_vel",
    "axis/jog_start",
    "axis/jog_stop",
    "axis/profile",
    "axis/motion_limits",
    "axis/software_position_limits",
    "axis/mode",
    "axis/param_write",
    "axis/param_save",
    "debug/controlword",
    "trajectory/move",
    "trajectory/stop",
}

AUTHORITY_MESSAGE_TYPES = {
    "authority/acquire",
    "authority/release",
    "authority/status",
}

ADVANCED_MESSAGE_TYPES = {
    "debug/controlword",
    "trajectory/move",
    "trajectory/stop",
}

ADVANCED_STATUS_MESSAGE_TYPES = {
    "trajectory/status",
}

STATUS_MESSAGE_TYPES = {
    "system/status",
    "axis/status",
    "trajectory/status",
}

# Master Startup


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
            csp_counts_per_unit=args.csp_counts_per_unit,
            csp_velocity_offset_enabled=args.csp_velocity_offset,
            csp_command_step_threshold=args.csp_command_step_threshold,
            csp_command_step_error_threshold=(
                args.csp_command_step_error_threshold
            ),
            csp_profile=args.csp_profile,
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
        csp_profile=args.csp_profile,
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

# Cycle I/O


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

# Drive State And Mode

def read_drive_diagnostics(master, axis_index):
    return DEVICE_PROFILE.read_diagnostics(master, axis_index)


def read_all_diagnostics(master):
    return [
        read_drive_diagnostics(master, axis_index)
        for axis_index in range(axis_count(master))
    ]


def diagnostics_summary(master, axis_indices):
    summaries = []
    for axis_index in axis_indices:
        try:
            diagnostics = read_drive_diagnostics(master, axis_index)
        except Exception as exc:
            summaries.append(f"axis {axis_index}: diagnostics read failed: {exc}")
            continue
        statusword = diagnostics.get("statusword")
        error_code = diagnostics.get("error_code")
        status_text = (
            f"0x{statusword:04X}" if isinstance(statusword, int) else str(statusword)
        )
        error_text = (
            f"0x{error_code:08X}" if isinstance(error_code, int) else str(error_code)
        )
        summaries.append(
            f"axis {axis_index}: statusword={status_text} "
            f"error_code={error_text} "
            f"mode_display={diagnostics.get('mode_display')} "
            f"error={diagnostics.get('error_code_text')}"
        )
    return summaries


PV_USER_POSITION_UNITS = {
    0x1000: "rad",
    0x4100: "deg",
    0xB400: "rev",
}


LINEAR_USER_POSITION_UNITS = {
    0x0100: "m",
}


def user_position_unit_name(user_position_unit):
    if user_position_unit is None:
        return "unknown"
    unit = int(user_position_unit)
    return (
        PV_USER_POSITION_UNITS.get(unit)
        or LINEAR_USER_POSITION_UNITS.get(unit)
        or f"0x{unit:04X}"
    )


def axis_motion_kind(user_position_unit):
    if user_position_unit is None:
        return "unknown"
    unit = int(user_position_unit)
    if unit in PV_USER_POSITION_UNITS:
        return "rotary"
    if unit in LINEAR_USER_POSITION_UNITS:
        return "linear"
    return "unknown"


def api_position_unit_name(user_position_unit):
    motion_kind = axis_motion_kind(user_position_unit)
    if motion_kind == "rotary":
        return "deg"
    if motion_kind == "linear":
        return "mm"
    return user_position_unit_name(user_position_unit)


def api_to_user_unit_factor(user_position_unit):
    if user_position_unit is None:
        return 1.0
    unit = int(user_position_unit)
    if unit in LINEAR_USER_POSITION_UNITS:
        return 0.001
    if unit == 0x1000:
        return 3.141592653589793 / 180.0
    if unit == 0x4100:
        return 1.0
    if unit == 0xB400:
        return 1.0 / 360.0
    return 1.0


def scale_from_exponent(exponent, default=1.0):
    if exponent is None:
        return default
    exponent_value = int(exponent)
    if exponent_value > 0:
        return 10.0 ** (-exponent_value)
    return 10.0 ** exponent_value


def build_axis_metadata(user_position_units, converting_unit_exponents):
    metadata = []
    axis_total = max(len(user_position_units), len(converting_unit_exponents))
    for axis_index in range(axis_total):
        user_position_unit = (
            user_position_units[axis_index]
            if axis_index < len(user_position_units)
            else None
        )
        exponents = (
            converting_unit_exponents[axis_index]
            if axis_index < len(converting_unit_exponents)
            else None
        )
        if exponents is None:
            exponents = [None, None, None, None]
        motion_kind = axis_motion_kind(user_position_unit)
        user_unit_name = user_position_unit_name(user_position_unit)
        position_unit = api_position_unit_name(user_position_unit)
        acceleration_scale = scale_from_exponent(exponents[2], 1.0)
        metadata.append({
            "axis": axis_index,
            "user_position_unit": user_position_unit,
            "user_position_unit_name": user_unit_name,
            "motion_kind": motion_kind,
            "pv_allowed": (
                pv_allowed_user_position_unit(user_position_unit)
                if user_position_unit is not None
                else False
            ),
            "converting_unit_exponents": exponents,
            "position_unit": position_unit,
            "velocity_unit": f"{position_unit}/s",
            "acceleration_unit": f"{position_unit}/s^2",
            "deceleration_unit": f"{position_unit}/s^2",
            "jerk_unit": f"{position_unit}/s^3",
            "position_scale": scale_from_exponent(exponents[0], 1.0),
            "velocity_scale": scale_from_exponent(exponents[1], 1.0),
            "acceleration_scale": acceleration_scale,
            "deceleration_scale": acceleration_scale,
            "jerk_scale": scale_from_exponent(exponents[3], 1.0),
        })
    return metadata


def default_axis_metadata(axis_count):
    return build_axis_metadata(
        [None for _ in range(axis_count)],
        [None for _ in range(axis_count)],
    )


def axis_metadata(state, axis_index):
    metadata = state.get("axis_metadata", [])
    if axis_index < len(metadata) and isinstance(metadata[axis_index], dict):
        return metadata[axis_index]
    return {}


def axis_position_counts_per_api_unit(state, axis_index):
    metadata = axis_metadata(state, axis_index)
    if metadata.get("motion_kind") in ("linear", "rotary"):
        position_scale = max(float(metadata.get("position_scale", 1.0)), 1e-12)
        return api_to_user_unit_factor(metadata.get("user_position_unit")) / position_scale
    return max(float(state.get("position_counts_per_unit", 1.0)), 1e-9)


def axis_position_counts_per_api_units(state, axis_count_value):
    return [
        axis_position_counts_per_api_unit(state, axis_index)
        for axis_index in range(axis_count_value)
    ]


def axis_position_drive_to_api(state, axis_index, value):
    return float(value) / axis_position_counts_per_api_unit(state, axis_index)


def axis_position_api_to_drive(state, axis_index, value):
    return float(value) * axis_position_counts_per_api_unit(state, axis_index)


def axis_motion_scale(state, axis_index, kind="velocity"):
    metadata = axis_metadata(state, axis_index)
    key = {
        "velocity": "velocity_scale",
        "acceleration": "acceleration_scale",
        "deceleration": "deceleration_scale",
        "jerk": "jerk_scale",
    }.get(kind, "velocity_scale")
    try:
        return max(float(metadata.get(key, 1.0)), 1e-12)
    except (TypeError, ValueError):
        return 1.0


def axis_motion_drive_to_api(state, axis_index, value, kind="velocity"):
    metadata = axis_metadata(state, axis_index)
    factor = api_to_user_unit_factor(metadata.get("user_position_unit"))
    return float(value) * axis_motion_scale(state, axis_index, kind) / factor


def axis_motion_api_to_drive(state, axis_index, value, kind="velocity"):
    metadata = axis_metadata(state, axis_index)
    factor = api_to_user_unit_factor(metadata.get("user_position_unit"))
    return float(value) * factor / axis_motion_scale(state, axis_index, kind)


def require_int32_value(value, field_name):
    int_value = int(round(float(value)))
    if int_value < INT32_MIN or int_value > INT32_MAX:
        raise ValueError(
            f"{field_name}={int_value} is outside int32 PDO range "
            f"[{INT32_MIN}, {INT32_MAX}]"
        )
    return int_value


def require_uint32_value(value, field_name):
    int_value = int(round(float(value)))
    if int_value < 0 or int_value > UINT32_MAX:
        raise ValueError(
            f"{field_name}={int_value} is outside uint32 PDO range "
            f"[0, {UINT32_MAX}]"
        )
    return int_value


def profile_settings_drive_to_api(state, axis_index, values):
    kinds = ["velocity", "acceleration", "deceleration", "jerk"]
    return [
        axis_motion_drive_to_api(state, axis_index, value, kinds[index])
        for index, value in enumerate(values)
    ]


def motion_limits_drive_to_api(state, axis_index, values):
    kinds = ["velocity", "velocity", "acceleration", "deceleration"]
    return [
        axis_motion_drive_to_api(state, axis_index, value, kinds[index])
        for index, value in enumerate(values)
    ]


def trajectory_message_api_to_drive(message, state):
    axes = [
        int(axis)
        for axis in message.get("axes", [])
    ]
    if not axes:
        axes = list(range(len(state.get("target_positions", []))))

    converted = dict(message)
    points = []
    for point in message.get("points", []):
        converted_point = dict(point)
        converted_point["positions"] = [
            require_int32_value(
                axis_position_api_to_drive(state, axis_index, position),
                f"axis {axis_index} target_position",
            )
            for axis_index, position in zip(axes, point.get("positions", []))
        ]
        points.append(converted_point)
    converted["points"] = points
    return converted


def read_axis_user_position_units(master):
    units = []
    for axis_index in range(axis_count(master)):
        try:
            value = int(DEVICE_PROFILE.read_user_unit_position(master, axis_index))
        except Exception as exc:
            print(
                "Axis user position unit read failed: "
                f"axis={axis_index} object=0x216E:01 error={exc}",
                flush=True,
            )
            units.append(None)
            continue
        units.append(value)
        print(
            "Axis user position unit: "
            f"axis={axis_index} 0x216E:01=0x{value:04X} "
            f"unit={user_position_unit_name(value)}",
            flush=True,
        )
    return units


def read_axis_converting_unit_exponents(master):
    exponents = []
    for axis_index in range(axis_count(master)):
        try:
            values = DEVICE_PROFILE.read_converting_unit_exponents(master, axis_index)
        except Exception as exc:
            print(
                "Axis converting unit read failed: "
                f"axis={axis_index} object=0x2194:01-04 error={exc}",
                flush=True,
            )
            exponents.append(None)
            continue
        exponents.append(values)
        print(
            "Axis converting unit exponents: "
            f"axis={axis_index} "
            f"position={values[0]} velocity={values[1]} "
            f"acceleration={values[2]} jerk={values[3]}",
            flush=True,
        )
    return exponents


def pv_allowed_axis(state, axis_index):
    units = state.get("user_position_units", [])
    if axis_index >= len(units):
        return False
    user_position_unit = units[axis_index]
    if user_position_unit is None:
        return False
    return pv_allowed_user_position_unit(user_position_unit)


def pv_allowed_user_position_unit(user_position_unit):
    return int(user_position_unit) in PV_USER_POSITION_UNITS


def pv_reject_message(state, axis_indices):
    details = []
    for axis_index in axis_indices:
        units = state.get("user_position_units", [])
        user_position_unit = units[axis_index] if axis_index < len(units) else None
        if user_position_unit is None:
            details.append(f"axis {axis_index}: 0x216E:01 unread")
        else:
            details.append(
                f"axis {axis_index}: 0x216E:01=0x{int(user_position_unit):04X} "
                f"unit={user_position_unit_name(user_position_unit)}"
            )
    return (
        "PV mode is allowed only for rotary user position units "
        "(rad, degree, or revolution). "
        + "; ".join(details)
    )


def reject_if_pv_not_allowed(state, axis_indices, client, command):
    blocked_axes = [
        axis_index
        for axis_index in axis_indices
        if not pv_allowed_axis(state, axis_index)
    ]
    if not blocked_axes:
        return False

    message = pv_reject_message(state, blocked_axes)
    reject_command_message(client, command, message)
    print(f"Ignored {command}: {message}", flush=True)
    return True


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


def initialize_drive(master, motion_mode, csp_interpolation_mode):
    master.connect()
    require_txpdo_fields(master)
    write_csp_interpolation_modes(master, csp_interpolation_mode)
    if motion_mode == "pv":
        user_position_units = read_axis_user_position_units(master)
        blocked_axes = [
            axis_index
            for axis_index, user_position_unit in enumerate(user_position_units)
            if user_position_unit is None
            or not pv_allowed_user_position_unit(user_position_unit)
        ]
        if blocked_axes:
            raise ValueError(
                pv_reject_message(
                    {"user_position_units": user_position_units},
                    blocked_axes,
                )
            )
    configure_motion_mode(master, motion_mode)

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

# Feedback Snapshots

def feedback_message(master, state, client_id=None):
    owner = state.get("command_authority_owner")
    return {
        "type": "feedback",
        "drive_initialized": bool(state.get("drive_initialized", True)),
        "initialization_error": state.get("initialization_error", ""),
        "target_positions": [
            axis_position_drive_to_api(state, axis_index, value)
            for axis_index, value in enumerate(state["target_positions"])
        ],
        "actual_positions": [
            axis_position_drive_to_api(state, axis_index, slave.txpdo.actual_position)
            for axis_index, slave in enumerate(master.slaves)
        ],
        "actual_velocities": [
            axis_motion_drive_to_api(state, axis_index, slave.txpdo.actual_velocity)
            for axis_index, slave in enumerate(master.slaves)
        ],
        "setpoint_positions": [
            axis_position_drive_to_api(state, axis_index, slave.txpdo.setpoint_position)
            for axis_index, slave in enumerate(master.slaves)
        ],
        "derived_velocities": [
            axis_motion_drive_to_api(state, axis_index, value)
            for axis_index, value in enumerate(state["derived_velocities"])
        ],
        "command_positions": [
            axis_position_drive_to_api(state, axis_index, generator.command_position)
            for axis_index, generator in enumerate(master.trajectory_generators)
        ],
        "command_velocities": [
            axis_motion_drive_to_api(state, axis_index, generator.command_velocity)
            for axis_index, generator in enumerate(master.trajectory_generators)
        ],
        "statuswords": [
            int(slave.txpdo.statusword)
            for slave in master.slaves
        ],
        "motion_limits": flatten_motion_limits(state["motion_limits"], state),
        "profile_settings": flatten_profile_settings(state["profile_settings"], state),
        "software_position_limits": flatten_software_position_limits(
            state["software_position_limits"],
            state,
        ),
        "axis_metadata": state.get("axis_metadata", []),
        "user_position_units": state.get("user_position_units", []),
        "converting_unit_exponents": state.get("converting_unit_exponents", []),
        "motion_mode": state["motion_mode"],
        "motion_modes": state["motion_modes"],
        "server_mode": state.get("server_mode", "basic"),
        "csp_counts_per_unit": master.csp_counts_per_unit,
        "position_counts_per_unit": state["position_counts_per_unit"],
        "axis_position_counts_per_unit": state.get(
            "axis_position_counts_per_unit",
            [],
        ),
        "capabilities": state["capabilities"],
        "trajectory": public_trajectory_state(state),
        "homing": public_homing_state(state),
        "diagnostics": master.last_diagnostics,
        "command_authority": {
            "owner": owner,
            "owned_by_this_client": owner is not None and owner == client_id,
            "available": owner is None,
        },
    }


def flatten_motion_limits(motion_limits, state=None):
    return [
        float(
            motion_limits_drive_to_api(state, axis_index, axis_limits)[field_index]
            if state is not None
            else value
        )
        for axis_index, axis_limits in enumerate(motion_limits)
        for field_index, value in enumerate(axis_limits)
    ]


def flatten_profile_settings(profile_settings, state=None):
    return [
        float(
            profile_settings_drive_to_api(state, axis_index, axis_settings)[field_index]
            if state is not None
            else value
        )
        for axis_index, axis_settings in enumerate(profile_settings)
        for field_index, value in enumerate(axis_settings)
    ]


def flatten_software_position_limits(software_position_limits, state=None):
    return [
        float(
            axis_position_drive_to_api(state, axis_index, value)
            if state is not None
            else value
        )
        for axis_index, axis_limits in enumerate(software_position_limits)
        for value in axis_limits
    ]


def public_trajectory_state(state):
    trajectory = dict(state.get("trajectory", {}))
    axes = trajectory.get("axes", [])
    points = []
    for point in trajectory.get("points", []) or []:
        converted_point = dict(point)
        converted_point["positions"] = [
            axis_position_drive_to_api(state, axis_index, position)
            for axis_index, position in zip(axes, point.get("positions", []))
        ]
        points.append(converted_point)
    trajectory["points"] = points
    return trajectory


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


def operation_enabled_axes(master, axes):
    return [
        axis_index
        for axis_index in axes
        if int(master.slaves[axis_index].txpdo.statusword) & 0x0004
    ]


def disabled_operation_axes(master, axes):
    enabled = set(operation_enabled_axes(master, axes))
    return [
        axis_index
        for axis_index in axes
        if axis_index not in enabled
    ]


def reject_if_any_axis_disabled(master, axes, client, command):
    disabled_axes = disabled_operation_axes(master, axes)
    if not disabled_axes:
        return False

    reject_command_message(
        client,
        command,
        "Axis operation is disabled. "
        f"disabled_axes={disabled_axes} "
        f"statuswords={[f'0x{master.slaves[index].txpdo.statusword:04X}' for index in disabled_axes]}",
    )
    return True

# Trajectory Runtime

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


def handle_trajectory_stop(message, master, state, client):
    command = public_command_name(message)
    mode = str(message.get("mode", "controlled")).strip().lower()
    if mode != "controlled":
        state["trajectory"] = inactive_trajectory_state("stop_rejected")
        state["trajectory"]["message"] = f"Unsupported stop mode: {mode}"
        print(f"Ignored unsupported trajectory/stop mode: {mode}", flush=True)
        return

    state["trajectory"] = inactive_trajectory_state("stopped")
    axes = list(range(axis_count(master)))
    if reject_if_any_axis_disabled(master, axes, client, command):
        state["trajectory"] = inactive_trajectory_state("stop_rejected")
        state["trajectory"]["message"] = "Axis operation is disabled."
        return

    ensure_csp_mode(master, state, axes)
    positions = actual_positions(master)
    state["target_positions"] = positions
    master.set_target_positions(positions)
    master.sync_trajectory_to_actual_positions()
    command_csp_positions(master, positions, axes)
    print(
        "Received trajectory/stop: "
        f"mode={mode} hold_positions={positions}",
        flush=True,
    )


def handle_trajectory_status(client, master, state):
    message = feedback_message(master, state, client["id"])
    message["type"] = "trajectory/status"
    send_client_message(client, message)

# Homing Runtime

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
        axis_indices = parse_axis_indices(message, master, "axis/home")
    except (TypeError, ValueError) as exc:
        state["homing"] = inactive_homing_state("rejected")
        state["homing"]["message"] = str(exc)
        send_homing_status(client, master, state)
        print(f"Ignored axis/home: {exc}", flush=True)
        return
    disabled_axes = disabled_operation_axes(master, axis_indices)
    if disabled_axes:
        message_text = (
            "Axis operation is disabled. "
            f"disabled_axes={disabled_axes}"
        )
        state["homing"] = inactive_homing_state("rejected")
        state["homing"]["message"] = message_text
        send_homing_status(client, master, state)
        print(f"Ignored axis/home: {message_text}", flush=True)
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
        "Received axis/home: "
        f"axes={axis_indices} "
        f"original_modes={original_modes} "
        f"initial_referenced={initial_referenced} "
        f"controlwords={[f'0x{master.slaves[index].rxpdo.controlword:04X}' for index in axis_indices]}",
        flush=True,
    )


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


SDO_READERS = {
    "uint8": "sdo_read_uint8",
    "int8": "sdo_read_int8",
    "uint16": "sdo_read_uint16",
    "int32": "sdo_read_int32",
    "uint32": "sdo_read_uint32",
    "udint": "sdo_read_uint32",
    "float32": "sdo_read_float32",
}

SDO_WRITERS = {
    "uint8": "sdo_write_uint8",
    "int8": "sdo_write_int8",
    "uint16": "sdo_write_uint16",
    "int32": "sdo_write_int32",
    "uint32": "sdo_write_uint32",
    "udint": "sdo_write_uint32",
    "float32": "sdo_write_float32",
}

# Parameter Commands

def sdo_response_type(message, default_type):
    return command_name(message) or default_type


def parse_sdo_request(message, master):
    data_type = str(message.get("data_type", "uint32")).strip().lower()
    axis_index = parse_int_field(message.get("axis", 0))
    index = parse_int_field(message.get("index"), 0)
    subindex = parse_int_field(message.get("subindex", 0))

    if axis_index < 0 or axis_index >= axis_count(master):
        raise ValueError(f"Invalid axis index: {axis_index}")
    return axis_index, index, subindex, data_type


def handle_sdo_read(message, master, client):
    response_type = sdo_response_type(message, "axis/param_read")
    try:
        axis_index, index, subindex, data_type = parse_sdo_request(message, master)
        reader_name = SDO_READERS.get(data_type)
        if reader_name is None:
            raise ValueError(f"Unsupported SDO data type: {data_type}")
        reader = getattr(master, reader_name)
        value = reader(axis_index, index, subindex)
    except (TypeError, ValueError) as exc:
        send_client_message(
            client,
            {
                "type": response_type,
                "ok": False,
                "axis": message.get("axis", 0),
                "index": message.get("index"),
                "subindex": message.get("subindex", 0),
                "data_type": str(message.get("data_type", "uint32")).strip().lower(),
                "error": str(exc),
            },
        )
        return
    except Exception as exc:
        send_client_message(
            client,
            {
                "type": response_type,
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
            "type": response_type,
            "ok": True,
            "axis": axis_index,
            "index": index,
            "subindex": subindex,
            "data_type": data_type,
            "value": float(value) if data_type == "float32" else int(value),
            "hex": (
                None
                if data_type == "float32"
                else f"0x{int(value) & 0xFFFFFFFF:08X}"
            ),
        },
    )


def handle_param_write(message, master, client):
    response_type = public_command_name(message)
    try:
        axis_index, index, subindex, data_type = parse_sdo_request(message, master)
        writer_name = SDO_WRITERS.get(data_type)
        if writer_name is None:
            raise ValueError(f"Unsupported SDO data type: {data_type}")
        if "value" not in message:
            raise ValueError("param_write requires value")
        value = float(message["value"]) if data_type == "float32" else int(
            str(message["value"]),
            0,
        )
        getattr(master, writer_name)(axis_index, index, subindex, value)
    except Exception as exc:
        send_client_message(
            client,
            {
                "type": response_type,
                "ok": False,
                "axis": message.get("axis", 0),
                "index": message.get("index"),
                "subindex": message.get("subindex", 0),
                "data_type": str(message.get("data_type", "uint32")).strip().lower(),
                "error": str(exc),
            },
        )
        return

    send_client_message(
        client,
        {
            "type": response_type,
            "ok": True,
            "axis": axis_index,
            "index": index,
            "subindex": subindex,
            "data_type": data_type,
            "value": value,
        },
    )


def handle_param_save(message, master, client):
    response_type = public_command_name(message)
    try:
        axis_index = selected_single_axis(message, master, response_type)
        result = DEVICE_PROFILE.save_parameters(master, axis_index)
    except Exception as exc:
        send_client_message(
            client,
            {
                "type": response_type,
                "ok": False,
                "axis": message.get("axis", message.get("axes", 0)),
                "error": str(exc),
            },
        )
        return

    send_client_message(
        client,
        {
            "type": response_type,
            "ok": True,
            "axis": axis_index,
            "result": result,
        },
    )

# Motion Command Helpers

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


def command_position_axes(master, state, axes, positions, command_name, client=None):
    faults = faulted_axes(master)
    if faults:
        hold_faulted_axes(master, state)
        master.sync_trajectory_to_actual_positions()
        print(
            f"Ignored {command_name} because at least one drive is faulted. "
            f"faulted_axes={faults} "
            f"statuswords={[f'0x{slave.txpdo.statusword:04X}' for slave in master.slaves]}",
            flush=True,
        )
        return

    disabled_axes = disabled_operation_axes(master, axes)
    if disabled_axes:
        message_text = (
            "Axis operation is disabled. "
            f"disabled_axes={disabled_axes} "
            f"statuswords={[f'0x{master.slaves[index].txpdo.statusword:04X}' for index in disabled_axes]}"
        )
        if client is not None:
            reject_command_message(client, command_name, message_text)
        print(f"Ignored {command_name}: {message_text}", flush=True)
        return

    target_positions = list(state["target_positions"])
    for axis_index in axes:
        target_positions[axis_index] = float(positions[axis_index])
    state["target_positions"] = target_positions

    pp_axes = [
        axis_index
        for axis_index in axes
        if state["motion_modes"][axis_index] == "pp"
    ]
    csp_axes = [
        axis_index
        for axis_index in axes
        if state["motion_modes"][axis_index] == "csp"
    ]
    non_position_axes = [
        axis_index
        for axis_index in axes
        if state["motion_modes"][axis_index] not in {"pp", "csp"}
    ]
    if non_position_axes:
        print(
            f"Ignored {command_name} for non-position axes. "
            f"axes={non_position_axes} "
            f"modes={[state['motion_modes'][axis] for axis in non_position_axes]}",
            flush=True,
        )
    try:
        if pp_axes:
            command_profile_positions(master, state["target_positions"], pp_axes)
        if csp_axes:
            command_csp_positions(master, state["target_positions"], csp_axes)
    except Exception as exc:
        actual = actual_positions(master)
        for axis_index in axes:
            state["target_positions"][axis_index] = actual[axis_index]
            hold_axis_at_actual_position(master, state, axis_index)
        master.set_target_positions(state["target_positions"])
        message_text = (
            f"{command_name} failed while sending position command: {exc}"
        )
        if client is not None:
            reject_command_message(client, command_name, message_text)
        print(
            f"Ignored {command_name}: {message_text} "
            f"axes={axes} statuswords="
            f"{[f'0x{master.slaves[index].txpdo.statusword:04X}' for index in axes]}",
            flush=True,
        )


def axis_velocities_from_message(message, master, state, command):
    axes = selected_axes(message, master, command)
    if "velocities" in message:
        values = [
            float(value)
            for value in message.get("velocities", [])
        ]
    elif "velocity" in message:
        values = [float(message.get("velocity"))]
    else:
        raise ValueError(f"{command} requires velocities or velocity")

    if len(values) != len(axes):
        raise ValueError(
            f"{command} value count must match selected axes. "
            f"axes={len(axes)} values={len(values)}"
        )
    return axes, [
        axis_motion_api_to_drive(state, axis_index, value)
        for axis_index, value in zip(axes, values)
    ]


def axis_positions_from_message(message, master, state, command):
    axes = selected_axes(message, master, command)
    if "positions" in message:
        values = [
            float(value)
            for value in message.get("positions", [])
        ]
    elif "position" in message:
        values = [float(message.get("position"))]
    else:
        raise ValueError(f"{command} requires positions or position")

    if len(values) == axis_count(master) and len(axes) == axis_count(master):
        return [
            require_int32_value(
                axis_position_api_to_drive(state, axis_index, value),
                f"axis {axis_index} target_position",
            )
            for axis_index, value in enumerate(values)
        ]
    if len(values) != len(axes):
        raise ValueError(
            f"{command} value count must match selected axes. "
            f"axes={len(axes)} values={len(values)}"
        )

    positions = list(state["target_positions"])
    for axis_index, value in zip(axes, values):
        positions[axis_index] = require_int32_value(
            axis_position_api_to_drive(state, axis_index, value),
            f"axis {axis_index} target_position",
        )
    return positions


def axis_distances_from_message(message, master, state, command):
    axes = selected_axes(message, master, command)
    if "distances" in message:
        values = [
            float(value)
            for value in message.get("distances", [])
        ]
    elif "distance" in message:
        values = [float(message.get("distance"))]
    else:
        raise ValueError(f"{command} requires distances or distance")

    if len(values) != len(axes):
        raise ValueError(
            f"{command} value count must match selected axes. "
            f"axes={len(axes)} values={len(values)}"
        )
    return axes, [
        require_int32_value(
            axis_position_api_to_drive(state, axis_index, value),
            f"axis {axis_index} target_distance",
        )
        for axis_index, value in zip(axes, values)
    ]


def handle_axis_move_abs(message, master, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, master, command)
        positions = axis_positions_from_message(message, master, state, command)
        apply_move_profile_velocity(message, master, state, axes)
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return
    command_position_axes(master, state, axes, positions, command, client)


def handle_axis_move_rel(message, master, state, client):
    command = public_command_name(message)
    try:
        axes, distances = axis_distances_from_message(message, master, state, command)
        apply_move_profile_velocity(message, master, state, axes)
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return

    positions = actual_positions(master)
    for axis_index, distance in zip(axes, distances):
        positions[axis_index] = require_int32_value(
            positions[axis_index] + distance,
            f"axis {axis_index} target_position",
        )
    command_position_axes(master, state, axes, positions, command, client)


def handle_axis_move_vel(message, master, state, client):
    command = public_command_name(message)
    try:
        axes, velocities = axis_velocities_from_message(message, master, state, command)
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return

    command_profile_velocities(master, state, axes, velocities, command, client)


def apply_move_profile_velocity(message, master, state, axes):
    if "profile_velocity" not in message and "profile_velocities" not in message:
        return

    if "profile_velocities" in message:
        values = [
            float(value)
            for value in message.get("profile_velocities", [])
        ]
        if len(values) != len(axes):
            raise ValueError(
                "profile_velocities count must match selected axes. "
                f"axes={len(axes)} values={len(values)}"
            )
    else:
        values = [float(message.get("profile_velocity")) for _axis in axes]

    for axis_index, profile_velocity in zip(axes, values):
        drive_profile_velocity = axis_motion_api_to_drive(
            state,
            axis_index,
            profile_velocity,
        )
        state["profile_settings"][axis_index][0] = drive_profile_velocity
        slave = master.slaves[axis_index]
        if slave.rxpdo.has_field("profile_velocity"):
            slave.rxpdo.profile_velocity = require_uint32_value(
                drive_profile_velocity,
                f"axis {axis_index} profile_velocity",
            )

# System And Axis Commands

def handle_system_stop(message, master, state):
    mode = str(message.get("mode", "controlled")).strip().lower()
    if mode != "controlled":
        print(f"Ignored unsupported system/stop mode: {mode}", flush=True)
        return

    if state.get("homing", {}).get("active"):
        finish_homing(master, state, "stopped", "Homing stopped by system/stop.")

    state["trajectory"] = inactive_trajectory_state("system_stop")
    positions = actual_positions(master)
    state["target_positions"] = positions
    master.set_target_positions(positions)
    master.sync_trajectory_to_actual_positions()
    enabled_axes = set(operation_enabled_axes(master, range(axis_count(master))))
    for axis_index, motion_mode in enumerate(state["motion_modes"]):
        if axis_index not in enabled_axes:
            continue
        if motion_mode == "pp":
            command_profile_positions(master, positions, [axis_index])
        elif motion_mode == "pv":
            command_profile_velocities(
                master,
                state,
                [axis_index],
                [0.0],
                "system/stop",
                None,
            )
        elif motion_mode == "csp":
            command_csp_positions(master, positions, [axis_index])

    print(
        "Received system/stop: "
        f"mode={mode} hold_positions={positions}",
        flush=True,
    )


def handle_axis_stop(message, master, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, master, command)
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return
    if reject_if_any_axis_disabled(master, axes, client, command):
        return

    if state.get("homing", {}).get("active"):
        finish_homing(master, state, "stopped", "Homing stopped by axis/stop.")

    state["trajectory"] = inactive_trajectory_state("axis_stop")
    positions = list(state["target_positions"])
    actual = actual_positions(master)
    for axis_index in axes:
        positions[axis_index] = actual[axis_index]
        hold_axis_at_actual_position(master, state, axis_index)

    state["target_positions"] = positions
    master.set_target_positions(positions)
    master.sync_trajectory_to_actual_positions()
    enabled_axes = set(operation_enabled_axes(master, axes))
    for axis_index in axes:
        if axis_index not in enabled_axes:
            continue
        motion_mode = state["motion_modes"][axis_index]
        if motion_mode == "pp":
            command_profile_positions(master, positions, [axis_index])
        elif motion_mode == "pv":
            command_profile_velocities(
                master,
                state,
                [axis_index],
                [0.0],
                "axis/stop",
                client,
            )
        elif motion_mode == "csp":
            command_csp_positions(master, positions, [axis_index])
        elif motion_mode == "jog":
            master.slaves[axis_index].rxpdo.controlword = 0x000F

def handle_axis_motion_limits(message, master, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, master, command)
        for axis_index in axes:
            current_limits = list(state["motion_limits"][axis_index])
            positive_velocity_limit = axis_motion_api_to_drive(
                state,
                axis_index,
                message.get(
                    "positive_velocity_limit",
                    message.get(
                        "max_profile_velocity_positive",
                        message.get(
                            "max_profile_velocity",
                            axis_motion_drive_to_api(
                                state,
                                axis_index,
                                current_limits[0],
                                "velocity",
                            ),
                        ),
                    ),
                )
            )
            negative_velocity_limit = axis_motion_api_to_drive(
                state,
                axis_index,
                message.get(
                    "negative_velocity_limit",
                    message.get(
                        "max_profile_velocity_negative",
                        axis_motion_drive_to_api(
                            state,
                            axis_index,
                            current_limits[1],
                            "velocity",
                        ),
                    ),
                )
            )
            max_acceleration = axis_motion_api_to_drive(
                state,
                axis_index,
                message.get(
                    "max_acceleration",
                    message.get(
                        "acceleration",
                        axis_motion_drive_to_api(
                            state,
                            axis_index,
                            current_limits[2],
                            "acceleration",
                        ),
                    ),
                ),
                "acceleration",
            )
            max_deceleration = axis_motion_api_to_drive(
                state,
                axis_index,
                message.get(
                    "max_deceleration",
                    message.get(
                        "deceleration",
                        axis_motion_drive_to_api(
                            state,
                            axis_index,
                            current_limits[3],
                            "deceleration",
                        ),
                    ),
                ),
                "deceleration",
            )
            update_axis_motion_limits(
                master,
                state,
                axis_index,
                positive_velocity_limit,
                negative_velocity_limit,
                max_acceleration,
                max_deceleration,
            )
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return

def update_axis_motion_limits(
    master,
    state,
    axis_index,
    positive_velocity_limit,
    negative_velocity_limit,
    acceleration,
    deceleration,
):
    state["motion_limits"][axis_index] = [
        positive_velocity_limit,
        negative_velocity_limit,
        acceleration,
        deceleration,
    ]
    api_axis_limits = motion_limits_drive_to_api(
        state,
        axis_index,
        state["motion_limits"][axis_index],
    )
    master.set_axis_motion_limits(
        axis_index,
        max(abs(api_axis_limits[0]), abs(api_axis_limits[1])),
        api_axis_limits[2],
        api_axis_limits[3],
        0.0,
    )
    master.slaves[axis_index].axis_server_motion_limits = list(
        state["motion_limits"][axis_index]
    )
    write_axis_motion_limits(master, axis_index, state["motion_limits"][axis_index])


def write_axis_motion_limits(master, axis_index, axis_limits):
    DEVICE_PROFILE.write_motion_limits(
        master,
        axis_index,
        axis_limits[0],
        axis_limits[1],
        axis_limits[2],
        axis_limits[3],
    )


def handle_axis_profile_settings(message, master, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, master, command)
        for axis_index in axes:
            current_settings = list(state["profile_settings"][axis_index])
            is_pv_axis = state["motion_modes"][axis_index] == "pv"
            profile_velocity = float(
                message.get(
                    "profile_velocity",
                    message.get(
                        "velocity",
                        axis_motion_drive_to_api(
                            state,
                            axis_index,
                            current_settings[0],
                            "velocity",
                        ),
                    ),
                )
            )
            if is_pv_axis:
                profile_velocity = axis_motion_drive_to_api(
                    state,
                    axis_index,
                    current_settings[0],
                    "velocity",
                )
            profile_acceleration = float(
                message.get(
                    "profile_acceleration",
                    message.get(
                        "acceleration",
                        axis_motion_drive_to_api(
                            state,
                            axis_index,
                            current_settings[1],
                            "acceleration",
                        ),
                    ),
                )
            )
            profile_deceleration = float(
                message.get(
                    "profile_deceleration",
                    message.get(
                        "deceleration",
                        axis_motion_drive_to_api(
                            state,
                            axis_index,
                            current_settings[2],
                            "deceleration",
                        ),
                    ),
                )
            )
            profile_jerk = None
            if (
                not is_pv_axis
                and ("profile_jerk" in message or "jerk" in message)
            ):
                profile_jerk = float(
                    message.get(
                        "profile_jerk",
                        message.get("jerk"),
                    )
                )
            update_axis_profile_settings(
                master,
                state,
                axis_index,
                axis_motion_api_to_drive(state, axis_index, profile_velocity),
                axis_motion_api_to_drive(
                    state,
                    axis_index,
                    profile_acceleration,
                    "acceleration",
                ),
                axis_motion_api_to_drive(
                    state,
                    axis_index,
                    profile_deceleration,
                    "deceleration",
                ),
                (
                    axis_motion_api_to_drive(state, axis_index, profile_jerk, "jerk")
                    if profile_jerk is not None
                    else None
                ),
            )
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return

    print(
        "Received axis/profile: "
        f"axes={axes} profile_settings={state['profile_settings']}",
        flush=True,
    )


def update_axis_profile_settings(
    master,
    state,
    axis_index,
    profile_velocity,
    profile_acceleration,
    profile_deceleration,
    profile_jerk=None,
):
    current_jerk = state["profile_settings"][axis_index][3]
    is_pv_axis = state["motion_modes"][axis_index] == "pv"
    state["profile_settings"][axis_index] = [
        profile_velocity,
        profile_acceleration,
        profile_deceleration,
        current_jerk if profile_jerk is None else profile_jerk,
    ]
    if not is_pv_axis and master.slaves[axis_index].rxpdo.has_field("profile_velocity"):
        master.slaves[axis_index].rxpdo.profile_velocity = require_uint32_value(
            profile_velocity,
            f"axis {axis_index} profile_velocity",
        )
    if is_pv_axis:
        master.sdo_write_uint32(
            axis_index,
            DEVICE_PROFILE.PROFILE_ACCELERATION_INDEX,
            0,
            max(0, int(profile_acceleration)),
        )
        master.sdo_write_uint32(
            axis_index,
            DEVICE_PROFILE.PROFILE_DECELERATION_INDEX,
            0,
            max(0, int(profile_deceleration)),
        )
    else:
        DEVICE_PROFILE.write_profile_settings(
            master,
            axis_index,
            profile_velocity,
            profile_acceleration,
            profile_deceleration,
        )
    if profile_jerk is not None:
        DEVICE_PROFILE.write_profile_jerk(master, axis_index, profile_jerk)


def handle_axis_software_position_limits(message, master, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, master, command)
        for axis_index in axes:
            current_limits = list(state["software_position_limits"][axis_index])
            negative_limit_api = float(
                message.get(
                    "negative_limit",
                    message.get(
                        "negative_software_position_limit",
                        axis_position_drive_to_api(
                            state,
                            axis_index,
                            current_limits[0],
                        ),
                    ),
                )
            )
            positive_limit_api = float(
                message.get(
                    "positive_limit",
                    message.get(
                        "positive_software_position_limit",
                        axis_position_drive_to_api(
                            state,
                            axis_index,
                            current_limits[1],
                        ),
                    ),
                )
            )
            negative_limit = int(round(axis_position_api_to_drive(
                state,
                axis_index,
                negative_limit_api,
            )))
            positive_limit = int(round(axis_position_api_to_drive(
                state,
                axis_index,
                positive_limit_api,
            )))
            if negative_limit > positive_limit:
                raise ValueError(
                    "negative software position limit is greater than "
                    f"positive limit. axis={axis_index} "
                    f"negative={negative_limit} positive={positive_limit}"
                )
            DEVICE_PROFILE.write_software_position_limits(
                master,
                axis_index,
                negative_limit,
                positive_limit,
            )
            try:
                readback_limits = DEVICE_PROFILE.read_software_position_limits(
                    master,
                    axis_index,
                )
            except Exception as exc:
                readback_limits = [f"read failed: {exc}", f"read failed: {exc}"]
            state["software_position_limits"][axis_index] = [
                negative_limit,
                positive_limit,
            ]
            print(
                "Axis software position limits write: "
                f"axis={axis_index} "
                f"api=({negative_limit_api}, {positive_limit_api}) "
                f"drive=({negative_limit}, {positive_limit}) "
                f"readback={readback_limits} "
                f"metadata={axis_metadata(state, axis_index)}",
                flush=True,
            )
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return

    print(
        "Received axis/software_position_limits: "
        f"axes={axes} limits={state['software_position_limits']}",
        flush=True,
    )


def reject_command(client, command, message):
    if client is None:
        return
    send_client_message(
        client,
        {
            "type": "command_rejected",
            "command": command,
            "message": message,
        },
    )


def handle_motion_mode(message, master, state, client=None):
    command = public_command_name(message)
    requested_mode = str(message.get("mode", "")).strip().lower()
    if requested_mode not in MOTION_MODES:
        error_message = f"Ignored invalid motion mode: {requested_mode}"
        print(error_message, flush=True)
        reject_command(client, command, error_message)
        return

    axis_value = message.get("axis", None)
    if axis_value is None:
        axis_indices = list(range(axis_count(master)))
    else:
        try:
            axis_index = int(axis_value)
        except (TypeError, ValueError):
            error_message = f"Ignored motion mode for invalid axis: {axis_value}"
            print(error_message, flush=True)
            reject_command(client, command, error_message)
            return
        if axis_index < 0 or axis_index >= axis_count(master):
            error_message = f"Ignored motion mode for invalid axis: {axis_index}"
            print(error_message, flush=True)
            reject_command(client, command, error_message)
            return
        axis_indices = [axis_index]

    if all(state["motion_modes"][axis_index] == requested_mode for axis_index in axis_indices):
        return

    if requested_mode == "pv" and reject_if_pv_not_allowed(
        state,
        axis_indices,
        client,
        command,
    ):
        return

    try:
        for axis_index in axis_indices:
            require_pdo_fields_for_mode(master, requested_mode, axis_index)
    except Exception as exc:
        error_message = (
            f"Ignored motion mode {requested_mode.upper()}: {exc}"
        )
        print(error_message, flush=True)
        reject_command(client, command, error_message)
        return

    for axis_index in axis_indices:
        hold_axis_at_actual_position(master, state, axis_index)
    master.set_target_positions(state["target_positions"])

    changed_axes = []
    failed = []
    for axis_index in axis_indices:
        previous_mode = state["motion_modes"][axis_index]
        try:
            configure_motion_mode(master, requested_mode, axis_index)
        except Exception as exc:
            failed.append((axis_index, exc))
            previous_code = mode_code(previous_mode)
            master.slaves[axis_index].rxpdo.mode_of_operation = previous_code
            print(
                "Motion mode change failed "
                f"axis={axis_index} requested={requested_mode.upper()} "
                f"previous={previous_mode.upper()} error={exc}",
                flush=True,
            )
            continue

        state["motion_modes"][axis_index] = requested_mode
        changed_axes.append(axis_index)

    if failed:
        message_text = "; ".join(
            f"axis {axis_index}: {exc}"
            for axis_index, exc in failed
        )
        reject_command(
            client,
            command,
            f"Motion mode change failed: {message_text}",
        )

    update_motion_mode_summary(state)
    if changed_axes:
        print(
            f"Motion mode changed axes={changed_axes} "
            f"to {requested_mode.upper()} modes={state['motion_modes']}",
            flush=True,
        )


def handle_fault_reset(master, state, axis_indices=None):
    print(
        "Received fault reset: pulsing fault reset bit, then switching on",
        flush=True,
    )
    if axis_indices is None:
        axis_indices = list(range(axis_count(master)))
    original_controlwords = [
        int(master.slaves[axis_index].rxpdo.controlword)
        for axis_index in axis_indices
    ]

    for axis_index, controlword in zip(axis_indices, original_controlwords):
        slave = master.slaves[axis_index]
        slave.rxpdo.controlword = controlword & ~0x0080
    exchange(master, cycles=2)

    for axis_index, controlword in zip(axis_indices, original_controlwords):
        slave = master.slaves[axis_index]
        slave.rxpdo.controlword = controlword | 0x0080
    exchange(master, cycles=2)

    for axis_index, controlword in zip(axis_indices, original_controlwords):
        slave = master.slaves[axis_index]
        slave.rxpdo.controlword = controlword & ~0x0080
    exchange(master, cycles=2)

    for axis_index in axis_indices:
        master.slaves[axis_index].rxpdo.controlword = 0x0006
    exchange(master, cycles=5)

    for axis_index in axis_indices:
        master.slaves[axis_index].rxpdo.controlword = 0x0007
    exchange(master, cycles=5)

    print(
        "Fault reset complete. "
        f"axes={axis_indices} "
        f"statuswords={[f'0x{master.slaves[index].txpdo.statusword:04X}' for index in axis_indices]} "
        f"controlwords={[f'0x{master.slaves[index].rxpdo.controlword:04X}' for index in axis_indices]}",
        flush=True,
    )


def handle_axis_reset(message, master, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, master, command)
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return
    handle_fault_reset(master, state, axes)


def handle_axis_enable(message, master, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, master, command)
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return
    for axis_index in axes:
        master.slaves[axis_index].rxpdo.controlword = 0x000F
    exchange(master, cycles=3)
    print(
        "Received axis/enable: "
        f"axes={axes} "
        f"statuswords={[f'0x{master.slaves[index].txpdo.statusword:04X}' for index in axes]}",
        flush=True,
    )
    send_client_message(client, feedback_message(master, state, client["id"]))


def handle_axis_disable(message, master, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, master, command)
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return

    trajectory = state.get("trajectory", {})
    if trajectory.get("active") and set(axes) & set(trajectory.get("axes", [])):
        state["trajectory"] = inactive_trajectory_state("axis_disable")

    homing = state.get("homing", {})
    if homing.get("active") and set(axes) & set(homing.get("axes", [])):
        finish_homing(master, state, "stopped", "Homing stopped by axis/disable.")

    for axis_index in axes:
        hold_axis_at_actual_position(master, state, axis_index)
        master.slaves[axis_index].rxpdo.controlword = 0x0007
    master.set_target_positions(state["target_positions"])
    exchange(master, cycles=3)
    print(
        "Received axis/disable: "
        f"axes={axes} "
        f"statuswords={[f'0x{master.slaves[index].txpdo.statusword:04X}' for index in axes]}",
        flush=True,
    )
    send_client_message(client, feedback_message(master, state, client["id"]))


def handle_axis_jog_start(message, master, state, client):
    command = public_command_name(message)
    try:
        axis_index = selected_single_axis(message, master, command)
        direction = str(message.get("direction", "")).strip().lower()
        speed = str(message.get("speed", "slow")).strip().lower()
        if direction not in {"positive", "negative", "+", "-"}:
            raise ValueError(
                f"{command} requires direction positive or negative"
            )
        if speed not in {"slow", "fast", "two_phase"}:
            raise ValueError(
                f"{command} speed must be slow, fast, or two_phase"
            )
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return
    if reject_if_any_axis_disabled(master, [axis_index], client, command):
        return

    try:
        require_pdo_fields_for_mode(master, "jog", axis_index)
        if state["motion_modes"][axis_index] != "jog":
            state["jog_previous_modes"][axis_index] = state["motion_modes"][axis_index]
            hold_axis_at_actual_position(master, state, axis_index)
            configure_motion_mode(master, "jog", axis_index)
            state["motion_modes"][axis_index] = "jog"
            update_motion_mode_summary(state)
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return

    slave = master.slaves[axis_index]
    slave.rxpdo.mode_of_operation = JOG_MODE
    controlword = 0x000F
    if direction in {"positive", "+"}:
        controlword |= 1 << 4
        public_direction = "positive"
    else:
        controlword |= 1 << 5
        public_direction = "negative"
    if speed == "slow":
        controlword |= 1 << 11
    elif speed == "fast":
        controlword |= 1 << 12
    slave.rxpdo.controlword = controlword
    print(
        "Received axis/jog_start: "
        f"axis={axis_index} direction={public_direction} speed={speed} "
        f"controlword=0x{controlword:04X}",
        flush=True,
    )


def handle_axis_jog_stop(message, master, state, client):
    command = public_command_name(message)
    try:
        axis_index = selected_single_axis(message, master, command)
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return

    slave = master.slaves[axis_index]
    if disabled_operation_axes(master, [axis_index]):
        slave.rxpdo.controlword = 0x0007
    else:
        slave.rxpdo.controlword = 0x000F
    exchange(master, cycles=5)

    previous_mode = state["jog_previous_modes"][axis_index] or "pp"
    try:
        hold_axis_at_actual_position(master, state, axis_index)
        configure_motion_mode(master, previous_mode, axis_index)
        state["motion_modes"][axis_index] = previous_mode
        update_motion_mode_summary(state)
    except Exception as exc:
        reject_command_message(
            client,
            command,
            f"Jog stopped, but failed to restore {previous_mode.upper()}: {exc}",
        )
        return
    finally:
        state["jog_previous_modes"][axis_index] = None

    print(
        "Received axis/jog_stop: "
        f"axis={axis_index} restored_mode={previous_mode.upper()}",
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

# Command Dispatch And TCP Clients

def is_advanced_mode(state):
    return state.get("server_mode") == "advanced"


def reject_advanced_only_command(client, message, state):
    command = command_name(message)
    send_client_message(
        client,
        {
            "type": "command_rejected",
            "command": command,
            "server_mode": state.get("server_mode"),
            "message": (
                f"{command} is available only in "
                "Axis Server advanced mode."
            ),
        },
    )


def command_name(message):
    return str(message.get("cmd", message.get("type", ""))).strip()


def public_command_name(message):
    return command_name(message)


def reject_command_message(client, command, message):
    send_client_message(
        client,
        {
            "type": "command_rejected",
            "command": command,
            "message": message,
        },
    )


def selected_axes(message, master, command):
    return parse_axis_indices(message, master, command)


def selected_single_axis(message, master, command):
    axes = selected_axes(message, master, command)
    if len(axes) != 1:
        raise ValueError(f"{command} requires exactly one axis")
    return axes[0]


def authority_status_payload(client, state, message_type="authority/status"):
    owner = state.get("command_authority_owner")
    owned_by_this_client = owner is not None and owner == client["id"]
    return {
        "type": message_type,
        "ok": True,
        "owner": owner,
        "owned_by_this_client": owned_by_this_client,
        "available": owner is None,
        "reason": None,
    }


def handle_authority_acquire(client, state):
    owner = state.get("command_authority_owner")
    if owner is None or owner == client["id"]:
        state["command_authority_owner"] = client["id"]
        payload = authority_status_payload(client, state, "authority/acquire")
        payload["granted"] = True
        payload["message"] = (
            "Command authority granted."
            if owner is None
            else "This connection already owns command authority."
        )
        send_client_message(client, payload)
        print(f"Command authority granted to client {client['id']}", flush=True)
        return

    send_client_message(
        client,
        {
            "type": "authority/acquire",
            "ok": False,
            "granted": False,
            "reason": "authority_busy",
            "owner": owner,
            "owned_by_this_client": False,
            "available": False,
            "message": f"Command authority is already held by client {owner}.",
        },
    )
    print(
        f"Command authority denied to client {client['id']}; owner={owner}",
        flush=True,
    )


def handle_authority_release(client, state):
    owner = state.get("command_authority_owner")
    if owner == client["id"]:
        state["command_authority_owner"] = None
        reason = None
        message = "Command authority released."
        print(f"Command authority released by client {client['id']}", flush=True)
    elif owner is None:
        reason = "authority_required"
        message = "This connection does not hold command authority."
    else:
        reason = "authority_busy"
        message = "This client does not hold command authority."

    send_client_message(
        client,
        {
            "type": "authority/release",
            "ok": owner == client["id"],
            "granted": False,
            "reason": reason,
            "owner": state.get("command_authority_owner"),
            "owned_by_this_client": False,
            "available": state.get("command_authority_owner") is None,
            "message": message,
        },
    )


def client_has_command_authority(client, state):
    return state.get("command_authority_owner") == client["id"]


def reject_command_without_authority(client, message, state):
    owner = state.get("command_authority_owner")
    reason = "authority_required" if owner is None else "authority_busy"
    send_client_message(
        client,
        {
            "type": "command_rejected",
            "ok": False,
            "reason": reason,
            "command": command_name(message),
            "owner": owner,
            "available": owner is None,
            "owned_by_this_client": False,
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
            "command": command_name(message),
            "message": (
                "Axis Server is running, but EtherCAT drive initialization "
                f"failed: {state.get('initialization_error', 'unknown error')}"
            ),
        },
    )


def handle_message(message, master, state, client):
    if AXIS_SERVER_COMMAND_LOGS:
        print(
            "Axis Server received command: "
            f"client={client.get('id')} "
            f"{json.dumps(message, sort_keys=True, ensure_ascii=False)}",
            flush=True,
        )

    raw_message_type = command_name(message)
    message_type = public_command_name(message)

    if message_type in AUTHORITY_MESSAGE_TYPES:
        if message_type == "authority/acquire":
            handle_authority_acquire(client, state)
        elif message_type == "authority/release":
            handle_authority_release(client, state)
        elif message_type == "authority/status":
            send_client_message(client, authority_status_payload(client, state))
        return

    if message_type in ("system/status", "axis/status"):
        status = feedback_message(master, state, client["id"])
        status["type"] = message_type
        send_client_message(client, status)
        return

    if (
        message_type in ADVANCED_STATUS_MESSAGE_TYPES
        and not is_advanced_mode(state)
    ):
        status = feedback_message(master, state, client["id"])
        status["type"] = message_type
        status["trajectory"] = inactive_trajectory_state("advanced_only")
        status["trajectory"]["message"] = (
            f"{message_type} is available only in Axis Server advanced mode."
        )
        send_client_message(client, status)
        return

    if message_type == "axis/param_read":
        handle_sdo_read(message, master, client)
        return

    if (
        message_type in ADVANCED_MESSAGE_TYPES
        and not is_advanced_mode(state)
    ):
        reject_advanced_only_command(client, message, state)
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

    if message_type == "trajectory/status":
        handle_trajectory_status(client, master, state)
    elif message_type == "trajectory/move":
        handle_trajectory_command(
            trajectory_message_api_to_drive(message, state),
            master,
            state,
            axis_count=axis_count,
            faulted_axes=faulted_axes,
            disabled_operation_axes=disabled_operation_axes,
            hold_faulted_axes=hold_faulted_axes,
            ensure_csp_mode=ensure_csp_mode,
            inactive_trajectory_state=inactive_trajectory_state,
        )
    elif message_type == "trajectory/stop":
        handle_trajectory_stop(message, master, state, client)
    elif message_type == "system/stop":
        handle_system_stop(message, master, state)
    elif message_type == "system/reset":
        handle_fault_reset(master, state)
    elif message_type == "axis/enable":
        handle_axis_enable(message, master, state, client)
    elif message_type == "axis/disable":
        handle_axis_disable(message, master, state, client)
    elif message_type == "axis/reset":
        handle_axis_reset(message, master, state, client)
    elif message_type == "axis/home":
        handle_homing_start(message, master, state, client)
    elif message_type == "axis/stop":
        handle_axis_stop(message, master, state, client)
    elif message_type == "axis/move_abs":
        handle_axis_move_abs(message, master, state, client)
    elif message_type == "axis/move_rel":
        handle_axis_move_rel(message, master, state, client)
    elif message_type == "axis/move_vel":
        handle_axis_move_vel(message, master, state, client)
    elif message_type == "axis/jog_start":
        handle_axis_jog_start(message, master, state, client)
    elif message_type == "axis/jog_stop":
        handle_axis_jog_stop(message, master, state, client)
    elif message_type == "axis/profile":
        handle_axis_profile_settings(message, master, state, client)
    elif message_type == "axis/motion_limits":
        handle_axis_motion_limits(message, master, state, client)
    elif message_type == "axis/software_position_limits":
        handle_axis_software_position_limits(message, master, state, client)
    elif message_type == "axis/mode":
        handle_motion_mode(message, master, state, client)
    elif message_type == "axis/param_write":
        handle_param_write(message, master, client)
    elif message_type == "axis/param_save":
        handle_param_save(message, master, client)
    elif message_type == "debug/controlword":
        handle_controlword(message, master, state)
    elif raw_message_type:
        reject_command_message(
            client,
            raw_message_type,
            f"Unknown command: {raw_message_type}",
        )


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

# Feedback Update Helpers

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

# Position Output Helpers

def command_profile_positions(master, target_positions, axis_indices):
    for axis_index in axis_indices:
        require_pdo_fields_for_mode(master, "pp", axis_index)
        target_position = target_positions[axis_index]
        slave = master.slaves[axis_index]
        slave.rxpdo.mode_of_operation = PROFILE_POSITION_MODE
        slave.rxpdo.target_position = require_int32_value(
            target_position,
            f"axis {axis_index} target_position",
        )

    pp_setpoint_handshake(master, axis_indices)


def command_profile_velocities(master, state, axis_indices, velocities, command, client=None):
    faults = faulted_axes(master)
    if faults:
        hold_faulted_axes(master, state)
        master.sync_trajectory_to_actual_positions()
        print(
            f"Ignored {command} because at least one drive is faulted. "
            f"faulted_axes={faults} "
            f"statuswords={[f'0x{slave.txpdo.statusword:04X}' for slave in master.slaves]}",
            flush=True,
        )
        return

    if reject_if_any_axis_disabled(master, axis_indices, client, command):
        return

    if reject_if_pv_not_allowed(state, axis_indices, client, command):
        return

    for axis_index, velocity in zip(axis_indices, velocities):
        require_pdo_fields_for_mode(master, "pv", axis_index)
        slave = master.slaves[axis_index]
        target_velocity = require_int32_value(
            velocity,
            f"axis {axis_index} target_velocity",
        )
        slave.rxpdo.target_velocity = target_velocity
        if state["motion_modes"][axis_index] != "pv":
            hold_axis_at_actual_position(master, state, axis_index)
            configure_motion_mode(master, "pv", axis_index)
            state["motion_modes"][axis_index] = "pv"
        slave.rxpdo.mode_of_operation = PROFILE_VELOCITY_MODE
        slave.rxpdo.target_velocity = target_velocity
        slave.rxpdo.controlword = 0x000F
        master.trajectory_generators[axis_index].command_velocity = float(velocity)
        master.trajectory_generators[axis_index].target_position = float(
            slave.txpdo.actual_position
        )
        master.trajectory_generators[axis_index].command_position = float(
            slave.txpdo.actual_position
        )

    update_motion_mode_summary(state)
    exchange(master, cycles=2)


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
        diagnostics = diagnostics_summary(master, axis_indices)
        message = (
            "PP set-point handshake did not complete cleanly. "
            f"axes={axis_indices} "
            f"ack_cleared_before={ack_cleared_before} "
            f"ack_set={ack_set} "
            f"ack_cleared_after={ack_cleared_after} "
            f"statuswords={[f'0x{master.slaves[index].txpdo.statusword:04X}' for index in axis_indices]} "
            f"diagnostics={diagnostics}"
        )
        print(message, flush=True)
        raise RuntimeError(message)


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
    checked_positions = list(target_positions)
    for axis_index in axis_indices:
        checked_positions[axis_index] = require_int32_value(
            checked_positions[axis_index],
            f"axis {axis_index} target_position",
        )
    for axis_index in axis_indices:
        slave = master.slaves[axis_index]
        slave.rxpdo.mode_of_operation = CSP_MODE
        slave.rxpdo.controlword = 0x000F

    master.set_target_positions(checked_positions)

# Server Loops

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

# Main Entry

def list_adapters():
    loader = PySOEMMaster("unused", 1)
    pysoem = loader._load_pysoem()
    for adapter in pysoem.find_adapters():
        print(f"name={adapter.name}")
        print(f"desc={adapter.desc}")
        print()


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
    profile_settings=None,
    motion_limits=None,
    user_position_units=None,
    converting_unit_exponents=None,
    axis_metadata=None,
    initialized=True,
    initialization_error="",
):
    if motion_limits is None:
        motion_limits = [
            [
                args.max_velocity,
                -abs(args.max_velocity),
                args.acceleration,
                args.deceleration,
            ]
            for _ in range(args.axis_count)
        ]
    if profile_settings is None:
        profile_settings = [
            [
                args.max_velocity,
                args.acceleration,
                args.deceleration,
                args.pp_jerk,
            ]
            for _ in range(args.axis_count)
        ]
    if user_position_units is None:
        user_position_units = [None for _ in range(args.axis_count)]
    if converting_unit_exponents is None:
        converting_unit_exponents = [None for _ in range(args.axis_count)]
    if axis_metadata is None:
        axis_metadata = build_axis_metadata(
            user_position_units,
            converting_unit_exponents,
        )
    return {
        "drive_initialized": bool(initialized),
        "initialization_error": initialization_error,
        "server_mode": args.server_mode,
        "target_positions": positions,
        "derived_velocities": [0.0 for _ in range(args.axis_count)],
        "derived_velocity_positions": positions,
        "derived_velocity_time": None,
        "derived_velocity_alpha": max(
            0.0,
            min(1.0, args.derived_velocity_alpha),
        ),
        "motion_limits": motion_limits,
        "profile_settings": profile_settings,
        "software_position_limits": software_position_limits,
        "axis_metadata": axis_metadata,
        "user_position_units": user_position_units,
        "converting_unit_exponents": converting_unit_exponents,
        "motion_mode": args.motion_mode,
        "motion_modes": [
            args.motion_mode
            for _ in range(args.axis_count)
        ],
        "position_counts_per_unit": (
            args.csp_counts_per_unit
        ),
        "axis_position_counts_per_unit": axis_position_counts_per_api_units(
            {"axis_metadata": axis_metadata, "position_counts_per_unit": args.csp_counts_per_unit},
            args.axis_count,
        ),
        "capabilities": {
            "position_loop_gain": args.backend == "mock",
            "profile_settings": True,
            "motion_limits": True,
            "software_position_limits": True,
            "csp_trajectory_feedback": args.server_mode == "advanced",
            "trajectory_commands": args.server_mode == "advanced",
        },
        "trajectory": inactive_trajectory_state(),
        "trajectory_sequence": 0,
        "last_trajectory_complete_time": None,
        "tx_history": deque(maxlen=max(1, TX_HISTORY_LENGTH)),
        "homing": inactive_homing_state(),
        "jog_previous_modes": [None for _ in range(args.axis_count)],
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
    if args.list_adapters:
        list_adapters()
        return

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
            profile_settings = None
            read_motion_limits_state = None
            user_position_units = None
            converting_unit_exponents = None
            positions = [0.0 for _ in range(args.axis_count)]
            state = initial_server_state(
                args,
                positions,
                software_position_limits,
                profile_settings=profile_settings,
                motion_limits=read_motion_limits_state,
                user_position_units=user_position_units,
                converting_unit_exponents=converting_unit_exponents,
                initialized=False,
                initialization_error=initialization_error,
            )
        else:
            master.last_diagnostics = default_diagnostics(
                args.axis_count,
                "Panel SDO read pending",
            )
            software_position_limits = [
                [-1000000, 1000000]
                for _ in range(args.axis_count)
            ]
            profile_settings = [
                [
                    args.max_velocity,
                    args.acceleration,
                    args.deceleration,
                    args.pp_jerk,
                ]
                for _ in range(args.axis_count)
            ]
            read_motion_limits_state = [
                [
                    args.max_velocity,
                    -abs(args.max_velocity),
                    args.acceleration,
                    args.deceleration,
                ]
                for _ in range(args.axis_count)
            ]
            user_position_units = read_axis_user_position_units(master)
            converting_unit_exponents = read_axis_converting_unit_exponents(master)
            axis_metadata = build_axis_metadata(
                user_position_units,
                converting_unit_exponents,
            )
            unit_state = {
                "axis_metadata": axis_metadata,
                "position_counts_per_unit": (
                    args.csp_counts_per_unit
                    if args.backend == "pysoem"
                    else 1.0
                ),
            }
            axis_position_scales = axis_position_counts_per_api_units(
                unit_state,
                args.axis_count,
            )
            for axis_index, scale in enumerate(axis_position_scales):
                if hasattr(master, "set_axis_csp_counts_per_unit"):
                    master.set_axis_csp_counts_per_unit(axis_index, scale)
            profile_settings = [
                [
                    axis_motion_api_to_drive(unit_state, axis_index, args.max_velocity),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        args.acceleration,
                        "acceleration",
                    ),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        args.deceleration,
                        "deceleration",
                    ),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        args.pp_jerk,
                        "jerk",
                    ),
                ]
                for axis_index in range(args.axis_count)
            ]
            read_motion_limits_state = [
                [
                    axis_motion_api_to_drive(unit_state, axis_index, args.max_velocity),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        -abs(args.max_velocity),
                    ),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        args.acceleration,
                        "acceleration",
                    ),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        args.deceleration,
                        "deceleration",
                    ),
                ]
                for axis_index in range(args.axis_count)
            ]
            for axis_index, axis_profile_settings in enumerate(profile_settings):
                slave = master.slaves[axis_index]
                if slave.rxpdo.has_field("profile_velocity"):
                    slave.rxpdo.profile_velocity = require_uint32_value(
                        axis_profile_settings[0],
                        f"axis {axis_index} profile_velocity",
                    )
            for axis_index, axis_limits in enumerate(read_motion_limits_state):
                master.slaves[axis_index].axis_server_motion_limits = list(axis_limits)
                api_axis_limits = motion_limits_drive_to_api(
                    unit_state,
                    axis_index,
                    axis_limits,
                )
                master.set_axis_motion_limits(
                    axis_index,
                    max(abs(api_axis_limits[0]), abs(api_axis_limits[1])),
                    api_axis_limits[2],
                    api_axis_limits[3],
                    args.jerk,
                )
            positions = actual_positions(master)
            print(
                "Drive initialized. "
                f"backend={args.backend} "
                f"axes={args.axis_count} "
                f"cycle_time={args.cycle_time} "
                f"spin_wait_time={args.spin_wait_time} "
                f"csp_counts_per_unit={args.csp_counts_per_unit} "
                f"csp_profile={args.csp_profile} "
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
                profile_settings=profile_settings,
                motion_limits=read_motion_limits_state,
                user_position_units=user_position_units,
                converting_unit_exponents=converting_unit_exponents,
                axis_metadata=axis_metadata,
                initialized=True,
            )
            state["axis_position_counts_per_unit"] = axis_position_scales
            state["position_counts_per_unit"] = (
                axis_position_scales[0]
                if axis_position_scales
                else args.csp_counts_per_unit
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
