from motion_server.api import require_int32


def axis_metadata(state, axis_index):
    metadata = state.get("axis_metadata", [])
    if axis_index < len(metadata) and isinstance(metadata[axis_index], dict):
        return metadata[axis_index]
    return {}


def axis_position_counts_per_api_unit(state, axis_index):
    return state["axis_devices"].position_counts_per_api_unit(axis_index)


def axis_position_counts_per_api_units(state, axis_count_value):
    return [
        axis_position_counts_per_api_unit(state, axis_index)
        for axis_index in range(axis_count_value)
    ]


def axis_position_drive_to_api(state, axis_index, value):
    return state["axis_devices"].position_drive_to_api(axis_index, value)


def axis_position_api_to_drive(state, axis_index, value):
    return state["axis_devices"].position_api_to_drive(axis_index, value)


def axis_motion_drive_to_api(state, axis_index, value, kind="velocity"):
    return state["axis_devices"].motion_drive_to_api(axis_index, value, kind)


def axis_motion_api_to_drive(state, axis_index, value, kind="velocity"):
    return state["axis_devices"].motion_api_to_drive(axis_index, value, kind)


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
            require_int32(
                axis_position_api_to_drive(state, axis_index, position),
                f"axis {axis_index} target_position",
            )
            for axis_index, position in zip(axes, point.get("positions", []))
        ]
        points.append(converted_point)
    converted["points"] = points
    return converted
