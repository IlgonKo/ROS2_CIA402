from motion_server.control.axis_units import (
    axis_motion_drive_to_api,
    axis_position_drive_to_api,
    motion_limits_drive_to_api,
    profile_settings_drive_to_api,
)


def feedback_message(runtime, state, client_id=None):
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
            for axis_index, slave in enumerate(runtime.slaves)
        ],
        "actual_velocities": [
            axis_motion_drive_to_api(state, axis_index, slave.txpdo.actual_velocity)
            for axis_index, slave in enumerate(runtime.slaves)
        ],
        "derived_velocities": [
            axis_motion_drive_to_api(state, axis_index, value)
            for axis_index, value in enumerate(state["derived_velocities"])
        ],
        "command_positions": [
            axis_position_drive_to_api(state, axis_index, generator.command_position)
            for axis_index, generator in enumerate(runtime.trajectory_generators)
        ],
        "command_velocities": [
            axis_motion_drive_to_api(state, axis_index, generator.command_velocity)
            for axis_index, generator in enumerate(runtime.trajectory_generators)
        ],
        "statuswords": [
            int(slave.txpdo.statusword)
            for slave in runtime.slaves
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
        "csp_counts_per_unit": runtime.csp_counts_per_unit,
        "position_counts_per_unit": state["position_counts_per_unit"],
        "axis_position_counts_per_unit": state.get(
            "axis_position_counts_per_unit",
            [],
        ),
        "capabilities": state["capabilities"],
        "trajectory": public_trajectory_state(state),
        "homing": public_homing_state(state),
        "diagnostics": runtime.last_diagnostics,
        "command_authority": {
            "owner": owner,
            "owned_by_this_client": owner is not None and owner == client_id,
            "available": owner is None,
        },
    }


def axis_status_message(runtime, state, axis_index, client_id=None):
    axis_index = int(axis_index)
    owner = state.get("command_authority_owner")
    user_position_units = state.get("user_position_units", [])
    converting_unit_exponents = state.get("converting_unit_exponents", [])
    axis_position_counts_per_unit = state.get(
        "axis_position_counts_per_unit",
        [],
    )
    axis_metadata = state.get("axis_metadata", [])
    return {
        "type": "axis/status",
        "axis": axis_index,
        "drive_initialized": bool(state.get("drive_initialized", True)),
        "initialization_error": state.get("initialization_error", ""),
        "target_position": axis_position_drive_to_api(
            state,
            axis_index,
            state["target_positions"][axis_index],
        ),
        "actual_position": axis_position_drive_to_api(
            state,
            axis_index,
            runtime.slaves[axis_index].txpdo.actual_position,
        ),
        "actual_velocity": axis_motion_drive_to_api(
            state,
            axis_index,
            runtime.slaves[axis_index].txpdo.actual_velocity,
        ),
        "derived_velocity": axis_motion_drive_to_api(
            state,
            axis_index,
            state["derived_velocities"][axis_index],
        ),
        "command_position": axis_position_drive_to_api(
            state,
            axis_index,
            runtime.trajectory_generators[axis_index].command_position,
        ),
        "command_velocity": axis_motion_drive_to_api(
            state,
            axis_index,
            runtime.trajectory_generators[axis_index].command_velocity,
        ),
        "statusword": int(runtime.slaves[axis_index].txpdo.statusword),
        "mode_display": int(
            runtime.slaves[axis_index].txpdo.mode_of_operation_display,
        ),
        "motion_mode": state["motion_modes"][axis_index],
        "server_mode": state.get("server_mode", "basic"),
        "position_counts_per_unit": state["position_counts_per_unit"],
        "axis_position_counts_per_unit": axis_list_value(
            axis_position_counts_per_unit,
            axis_index,
            state["position_counts_per_unit"],
        ),
        "motion_limits": motion_limits_drive_to_api(
            state,
            axis_index,
            state["motion_limits"][axis_index],
        ),
        "profile_settings": profile_settings_drive_to_api(
            state,
            axis_index,
            state["profile_settings"][axis_index],
        ),
        "software_position_limits": [
            axis_position_drive_to_api(state, axis_index, value)
            for value in state["software_position_limits"][axis_index]
        ],
        "axis_metadata": axis_list_value(axis_metadata, axis_index, {}),
        "user_position_unit": axis_list_value(
            user_position_units,
            axis_index,
            None,
        ),
        "converting_unit_exponents": axis_list_value(
            converting_unit_exponents,
            axis_index,
            None,
        ),
        "trajectory": public_axis_trajectory_state(state, axis_index),
        "homing": public_axis_homing_state(state, axis_index),
        "diagnostics": (
            runtime.last_diagnostics[axis_index]
            if axis_index < len(runtime.last_diagnostics)
            else {}
        ),
        "capabilities": state["capabilities"],
        "command_authority": {
            "owner": owner,
            "owned_by_this_client": owner is not None and owner == client_id,
            "available": owner is None,
        },
    }


def axis_list_value(values, axis_index, default=None):
    return values[axis_index] if axis_index < len(values) else default


def system_feedback_message(runtime, state, client_id=None):
    return {
        "type": "system/feedback",
        "target_positions": [
            axis_position_drive_to_api(state, axis_index, value)
            for axis_index, value in enumerate(state["target_positions"])
        ],
        "actual_positions": [
            axis_position_drive_to_api(state, axis_index, slave.txpdo.actual_position)
            for axis_index, slave in enumerate(runtime.slaves)
        ],
        "actual_velocities": [
            axis_motion_drive_to_api(state, axis_index, slave.txpdo.actual_velocity)
            for axis_index, slave in enumerate(runtime.slaves)
        ],
        "statuswords": [
            int(slave.txpdo.statusword)
            for slave in runtime.slaves
        ],
        "mode_displays": [
            int(slave.txpdo.mode_of_operation_display)
            for slave in runtime.slaves
        ],
        "command_authority": {
            "owner": state.get("command_authority_owner"),
            "owned_by_this_client": (
                state.get("command_authority_owner") is not None
                and state.get("command_authority_owner") == client_id
            ),
            "available": state.get("command_authority_owner") is None,
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


def public_axis_trajectory_state(state, axis_index):
    trajectory = dict(public_trajectory_state(state))
    axes = list(trajectory.get("axes", []))
    axis_index = int(axis_index)
    active_for_axis = bool(trajectory.get("active", False) and axis_index in axes)
    trajectory["axis"] = axis_index
    trajectory["active"] = active_for_axis

    if axis_index not in axes:
        trajectory["points"] = []
        return trajectory

    local_index = axes.index(axis_index)
    points = []
    for point in trajectory.get("points", []) or []:
        axis_point = dict(point)
        positions = list(point.get("positions", []))
        axis_point["position"] = (
            positions[local_index]
            if local_index < len(positions)
            else None
        )
        axis_point.pop("positions", None)
        points.append(axis_point)
    trajectory["points"] = points
    return trajectory


def public_homing_state(state):
    homing = dict(state["homing"])
    homing.pop("original_motion_modes", None)
    homing.pop("initial_referenced", None)
    homing.pop("referenced_seen_low", None)
    return homing


def public_axis_homing_state(state, axis_index):
    homing = dict(public_homing_state(state))
    axes = list(homing.get("axes", []))
    axis_index = int(axis_index)
    homing["axis"] = axis_index
    homing["active"] = bool(homing.get("active", False) and axis_index in axes)

    per_axis = {}
    for axis_state in homing.get("per_axis", []) or []:
        if int(axis_state.get("axis", -1)) == axis_index:
            per_axis = dict(axis_state)
            break
    homing["per_axis"] = per_axis
    return homing
