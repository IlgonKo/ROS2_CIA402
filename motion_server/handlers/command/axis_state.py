import time

from ethercat.mock_master import MockMaster
from motion_server.app.startup import refresh_axis_parameter_cache

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
    raise_operation_rejected,
    selected_axes,
)
from motion_server.api.encoder import status_data
from motion_server.app.state import inactive_trajectory_state
from motion_server.device_manager.profile_access import axis_device_profile
from motion_server.failure import (
    DeviceAccessException,
    MotionServerException,
    PartialFailure,
    collect_target_results,
)

HALT_BIT = 1 << 8
OPERATION_ENABLED_MASK = 0x006F
OPERATION_ENABLED_STATUS = 0x0027


def request_axis_halt(runtime, axis_index):
    slave = runtime.slaves[axis_index]
    slave.rxpdo.controlword = int(slave.rxpdo.controlword) | HALT_BIT


def stop_system(message, runtime, state):
    mode = str(message.get("mode", "controlled")).strip().lower()
    if mode != "controlled":
        print(f"Ignored unsupported system/stop mode: {mode}", flush=True)
        return

    if state.get("homing", {}).get("active"):
        finish_homing(runtime, state, "stopped", "Homing stopped by system/stop.")

    state["trajectory"] = inactive_trajectory_state("system_stop")
    positions = actual_positions(runtime)
    state["target_positions"] = positions
    runtime.set_target_positions(positions)
    runtime.sync_trajectory_to_actual_positions()
    enabled_axes = set(operation_enabled_axes(runtime, range(axis_count(runtime))))
    for axis_index, motion_mode in enumerate(state["motion_modes"]):
        if axis_index not in enabled_axes:
            continue
        if motion_mode == "pp":
            request_axis_halt(runtime, axis_index)
        elif motion_mode == "pv":
            command_profile_velocities(
                runtime,
                state,
                [axis_index],
                [0.0],
                "system/axes/stop",
                None,
            )
        elif motion_mode == "csp":
            request_axis_halt(runtime, axis_index)

    runtime.logger.status(
        "Received system/stop: "
        f"mode={mode} hold_positions={positions}",
    )


def stop_axes(message, runtime, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, runtime, command)
    except Exception as exc:
        raise_operation_rejected(client, command, str(exc))
        return
    if reject_if_any_axis_disabled(runtime, axes, client, command):
        return

    if state.get("homing", {}).get("active"):
        finish_homing(runtime, state, "stopped", "Homing stopped by axis/stop.")

    state["trajectory"] = inactive_trajectory_state("axis_stop")
    positions = list(state["target_positions"])
    actual = actual_positions(runtime)
    for axis_index in axes:
        positions[axis_index] = actual[axis_index]
        hold_axis_at_actual_position(runtime, state, axis_index)

    state["target_positions"] = positions
    runtime.set_target_positions(positions)
    runtime.sync_trajectory_to_actual_positions()
    enabled_axes = set(operation_enabled_axes(runtime, axes))
    for axis_index in axes:
        if axis_index not in enabled_axes:
            continue
        motion_mode = state["motion_modes"][axis_index]
        if motion_mode == "pp":
            request_axis_halt(runtime, axis_index)
        elif motion_mode == "pv":
            command_profile_velocities(
                runtime,
                state,
                [axis_index],
                [0.0],
                command,
                client,
            )
        elif motion_mode == "csp":
            request_axis_halt(runtime, axis_index)
        elif motion_mode == "jog":
            runtime.slaves[axis_index].rxpdo.controlword = 0x000F


