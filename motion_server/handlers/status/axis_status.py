from motion_server.api.encoder import (
    axis_list_value,
    public_axis_homing_state,
    public_axis_trajectory_state,
    public_homing_state,
    public_trajectory_state,
    motion_limits_api_values,
    profile_settings_api_values,
    software_position_limits_api_values,
)
from motion_server.control.axis_units import (
    axis_motion_drive_to_api,
    axis_position_drive_to_api,
    motion_limits_drive_to_api,
    profile_settings_drive_to_api,
)
from motion_server.diagnostic.models import (
    DiagnosticSource,
    DiagnosticSourceType,
)
from motion_server.diagnostic.serialization import diagnostic_status_snapshot


def axis_status_message(runtime, state, axis_index, client_id=None):
    axis_index = int(axis_index)
    owner = state.get("command_authority_owner")
    parameters = runtime.axis_parameters
    user_position_units = parameters.user_position_units
    converting_unit_exponents = parameters.converting_unit_exponents
    axis_position_counts_per_unit = state.get(
        "axis_position_counts_per_unit",
        [],
    )
    axis_metadata = parameters.axis_metadata
    return {
        "type": "system/axis/status",
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
            parameters.motion_limits[axis_index],
        ),
        "profile_settings": profile_settings_drive_to_api(
            state,
            axis_index,
            parameters.profile_settings[axis_index],
        ),
        "software_position_limits": [
            axis_position_drive_to_api(state, axis_index, value)
            for value in parameters.software_position_limits[axis_index]
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
        "device_diagnostics": (
            runtime.last_diagnostics[axis_index]
            if axis_index < len(runtime.last_diagnostics)
            else {}
        ),
        "diagnostic_status": diagnostic_status_snapshot(
            runtime,
            source=DiagnosticSource(DiagnosticSourceType.AXIS, axis_index),
        ),
        "capabilities": state["capabilities"],
        "command_authority": {
            "owner": owner,
            "owned_by_this_client": owner is not None and owner == client_id,
            "available": owner is None,
        },
    }


def axes_status_message(runtime, state, client_id=None):
    owner = state.get("command_authority_owner")
    return {
        "type": "system/axes/status",
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
        "motion_limits": motion_limits_api_values(runtime.axis_parameters.motion_limits, state),
        "profile_settings": profile_settings_api_values(
            runtime.axis_parameters.profile_settings,
            state,
        ),
        "software_position_limits": software_position_limits_api_values(
            runtime.axis_parameters.software_position_limits,
            state,
        ),
        "axis_metadata": runtime.axis_parameters.axis_metadata,
        "user_position_units": runtime.axis_parameters.user_position_units,
        "converting_unit_exponents": runtime.axis_parameters.converting_unit_exponents,
        "motion_mode": state["motion_mode"],
        "motion_modes": state["motion_modes"],
        "server_mode": state.get("server_mode", "basic"),
        "position_counts_per_unit": state["position_counts_per_unit"],
        "axis_position_counts_per_unit": state.get(
            "axis_position_counts_per_unit",
            [],
        ),
        "capabilities": state["capabilities"],
        "trajectory": public_trajectory_state(state),
        "homing": public_homing_state(state),
        "device_diagnostics": runtime.last_diagnostics,
        "diagnostic_status": diagnostic_status_snapshot(
            runtime,
            source_type=DiagnosticSourceType.AXIS,
        ),
        "command_authority": {
            "owner": owner,
            "owned_by_this_client": owner is not None and owner == client_id,
            "available": owner is None,
        },
    }
