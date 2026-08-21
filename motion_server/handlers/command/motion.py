from motion_server.config import HOMING_REFERENCED_MASK
from motion_server.control.axis_units import (
    axis_motion_api_to_drive,
    axis_position_api_to_drive,
)
from motion_server.control.axis_operations import (
    actual_positions,
    axis_count,
    disabled_operation_axes,
    faulted_axes,
    hold_axis_at_actual_position,
    hold_faulted_axes,
)
from motion_server.control.setpoint_output import (
    command_csp_positions,
    command_profile_positions,
    command_profile_velocities,
)
from motion_server.api import (
    public_command_name,
    raise_operation_rejected,
    require_int32,
    require_uint32,
    selected_axes,
)
from motion_server.failure import InvalidStateException


def unreferenced_axes(runtime, axes):
    return [
        axis_index
        for axis_index in axes
        if not int(runtime.slaves[axis_index].txpdo.statusword) & HOMING_REFERENCED_MASK
    ]


def command_position_axes(runtime, state, axes, positions, command_name, client=None):
    faults = faulted_axes(runtime)
    if faults:
        hold_faulted_axes(runtime, state)
        runtime.sync_trajectory_to_actual_positions()
        print(
            f"Ignored {command_name} because at least one drive is faulted. "
            f"faulted_axes={faults} "
            f"statuswords={[f'0x{slave.txpdo.statusword:04X}' for slave in runtime.slaves]}",
            flush=True,
        )
        raise InvalidStateException(command_name, "axis_fault")

    disabled_axes = disabled_operation_axes(runtime, axes)
    if disabled_axes:
        message_text = (
            "Axis operation is disabled. "
            f"disabled_axes={disabled_axes} "
            f"statuswords={[f'0x{runtime.slaves[index].txpdo.statusword:04X}' for index in disabled_axes]}"
        )
        if client is not None:
            raise_operation_rejected(client, command_name, message_text)
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
            command_profile_positions(runtime, state["target_positions"], pp_axes)
        if csp_axes:
            command_csp_positions(runtime, state["target_positions"], csp_axes)
    except Exception as exc:
        actual = actual_positions(runtime)
        for axis_index in axes:
            state["target_positions"][axis_index] = actual[axis_index]
            hold_axis_at_actual_position(runtime, state, axis_index)
        runtime.set_target_positions(state["target_positions"])
        message_text = (
            f"{command_name} failed while sending position command: {exc}"
        )
        if client is not None:
            raise_operation_rejected(client, command_name, message_text)
        print(
            f"Ignored {command_name}: {message_text} "
            f"axes={axes} statuswords="
            f"{[f'0x{runtime.slaves[index].txpdo.statusword:04X}' for index in axes]}",
            flush=True,
        )


def axis_velocities_from_message(message, runtime, state, command):
    axes = selected_axes(message, runtime, command)
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


def axis_positions_from_message(message, runtime, state, command):
    axes = selected_axes(message, runtime, command)
    if "positions" in message:
        values = [
            float(value)
            for value in message.get("positions", [])
        ]
    elif "position" in message:
        values = [float(message.get("position"))]
    else:
        raise ValueError(f"{command} requires positions or position")

    if len(values) == axis_count(runtime) and len(axes) == axis_count(runtime):
        return [
            require_int32(
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
        positions[axis_index] = require_int32(
            axis_position_api_to_drive(state, axis_index, value),
            f"axis {axis_index} target_position",
        )
    return positions


def axis_distances_from_message(message, runtime, state, command):
    axes = selected_axes(message, runtime, command)
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
        require_int32(
            axis_position_api_to_drive(state, axis_index, value),
            f"axis {axis_index} target_distance",
        )
        for axis_index, value in zip(axes, values)
    ]


def move_absolute(message, runtime, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, runtime, command)
        positions = axis_positions_from_message(message, runtime, state, command)
        apply_move_profile_velocity(message, runtime, state, axes)
    except Exception as exc:
        raise_operation_rejected(client, command, str(exc))
        return

    not_referenced = unreferenced_axes(runtime, axes)
    if not_referenced:
        message_text = (
            "Absolute move requires referenced axes. "
            f"unreferenced_axes={not_referenced} "
            f"statuswords={[f'0x{runtime.slaves[index].txpdo.statusword:04X}' for index in not_referenced]}"
        )
        raise_operation_rejected(client, command, message_text)
        print(f"Ignored {command}: {message_text}", flush=True)
        return

    command_position_axes(runtime, state, axes, positions, command, client)


def move_relative(message, runtime, state, client):
    command = public_command_name(message)
    try:
        axes, distances = axis_distances_from_message(message, runtime, state, command)
        apply_move_profile_velocity(message, runtime, state, axes)
    except Exception as exc:
        raise_operation_rejected(client, command, str(exc))
        return

    positions = runtime.relative_target_positions(axes, distances)
    for axis_index in axes:
        positions[axis_index] = require_int32(
            positions[axis_index],
            f"axis {axis_index} target_position",
        )
    command_position_axes(runtime, state, axes, positions, command, client)


def move_velocity(message, runtime, state, client):
    command = public_command_name(message)
    try:
        axes, velocities = axis_velocities_from_message(message, runtime, state, command)
    except Exception as exc:
        raise_operation_rejected(client, command, str(exc))
        return

    command_profile_velocities(runtime, state, axes, velocities, command, client)


def apply_move_profile_velocity(message, runtime, state, axes):
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
        slave = runtime.slaves[axis_index]
        if slave.rxpdo.has_field("profile_velocity"):
            slave.rxpdo.profile_velocity = require_uint32(
                drive_profile_velocity,
                f"axis {axis_index} profile_velocity",
            )
