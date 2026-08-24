import time

from device.capabilities import DeviceCapability

from motion_server.handlers.command.homing import finish_homing
from motion_server.app.cycle import exchange
from motion_server.handlers.status import axes_status_message
from motion_server.control.axis_operations import (
    actual_positions,
    axis_count,
    hold_axis_at_actual_position,
    operation_enabled_axes,
    reject_if_any_axis_disabled,
)
from motion_server.control.setpoint_output import (
    command_profile_velocities,
)
from motion_server.api import (
    public_command_name,
    selected_axes,
)
from motion_server.api.encoder import status_data
from motion_server.app.state import inactive_trajectory_state
from motion_server.config import (
    AXIS_RESTART_DISABLE_SETTLE_TIME,
    DEVICE_PROFILE,
    status_log,
)
from motion_server.failure import (
    DeviceAccessException,
    InvalidArgumentException,
    ItemFailure,
    MotionServerException,
    OperationTimeoutException,
    PartialFailure,
    UnsupportedOperationException,
    collect_target_results,
)

HALT_BIT = 1 << 8
OPERATION_ENABLED_MASK = 0x006F
OPERATION_ENABLED_STATUS = 0x0027


def request_axis_halt(runtime, axis_index):
    try:
        controlword = int(runtime.slaves[axis_index].rxpdo.controlword)
    except (OSError, AttributeError, TypeError, ValueError) as exc:
        raise DeviceAccessException("axis_controlword_read") from exc
    set_axis_controlword(runtime, axis_index, controlword | HALT_BIT)


def stop_axes(message, runtime, state, client):
    command = public_command_name(message)
    axes = selected_axes(message, runtime, command)
    if reject_if_any_axis_disabled(runtime, axes, client, command):
        return

    positions = list(state["target_positions"])
    actual = actual_positions(runtime)
    enabled_axes = set(operation_enabled_axes(runtime, axes))
    stopped_axes = []
    failed = []
    for axis_index in axes:
        if axis_index not in enabled_axes:
            continue
        motion_mode = state["motion_modes"][axis_index]
        try:
            if motion_mode == "pv":
                command_profile_velocities(
                    runtime,
                    state,
                    [axis_index],
                    [0.0],
                    command,
                    client,
                )
            else:
                request_axis_halt(runtime, axis_index)
        except MotionServerException as exc:
            failed.append(ItemFailure(axis_index, exc))
            continue
        positions[axis_index] = actual[axis_index]
        stopped_axes.append(axis_index)

    if stopped_axes:
        state["target_positions"] = positions
        runtime.set_target_positions(positions)
        runtime.sync_trajectory_to_actual_positions()
        if state.get("homing", {}).get("active"):
            finish_homing(runtime, state, "stopped", "Homing stopped by axis/stop.")
        state["trajectory"] = inactive_trajectory_state("axis_stop")
    if failed:
        if not stopped_axes:
            raise failed[0].exception
        return PartialFailure(stopped_axes, failed)
    status_log(
        "Received axis/stop: "
        f"axes={axes} hold_positions={positions}",
    )
    return status_data(axes_status_message(runtime, state, client["id"]))


def reset_faults(runtime, state, axis_indices=None):
    status_log(
        "Received fault reset: pulsing fault reset bit, then switching on",
    )
    if axis_indices is None:
        axis_indices = list(range(axis_count(runtime)))
    original_controlwords = [
        int(runtime.slaves[axis_index].rxpdo.controlword)
        for axis_index in axis_indices
    ]

    for axis_index, controlword in zip(axis_indices, original_controlwords):
        slave = runtime.slaves[axis_index]
        slave.rxpdo.controlword = controlword & ~0x0080
    exchange(runtime, cycles=2)

    for axis_index, controlword in zip(axis_indices, original_controlwords):
        slave = runtime.slaves[axis_index]
        slave.rxpdo.controlword = controlword | 0x0080
    exchange(runtime, cycles=2)

    for axis_index, controlword in zip(axis_indices, original_controlwords):
        slave = runtime.slaves[axis_index]
        slave.rxpdo.controlword = controlword & ~0x0080
    exchange(runtime, cycles=2)

    for axis_index in axis_indices:
        runtime.slaves[axis_index].rxpdo.controlword = 0x0006
    exchange(runtime, cycles=5)

    for axis_index in axis_indices:
        runtime.slaves[axis_index].rxpdo.controlword = 0x0007
    exchange(runtime, cycles=5)

    status_log(
        "Fault reset complete. "
        f"axes={axis_indices} "
        f"statuswords={[f'0x{runtime.slaves[index].txpdo.statusword:04X}' for index in axis_indices]} "
        f"controlwords={[f'0x{runtime.slaves[index].rxpdo.controlword:04X}' for index in axis_indices]}",
    )


def reset_axes(message, runtime, state, client):
    command = public_command_name(message)
    axes = selected_axes(message, runtime, command)
    reset_faults(runtime, state, axes)


def wait_axis_not_operation_enabled(runtime, axis_index, max_cycles=50):
    for _ in range(max(1, int(max_cycles))):
        exchange(runtime, cycles=1)
        statusword = int(runtime.slaves[axis_index].txpdo.statusword)
        if (statusword & OPERATION_ENABLED_MASK) != OPERATION_ENABLED_STATUS:
            return True
    return False


def keep_pdo_alive_for_seconds(runtime, seconds):
    deadline = time.monotonic() + max(0.0, float(seconds))
    while time.monotonic() < deadline:
        exchange(runtime, cycles=1)


