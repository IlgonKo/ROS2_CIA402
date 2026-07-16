from collections import deque

from motion_server.control.axis_units import axis_position_counts_per_api_units
from motion_server.config import TX_HISTORY_LENGTH


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
    args,
    drive_manager,
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
    if motion_limits is None:
        motion_limits = [
            [
                args.max_velocity,
                -abs(args.max_velocity),
                args.acceleration,
                args.deceleration,
            ]
            for _ in range(args.axis_count)
        ]
    if profile_settings is None:
        profile_settings = [
            [
                args.max_velocity,
                args.acceleration,
                args.deceleration,
                args.pp_jerk,
            ]
            for _ in range(args.axis_count)
        ]
    if user_position_units is None:
        user_position_units = [None for _ in range(args.axis_count)]
    if converting_unit_exponents is None:
        converting_unit_exponents = [None for _ in range(args.axis_count)]
    drive_manager.configure_unit_conversion(
        user_position_units,
        converting_unit_exponents,
        args.csp_counts_per_unit,
    )
    if axis_metadata is None:
        axis_metadata = drive_manager.unit_metadata()
    return {
        "drive_manager": drive_manager,
        "drive_initialized": bool(initialized),
        "initialization_error": initialization_error,
        "server_mode": args.server_mode,
        "target_positions": positions,
        "derived_velocities": [0.0 for _ in range(args.axis_count)],
        "derived_velocity_positions": positions,
        "derived_velocity_time": None,
        "derived_velocity_alpha": max(
            0.0,
            min(1.0, args.derived_velocity_alpha),
        ),
        "motion_limits": motion_limits,
        "profile_settings": profile_settings,
        "software_position_limits": software_position_limits,
        "axis_metadata": axis_metadata,
        "user_position_units": user_position_units,
        "converting_unit_exponents": converting_unit_exponents,
        "motion_mode": args.motion_mode,
        "motion_modes": [
            args.motion_mode
            for _ in range(args.axis_count)
        ],
        "position_counts_per_unit": (
            args.csp_counts_per_unit
        ),
        "axis_position_counts_per_unit": axis_position_counts_per_api_units(
            {"drive_manager": drive_manager},
            args.axis_count,
        ),
        "capabilities": {
            "position_loop_gain": args.backend == "mock",
            "profile_settings": True,
            "motion_limits": True,
            "software_position_limits": True,
            "csp_trajectory_feedback": args.server_mode == "advanced",
            "trajectory_commands": args.server_mode == "advanced",
        },
        "trajectory": inactive_trajectory_state(),
        "trajectory_sequence": 0,
        "last_trajectory_complete_time": None,
        "tx_history": deque(maxlen=max(1, TX_HISTORY_LENGTH)),
        "homing": inactive_homing_state(),
        "jog_previous_modes": [None for _ in range(args.axis_count)],
        "command_authority_owner": None,
        "spin_wait_time": max(0.0, args.spin_wait_time),
        "dc_phase_lock": args.dc_phase_lock,
        "dc_absolute_shift": args.dc_absolute_shift,
        "dc_phase_offset_ns": args.dc_phase_offset,
        "dc_phase_kp": args.dc_phase_kp,
        "dc_phase_ki": args.dc_phase_ki,
        "dc_phase_max_correction": args.dc_phase_max_correction,
    }