def reset_faults(runtime, state, axis_indices=None):
    runtime.logger.status(
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

    runtime.logger.status(
        "Fault reset complete. "
        f"axes={axis_indices} "
        f"statuswords={[f'0x{runtime.slaves[index].txpdo.statusword:04X}' for index in axis_indices]} "
        f"controlwords={[f'0x{runtime.slaves[index].rxpdo.controlword:04X}' for index in axis_indices]}",
    )


def reset_axes(message, runtime, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, runtime, command)
    except Exception as exc:
        raise_operation_rejected(client, command, str(exc))
        return
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
    try:
        axes = selected_axes(message, runtime, command)
    except Exception as exc:
        raise_operation_rejected(client, command, str(exc))
        return
    if len(axes) != 1:
        raise_operation_rejected(client, command, f"{command} requires exactly one axis.")
        return

    axis_index = axes[0]
    profile = axis_device_profile(runtime, axis_index)
    if DeviceCapability.AXIS_RESTART not in profile.capabilities:
        raise_operation_rejected(
            client,
            command,
            f"Device profile {profile.name!r} does not support axis restart.",
        )
        return
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
            raise RuntimeError(
                "Axis did not leave Operation Enabled before restart. "
                f"statusword=0x{disabled_statusword:04X}"
            )
        disable_settle_time = max(
            0.0,
            float(state.get("axis_restart_disable_settle_time", 1.0)),
        )
        keep_pdo_alive_for_seconds(runtime, disable_settle_time)
        disabled_controlword = int(runtime.slaves[axis_index].rxpdo.controlword)
        disabled_statusword = int(runtime.slaves[axis_index].txpdo.statusword)
        result = profile.request_axis_restart(runtime, axis_index)
        if isinstance(runtime.ethercat_master, MockMaster):
            refresh_axis_parameter_cache(runtime, axis_index)
        result["disabled_controlword"] = f"0x{disabled_controlword:04X}"
        result["disabled_statusword"] = f"0x{disabled_statusword:04X}"
        result["disable_settle_time"] = disable_settle_time
    except Exception as exc:
        raise DeviceAccessException("axis_restart") from exc
    runtime.logger.status(
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
    try:
        axes = selected_axes(message, runtime, command)
    except Exception as exc:
        raise_operation_rejected(client, command, str(exc))
        return
    try:
        result = set_axes_controlword(runtime, axes, 0x000F)
    except MotionServerException as exc:
        raise_operation_rejected(client, command, str(exc))
        return
    if isinstance(result, PartialFailure):
        raise_operation_rejected(client, command, "Axis command partially failed.")
        return result
    exchange(runtime, cycles=3)
    runtime.logger.status(
        "Received axis/enable: "
        f"axes={axes} "
        f"statuswords={[f'0x{runtime.slaves[index].txpdo.statusword:04X}' for index in axes]}",
    )
    return status_data(axes_status_message(runtime, state, client["id"]))


def disable(message, runtime, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, runtime, command)
    except Exception as exc:
        raise_operation_rejected(client, command, str(exc))
        return

    trajectory = state.get("trajectory", {})
    if trajectory.get("active") and set(axes) & set(trajectory.get("axes", [])):
        state["trajectory"] = inactive_trajectory_state("axis_disable")

    homing = state.get("homing", {})
    if homing.get("active") and set(axes) & set(homing.get("axes", [])):
        finish_homing(runtime, state, "stopped", "Homing stopped by axis/disable.")

    def disable_axis(axis_index):
        hold_axis_at_actual_position(runtime, state, axis_index)
        set_axis_controlword(runtime, axis_index, 0x0007)

    try:
        result = collect_target_results(axes, disable_axis)
    except MotionServerException as exc:
        raise_operation_rejected(client, command, str(exc))
        return
    if isinstance(result, PartialFailure):
        raise_operation_rejected(client, command, "Axis command partially failed.")
    runtime.set_target_positions(state["target_positions"])
    exchange(runtime, cycles=3)
    runtime.logger.status(
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
    try:
        controlword = int(str(message.get("controlword")), 0)
    except (TypeError, ValueError):
        print(f"Ignored invalid controlword: {message.get('controlword')}", flush=True)
        return

    axis_value = message.get("axis", None)
    if axis_value is None:
        axis_indices = list(range(axis_count(runtime)))
        for slave in runtime.slaves:
            slave.rxpdo.controlword = controlword
        target_text = "all axes"
    else:
        try:
            axis_index = int(axis_value)
        except (TypeError, ValueError):
            print(f"Ignored controlword for invalid axis: {axis_value}", flush=True)
            return

        if axis_index < 0 or axis_index >= axis_count(runtime):
            print(f"Ignored controlword for invalid axis: {axis_index}", flush=True)
            return

        axis_indices = [axis_index]
        runtime.slaves[axis_index].rxpdo.controlword = controlword
        target_text = f"axis {axis_index}"

    if not is_operation_enabled_controlword(controlword):
        for axis_index in axis_indices:
            hold_axis_at_actual_position(runtime, state, axis_index)
        runtime.set_target_positions(state["target_positions"])

    runtime.logger.status(
        f"Manual controlword applied to {target_text}: 0x{controlword:04X}",
    )