def restart_axis(message, runtime, state, client):
    command = public_command_name(message)
    if DeviceCapability.AXIS_RESTART not in DEVICE_PROFILE.capabilities:
        raise UnsupportedOperationException(
            command,
            f"Device profile {DEVICE_PROFILE.name!r} does not support axis restart",
        )
    axes = selected_axes(message, runtime, command)
    if len(axes) != 1:
        raise InvalidArgumentException("axis", "requires exactly one axis")

    axis_index = axes[0]
    try:
        homing = state.get("homing", {})
        if homing.get("active") and axis_index in homing.get("axes", []):
            finish_homing(
                runtime,
                state,
                "stopped",
                "Homing stopped by axis/restart.",
            )

        trajectory = state.get("trajectory", {})
        if trajectory.get("active") and axis_index in trajectory.get("axes", []):
            state["trajectory"] = inactive_trajectory_state("axis_restart")

        hold_axis_at_actual_position(runtime, state, axis_index)
        runtime.set_target_positions(state["target_positions"])
        runtime.slaves[axis_index].rxpdo.controlword = 0x0007
        disabled = wait_axis_not_operation_enabled(runtime, axis_index)
        disabled_statusword = int(runtime.slaves[axis_index].txpdo.statusword)
        if not disabled:
            raise OperationTimeoutException(
                "axis_restart_disable",
                timeout_seconds=(50 * float(runtime.cycle_time)),
            )
        disable_settle_time = max(0.0, float(AXIS_RESTART_DISABLE_SETTLE_TIME))
        keep_pdo_alive_for_seconds(runtime, disable_settle_time)
        disabled_controlword = int(runtime.slaves[axis_index].rxpdo.controlword)
        disabled_statusword = int(runtime.slaves[axis_index].txpdo.statusword)
        result = DEVICE_PROFILE.request_axis_restart(runtime, axis_index)
        result["disabled_controlword"] = f"0x{disabled_controlword:04X}"
        result["disabled_statusword"] = f"0x{disabled_statusword:04X}"
        result["disable_settle_time"] = disable_settle_time
    except OperationTimeoutException:
        raise
    except (OSError, AttributeError, TypeError, ValueError) as exc:
        raise DeviceAccessException("axis_restart") from exc
    status_log(
        "Axis restart requested: "
        f"axis={axis_index} result={result}",
    )
    return {
        "axis": axis_index,
        "result": result,
        "message": "Axis restart command sent.",
    }


def enable(message, runtime, state, client):
    command = public_command_name(message)
    axes = selected_axes(message, runtime, command)
    result = set_axes_controlword(runtime, axes, 0x000F)
    if isinstance(result, PartialFailure):
        return result
    exchange(runtime, cycles=3)
    status_log(
        "Received axis/enable: "
        f"axes={axes} "
        f"statuswords={[f'0x{runtime.slaves[index].txpdo.statusword:04X}' for index in axes]}",
    )
    return status_data(axes_status_message(runtime, state, client["id"]))


def disable(message, runtime, state, client):
    command = public_command_name(message)
    axes = selected_axes(message, runtime, command)
    actual = actual_positions(runtime)

    def disable_axis(axis_index):
        set_axis_controlword(runtime, axis_index, 0x0007)

    result = collect_target_results(axes, disable_axis)
    succeeded_axes = (
        list(result.succeeded)
        if isinstance(result, PartialFailure)
        else list(axes)
    )
    if succeeded_axes:
        positions = list(state["target_positions"])
        for axis_index in succeeded_axes:
            positions[axis_index] = actual[axis_index]
        state["target_positions"] = positions
        trajectory = state.get("trajectory", {})
        if trajectory.get("active") and set(succeeded_axes) & set(trajectory.get("axes", [])):
            state["trajectory"] = inactive_trajectory_state("axis_disable")

        homing = state.get("homing", {})
        if homing.get("active") and set(succeeded_axes) & set(homing.get("axes", [])):
            finish_homing(runtime, state, "stopped", "Homing stopped by axis/disable.")
    runtime.set_target_positions(state["target_positions"])
    exchange(runtime, cycles=3)
    status_log(
        "Received axis/disable: "
        f"axes={axes} "
        f"statuswords={[f'0x{runtime.slaves[index].txpdo.statusword:04X}' for index in axes]}",
    )
    if isinstance(result, PartialFailure):
        return result
    return status_data(axes_status_message(runtime, state, client["id"]))


def set_axis_controlword(runtime, axis_index, controlword):
    try:
        runtime.slaves[axis_index].rxpdo.controlword = controlword
    except (OSError, AttributeError, TypeError, ValueError) as exc:
        raise DeviceAccessException("axis_controlword_write") from exc


def set_axes_controlword(runtime, axes, controlword):
    return collect_target_results(
        axes,
        lambda axis_index: set_axis_controlword(runtime, axis_index, controlword),
    )


def is_operation_enabled_controlword(controlword):
    return (int(controlword) & 0x008F) in {0x000F, 0x001F}


def set_controlword(message, runtime, state):
    command = public_command_name(message)
    try:
        controlword = int(str(message.get("controlword")), 0)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentException(
            "controlword", "must be an integer",
        ) from exc
    if controlword < 0 or controlword > 0xFFFF:
        raise InvalidArgumentException(
            "controlword",
            "is outside uint16 range [0, 65535]",
            public_value=controlword,
        )

    axis_indices = selected_axes(message, runtime, command)
    if len(axis_indices) != 1:
        raise InvalidArgumentException("axis", "requires exactly one axis")
    axis_index = axis_indices[0]
    set_axis_controlword(runtime, axis_index, controlword)

    if not is_operation_enabled_controlword(controlword):
        hold_axis_at_actual_position(runtime, state, axis_index)
        runtime.set_target_positions(state["target_positions"])

    status_log(
        f"Manual controlword applied to axis {axis_index}: 0x{controlword:04X}",
    )
