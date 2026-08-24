from motion_server.control.axis_units import axis_position_counts_per_api_units


def inactive_trajectory_state(result="idle"):
    return {
        "active": False,
        "state": result,
        "axes": [],
        "segment": 0,
        "time_from_start": 0.0,
        "points": [],
        "start_time": None,
        "message": "",
    }


def inactive_homing_state(result="idle"):
    return {
        "active": False,
        "state": result,
        "axes": [],
        "start_time": None,
        "message": "",
        "per_axis": [],
    }


def initial_server_state(
    server_config,
    ethercat_config,
    motion_config,
    axis_count_value,
    axis_devices,
    positions,
    software_position_limits,
    profile_settings=None,
    motion_limits=None,
    user_position_units=None,
    converting_unit_exponents=None,
    axis_metadata=None,
    initialized=True,
    initialization_error="",
):
    limits = motion_config.default_limits
    if motion_limits is None:
        motion_limits = [
            [
                limits.max_velocity,
                -abs(limits.max_velocity),
                limits.acceleration,
                limits.deceleration,
            ]
            for _ in range(axis_count_value)
        ]
    if profile_settings is None:
        profile_settings = [
            [
                limits.max_velocity,
                limits.acceleration,
                limits.deceleration,
                limits.pp_jerk,
            ]
            for _ in range(axis_count_value)
        ]
    if user_position_units is None:
        user_position_units = [None for _ in range(axis_count_value)]
    if converting_unit_exponents is None:
        converting_unit_exponents = [None for _ in range(axis_count_value)]
    axis_devices.configure_unit_conversion(
        user_position_units,
        converting_unit_exponents,
    )
    if axis_metadata is None:
        axis_metadata = axis_devices.unit_metadata()
    axis_position_scales = axis_position_counts_per_api_units(
        {"axis_devices": axis_devices},
        axis_count_value,
    )
    return {
        "axis_devices": axis_devices,
        "drive_initialized": bool(initialized),
        "initialization_error": initialization_error,
        "server_mode": server_config.mode.value,
        "target_positions": positions,
        "derived_velocities": [0.0 for _ in range(axis_count_value)],
        "derived_velocity_positions": positions,
        "derived_velocity_time": None,
        "derived_velocity_alpha": max(
            0.0,
            min(1.0, 0.2),
        ),
        "motion_limits": motion_limits,
        "profile_settings": profile_settings,
        "software_position_limits": software_position_limits,
        "axis_metadata": axis_metadata,
        "user_position_units": user_position_units,
        "converting_unit_exponents": converting_unit_exponents,
        "motion_mode": motion_config.initial_motion_mode,
        "motion_modes": [
            motion_config.initial_motion_mode
            for _ in range(axis_count_value)
        ],
        "position_counts_per_unit": (
            axis_position_scales[0] if axis_position_scales else 1.0
        ),
        "axis_position_counts_per_unit": axis_position_scales,
        "capabilities": {
            "position_loop_gain": ethercat_config.backend.value == "mock",
            "profile_settings": True,
            "motion_limits": True,
            "software_position_limits": True,
            "csp_trajectory_feedback": server_config.mode.value == "advanced",
            "trajectory_commands": server_config.mode.value == "advanced",
        },
        "trajectory": inactive_trajectory_state(),
        "trajectory_sequence": 0,
        "last_trajectory_complete_time": None,
        "homing": inactive_homing_state(),
        "jog_previous_modes": [None for _ in range(axis_count_value)],
        "command_authority_owner": None,
        "spin_wait_time": ethercat_config.cycle.spin_wait_time,
        "dc_phase_lock": ethercat_config.dc.phase_lock,
        "dc_absolute_shift": ethercat_config.dc.absolute_shift,
        "dc_phase_offset_ns": ethercat_config.dc.phase_offset_ns,
        "dc_phase_kp": ethercat_config.dc.phase_kp,
        "dc_phase_ki": ethercat_config.dc.phase_ki,
        "dc_phase_max_correction": ethercat_config.dc.phase_max_correction,
    }
