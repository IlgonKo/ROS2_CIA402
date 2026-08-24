import time

from motion_server.config import (
    HOMING_ERROR_MASK,
    HOMING_MIN_MONITOR_TIME,
    HOMING_MODE,
    HOMING_REFERENCED_MASK,
    HOMING_START_BIT,
    MOTION_MODES,
    status_log,
)
from motion_server.app.cycle import exchange
from motion_server.api.encoder import public_homing_state
from motion_server.control.axis_operations import (
    axis_count,
    configure_mode_code,
    configure_motion_mode,
    disabled_operation_axes,
    update_motion_mode_summary,
)
from motion_server.api import parse_axis_indices
from motion_server.api.encoder import status_data
from motion_server.failure import InvalidStateException


def homing_axis_status(runtime, axis_index):
    statusword = int(runtime.slaves[axis_index].txpdo.statusword)
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
        "actual_position": float(runtime.slaves[axis_index].txpdo.actual_position),
        "mode_display": int(runtime.slaves[axis_index].txpdo.mode_of_operation_display),
    }


def homing_status_message(runtime, state):
    homing = public_homing_state(state)
    axes = homing["axes"] or list(range(axis_count(runtime)))
    homing["per_axis"] = [
        homing_axis_status(runtime, axis_index)
        for axis_index in axes
    ]
    return {
        "type": "homing_status",
        "homing": homing,
    }


def set_homing_start_bit(runtime, axis_indices, enabled):
    for axis_index in axis_indices:
        slave = runtime.slaves[axis_index]
        controlword = int(slave.rxpdo.controlword)
        if enabled:
            controlword |= HOMING_START_BIT
        else:
            controlword &= ~HOMING_START_BIT
        slave.rxpdo.controlword = controlword


def finish_homing(runtime, state, result, message):
    homing = state.get("homing", {})
    axes = homing.get("axes", [])
    if not axes:
        return

    set_homing_start_bit(runtime, axes, False)
    exchange(runtime, cycles=2)

    original_modes = homing.get("original_motion_modes", {})
    for axis_index in axes:
        original_mode = original_modes.get(axis_index)
        if original_mode in MOTION_MODES:
            configure_motion_mode(runtime, original_mode, axis_index)
            state["motion_modes"][axis_index] = original_mode

    update_motion_mode_summary(state)
    homing["active"] = False
    homing["state"] = result
    homing["message"] = message
    status_log(
        "Homing finished: "
        f"state={result} axes={axes} message={message} "
        f"modes={state['motion_modes']} "
        f"controlwords={[f'0x{runtime.slaves[index].rxpdo.controlword:04X}' for index in axes]}",
    )


def start_homing(message, runtime, state, client):
    command = str(message.get("cmd", "system/axis/home")).strip()
    axis_indices = parse_axis_indices(message, runtime, command)
    disabled_axes = disabled_operation_axes(runtime, axis_indices)
    if disabled_axes:
        message_text = (
            "Axis operation is disabled. "
            f"disabled_axes={disabled_axes}"
        )
        print(f"Ignored {command}: {message_text}", flush=True)
        raise InvalidStateException(command, "axis_disabled")

    original_modes = {
        axis_index: state["motion_modes"][axis_index]
        for axis_index in axis_indices
    }
    for axis_index in axis_indices:
        configure_mode_code(runtime, HOMING_MODE, axis_index)
        state["motion_modes"][axis_index] = "homing"
    update_motion_mode_summary(state)

    set_homing_start_bit(runtime, axis_indices, False)
    exchange(runtime, cycles=2)

    initial_referenced = {
        axis_index: bool(
            runtime.slaves[axis_index].txpdo.statusword & HOMING_REFERENCED_MASK
        )
        for axis_index in axis_indices
    }
    referenced_seen_low = {
        axis_index: not referenced
        for axis_index, referenced in initial_referenced.items()
    }

    set_homing_start_bit(runtime, axis_indices, True)
    exchange(runtime, cycles=2)

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
    status_log(
        f"Received {command}: "
        f"axes={axis_indices} "
        f"original_modes={original_modes} "
        f"initial_referenced={initial_referenced} "
        f"controlwords={[f'0x{runtime.slaves[index].rxpdo.controlword:04X}' for index in axis_indices]}",
    )
    return status_data(homing_status_message(runtime, state))


def update_homing_state(runtime, state):
    homing = state.get("homing", {})
    if not homing.get("active"):
        return

    axes = homing.get("axes", [])
    statuses = [
        homing_axis_status(runtime, axis_index)
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
        finish_homing(runtime, state, "error", "Homing error bit is set.")
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
        finish_homing(runtime, state, "complete", "Axis referenced.")
