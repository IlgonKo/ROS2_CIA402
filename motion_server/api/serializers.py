from motion_server.control.axis_units import (
    axis_position_drive_to_api,
    motion_limits_drive_to_api,
    profile_settings_drive_to_api,
)


def axis_list_value(values, axis_index, default=None):
    return values[axis_index] if axis_index < len(values) else default


def motion_limits_api_values(motion_limits, state=None):
    return [
        float(
            motion_limits_drive_to_api(state, axis_index, axis_limits)[field_index]
            if state is not None
            else value
        )
        for axis_index, axis_limits in enumerate(motion_limits)
        for field_index, value in enumerate(axis_limits)
    ]


def profile_settings_api_values(profile_settings, state=None):
    return [
        float(
            profile_settings_drive_to_api(state, axis_index, axis_settings)[field_index]
            if state is not None
            else value
        )
        for axis_index, axis_settings in enumerate(profile_settings)
        for field_index, value in enumerate(axis_settings)
    ]


def software_position_limits_api_values(software_position_limits, state=None):
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
