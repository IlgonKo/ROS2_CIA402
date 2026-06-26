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
from ethercat.mock_master import MockMaster
from ethercat.mock_slave import MockSlave
from ethercat.pysoem_master import PySOEMMaster
from motion.axis import Axis


DEFAULT_CYCLE_TIME = float(os.environ.get("PYSOEM_CYCLE_TIME", "0.01"))
DERIVED_VELOCITY_ALPHA = float(
    os.environ.get("PYSOEM_DERIVED_VELOCITY_ALPHA", "0.2")
)
FEEDBACK_PERIOD = 0.05
STATUS_LOG_PERIOD = 1.0
PROFILE_POSITION_MODE = 1
CSP_MODE = 8
CSV_MODE = 9
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
        "--axis-count",
        type=int,
        default=int(os.environ.get("PYSOEM_AXIS_COUNT", "1")),
    )
    parser.add_argument("--max-velocity", type=float, default=1000.0)
    parser.add_argument("--acceleration", type=float, default=500.0)
    parser.add_argument("--deceleration", type=float, default=500.0)
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

        return MockMaster(
            slaves,
            cycle_time=args.cycle_time,
            csp_counts_per_unit=args.csp_counts_per_unit,
        )

    return PySOEMMaster(
        interface_name=args.interface,
        slave_count=args.axis_count,
        cycle_time=args.cycle_time,
        motion_limits=motion_limits,
        csp_counts_per_unit=args.csp_counts_per_unit,
    )


def exchange(master, cycles=1):
    for _ in range(cycles):
        master.send_processdata()
        master.receive_processdata()
        time.sleep(master.cycle_time)


def axis_count(master):
    return len(master.slaves)


def faulted_axes(master):
    return [
        index
        for index, slave in enumerate(master.slaves)
        if slave.txpdo.statusword & 0x0008
    ]


def wait_status_all(master, expected_status, max_cycles=200):
    for _ in range(max_cycles):
        exchange(master)
        if all(
            (slave.txpdo.statusword & 0x006F) == expected_status
            for slave in master.slaves
        ):
            return True

    return False


def read_drive_diagnostics(master, axis_index):
    diagnostics = {}

    try:
        diagnostics["statusword"] = master.sdo_read_uint16(axis_index, 0x6041, 0)
    except Exception as exc:
        diagnostics["statusword"] = f"read failed: {exc}"

    try:
        diagnostics["error_code"] = master.sdo_read_uint16(axis_index, 0x603F, 0)
    except Exception as exc:
        diagnostics["error_code"] = f"read failed: {exc}"

    try:
        diagnostics["error_register"] = master.sdo_read_uint8(axis_index, 0x1001, 0)
    except Exception as exc:
        diagnostics["error_register"] = f"read failed: {exc}"

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
        f"ERR={format_value(diagnostics['error_code'], 4)} "
        f"ERR_REG={format_value(diagnostics['error_register'], 2)} "
        f"MODE_DISP={diagnostics['mode_display']}"
    )


def format_axis_diagnostics(diagnostics_list):
    return " | ".join(
        f"A{index}:{format_diagnostics(diagnostics)}"
        for index, diagnostics in enumerate(diagnostics_list)
    )


def mode_code(mode_name):
    return MOTION_MODES[mode_name]


def configure_motion_mode(master, mode_name, axis_index=None):
    code = mode_code(mode_name)
    if mode_name == "csp":
        configure_csp_interpolation_time(master, axis_index)

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


def configure_csp_interpolation_time(master, axis_index=None):
    period_ms = max(1, int(round(master.cycle_time * 1000.0)))
    axis_indices = (
        range(axis_count(master))
        if axis_index is None
        else [axis_index]
    )
    for current_axis in axis_indices:
        try:
            master.sdo_write_uint8(current_axis, 0x60C2, 1, period_ms)
            master.sdo_write_int8(current_axis, 0x60C2, 2, -3)
            print(
                f"Axis {current_axis}: CSP interpolation time set to "
                f"{period_ms} ms",
                flush=True,
            )
        except Exception as exc:
            print(
                f"Axis {current_axis}: CSP interpolation time object 0x60C2 "
                f"is not available; continuing without it ({exc})",
                flush=True,
            )


