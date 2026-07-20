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


def public_homing_state(state):
    homing = dict(state["homing"])
    homing.pop("original_motion_modes", None)
    homing.pop("initial_referenced", None)
    homing.pop("referenced_seen_low", None)
    return homing
