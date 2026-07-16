from motion_server.commands.homing import finish_homing
from motion_server.app.cycle import exchange
from motion_server.api.feedback import feedback_message
from motion_server.control.axis_operations import (
    actual_positions,
    axis_count,
    hold_axis_at_actual_position,
    operation_enabled_axes,
    reject_if_any_axis_disabled,
)
from motion_server.control.setpoint_output import (
    command_csp_positions,
    command_profile_positions,
    command_profile_velocities,
)
from motion_server.api import (
    public_command_name,
    reject_command_message,
    selected_axes,
    send_client_message,
)
from motion_server.app.state import inactive_trajectory_state


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
            command_profile_positions(runtime, positions, [axis_index])
        elif motion_mode == "pv":
            command_profile_velocities(
                runtime,
                state,
                [axis_index],
                [0.0],
                "system/stop",
                None,
            )
        elif motion_mode == "csp":
            command_csp_positions(runtime, positions, [axis_index])

    print(
        "Received system/stop: "
        f"mode={mode} hold_positions={positions}",
        flush=True,
    )


def stop_axes(message, runtime, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, runtime, command)
    except Exception as exc:
        reject_command_message(client, command, str(exc))
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
            command_profile_positions(runtime, positions, [axis_index])
        elif motion_mode == "pv":
            command_profile_velocities(
                runtime,
                state,
                [axis_index],
                [0.0],
                "axis/stop",
                client,
            )
        elif motion_mode == "csp":
            command_csp_positions(runtime, positions, [axis_index])
        elif motion_mode == "jog":
            runtime.slaves[axis_index].rxpdo.controlword = 0x000F


def reset_faults(runtime, state, axis_indices=None):
    print(
        "Received fault reset: pulsing fault reset bit, then switching on",
        flush=True,
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

    print(
        "Fault reset complete. "
        f"axes={axis_indices} "
        f"statuswords={[f'0x{runtime.slaves[index].txpdo.statusword:04X}' for index in axis_indices]} "
        f"controlwords={[f'0x{runtime.slaves[index].rxpdo.controlword:04X}' for index in axis_indices]}",
        flush=True,
    )


def reset_axes(message, runtime, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, runtime, command)
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return
    reset_faults(runtime, state, axes)


def enable(message, runtime, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, runtime, command)
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return
    for axis_index in axes:
        runtime.slaves[axis_index].rxpdo.controlword = 0x000F
    exchange(runtime, cycles=3)
    print(
        "Received axis/enable: "
        f"axes={axes} "
        f"statuswords={[f'0x{runtime.slaves[index].txpdo.statusword:04X}' for index in axes]}",
        flush=True,
    )
    send_client_message(client, feedback_message(runtime, state, client["id"]))


def disable(message, runtime, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, runtime, command)
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return

    trajectory = state.get("trajectory", {})
    if trajectory.get("active") and set(axes) & set(trajectory.get("axes", [])):
        state["trajectory"] = inactive_trajectory_state("axis_disable")

    homing = state.get("homing", {})
    if homing.get("active") and set(axes) & set(homing.get("axes", [])):
        finish_homing(runtime, state, "stopped", "Homing stopped by axis/disable.")

    for axis_index in axes:
        hold_axis_at_actual_position(runtime, state, axis_index)
        runtime.slaves[axis_index].rxpdo.controlword = 0x0007
    runtime.set_target_positions(state["target_positions"])
    exchange(runtime, cycles=3)
    print(
        "Received axis/disable: "
        f"axes={axes} "
        f"statuswords={[f'0x{runtime.slaves[index].txpdo.statusword:04X}' for index in axes]}",
        flush=True,
    )
    send_client_message(client, feedback_message(runtime, state, client["id"]))


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

    print(
        f"Manual controlword applied to {target_text}: 0x{controlword:04X}",
        flush=True,
    )