def initialize_drive(master, motion_mode):
    master.connect()
    configure_motion_mode(master, motion_mode)
    for axis_index in range(axis_count(master)):
        write_profile_motion_limits(master, axis_index)

    exchange(master, cycles=10)
    master.sync_trajectory_to_actual_positions()

    if faulted_axes(master):
        master.set_controlword_all(0x0080)
        wait_status_all(master, 0x0040)
        master.set_controlword_all(0x0000)
        exchange(master, cycles=10)

    for controlword, expected_status in [
        (0x0006, 0x0021),
        (0x0007, 0x0023),
        (0x000F, 0x0027),
    ]:
        master.set_controlword_all(controlword)
        if not wait_status_all(master, expected_status):
            statuswords = [
                f"0x{slave.txpdo.statusword:04X}"
                for slave in master.slaves
            ]
            raise RuntimeError(
                f"Failed to reach CiA402 status 0x{expected_status:04X}. "
                f"Statuswords={statuswords}"
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
        "command_velocities": [
            float(generator.command_velocity)
            for generator in master.trajectory_generators
        ],
        "statuswords": [
            int(slave.txpdo.statusword)
            for slave in master.slaves
        ],
        "motion_limits": flatten_motion_limits(state["motion_limits"]),
        "motion_mode": state["motion_mode"],
        "motion_modes": state["motion_modes"],
        "csp_counts_per_unit": master.csp_counts_per_unit,
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


def handle_target_positions(message, master, state):
    positions = [
        float(value)
        for value in message.get("positions", [])
    ]
    if len(positions) < axis_count(master):
        print(
            "Ignored target_positions because command length is too short. "
            f"expected={axis_count(master)} got={len(positions)}",
            flush=True,
        )
        return

    faults = faulted_axes(master)
    if faults:
        hold_faulted_axes(master, state)
        master.sync_trajectory_to_actual_positions()
        print(
            "Ignored target_positions because at least one drive is faulted. "
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
            "Ignored target_positions for CSV axes. "
            f"csv_axes={csv_axes}",
            flush=True,
        )
    if pp_axes:
        command_profile_positions(master, state["target_positions"], pp_axes)
    if csp_axes:
        command_csp_positions(master, state["target_positions"], csp_axes)

    print(
        "Received target_positions: "
        f"modes={state['motion_modes']} "
        f"targets={state['target_positions']} "
        f"current_actual={actual_positions(master)}",
        flush=True,
    )


def handle_jog_position(message, master, state):
    try:
        axis_index = int(message.get("axis"))
        distance = float(message.get("distance"))
    except (TypeError, ValueError):
        print(
            f"Ignored invalid jog_position command: {message}",
            flush=True,
        )
        return

    if axis_index < 0 or axis_index >= axis_count(master):
        print(f"Ignored jog_position for invalid axis: {axis_index}", flush=True)
        return

    positions = actual_positions(master)
    positions[axis_index] += distance
    print(
        "Received jog_position: "
        f"axis={axis_index} distance={distance:.3f} target={positions[axis_index]:.3f}",
        flush=True,
    )
    handle_target_positions({"positions": positions}, master, state)


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
        kp = float(axis_limits[3]) if len(axis_limits) > 3 else 0.0

        state["motion_limits"][axis_index] = [
            max_velocity,
            acceleration,
            deceleration,
            kp,
        ]
        master.set_axis_motion_limits(
            axis_index,
            max_velocity,
            acceleration,
            deceleration,
        )
        master.slaves[axis_index].rxpdo.profile_velocity = int(max_velocity)
        write_profile_motion_limits(master, axis_index)

    print(f"Received motion_limits: {state['motion_limits']}", flush=True)


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
    print("Received alarm_ack", flush=True)
    master.last_diagnostics = read_all_diagnostics(master)
    print(
        "Alarm before ack: "
        f"{format_axis_diagnostics(master.last_diagnostics)}",
        flush=True,
    )

    state["target_positions"] = actual_positions(master)
    master.set_target_positions(state["target_positions"])
    master.sync_trajectory_to_actual_positions()
    exchange(master, cycles=10)

    for axis_index, motion_mode in enumerate(state["motion_modes"]):
        configure_motion_mode(master, motion_mode, axis_index)

    master.set_controlword_all(0x0000)
    exchange(master, cycles=10)
    master.set_controlword_all(0x0080)
    reset_done = wait_status_all(master, 0x0040, max_cycles=300)

    master.last_diagnostics = read_all_diagnostics(master)
    print(
        "Alarm after reset request: "
        f"reset_done={reset_done} "
        f"{format_axis_diagnostics(master.last_diagnostics)}",
        flush=True,
    )

    if not reset_done:
        return

    master.set_controlword_all(0x0000)
    exchange(master, cycles=10)

    for controlword, expected_status in [
        (0x0006, 0x0021),
        (0x0007, 0x0023),
        (0x000F, 0x0027),
    ]:
        master.set_controlword_all(controlword)
        reached = wait_status_all(master, expected_status, max_cycles=300)
        print(
            f"Alarm ack transition cw=0x{controlword:04X} "
            f"expected=0x{expected_status:04X} reached={reached} "
            f"statuswords={[f'0x{slave.txpdo.statusword:04X}' for slave in master.slaves]}",
            flush=True,
        )
        if not reached:
            master.last_diagnostics = read_all_diagnostics(master)
            print(
                "Alarm ack transition failed: "
                f"{format_axis_diagnostics(master.last_diagnostics)}",
                flush=True,
            )
            return

    master.sync_trajectory_to_actual_positions()
    state["target_positions"] = actual_positions(master)
    print(
        "Alarm ack complete. "
        f"statuswords={[f'0x{slave.txpdo.statusword:04X}' for slave in master.slaves]} "
        f"AP={actual_positions(master)}",
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
    "target_positions",
    "jog_position",
    "motion_limits",
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

    if message_type == "target_positions":
        handle_target_positions(message, master, state)
    elif message_type == "jog_position":
        handle_jog_position(message, master, state)
    elif message_type == "motion_limits":
        handle_motion_limits(message, master, state)
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
    now = time.monotonic()
    if now - last_status_log_time < STATUS_LOG_PERIOD:
        return last_status_log_time

    master.last_diagnostics = read_all_diagnostics(master)
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

    for axis_index in axis_indices:
        master.slaves[axis_index].rxpdo.controlword = 0x000F
    exchange(master, cycles=2)

    for axis_index in axis_indices:
        master.slaves[axis_index].rxpdo.controlword = 0x001F
    exchange(master, cycles=2)

    for axis_index in axis_indices:
        master.slaves[axis_index].rxpdo.controlword = 0x000F


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


def allocate_client_id(clients):
    used_ids = {client["id"] for client in clients}
    client_id = 1
    while client_id in used_ids:
        client_id += 1
    return client_id


def run_server_loop(server, master, state):
    server.setblocking(False)
    clients = []
    last_feedback_update_time = 0.0
    last_status_log_time = 0.0

    while True:
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

        hold_faulted_axes(master, state)
        exchange(master)

        now = time.monotonic()
        if clients and now - last_feedback_update_time >= FEEDBACK_PERIOD:
            update_derived_velocities(master, state, now)
            last_feedback_update_time = now

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
        }
        for _ in range(args.axis_count)
    ]
    master = create_master(args, motion_limits)

    try:
        initialize_drive(master, args.motion_mode)
        for slave in master.slaves:
            slave.rxpdo.profile_velocity = int(args.max_velocity)

        master.last_diagnostics = read_all_diagnostics(master)
        positions = actual_positions(master)
        print(
            "Drive initialized. "
            f"backend={args.backend} "
            f"axes={args.axis_count} "
            f"cycle_time={args.cycle_time} "
            f"csp_counts_per_unit={args.csp_counts_per_unit} "
            f"derived_velocity_alpha={args.derived_velocity_alpha} "
            f"statuswords={[f'0x{slave.txpdo.statusword:04X}' for slave in master.slaves]} "
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
                    0.0,
                ]
                for _ in range(args.axis_count)
            ],
            "motion_mode": args.motion_mode,
            "motion_modes": [
                args.motion_mode
                for _ in range(args.axis_count)
            ],
            "command_authority_owner": None,
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
