from motion_server.api.serializers import (
    axis_list_value,
    public_axis_homing_state,
    public_axis_trajectory_state,
    public_homing_state,
    public_trajectory_state,
    io_device_snapshot,
    motion_limits_api_values,
    profile_settings_api_values,
    software_position_limits_api_values,
)
from motion_server.api.selection import io_devices
from motion_server.control.axis_units import (
    axis_motion_drive_to_api,
    axis_position_drive_to_api,
    motion_limits_drive_to_api,
    profile_settings_drive_to_api,
)


def system_feedback_message(runtime, state, client_id=None):
    message = {
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
    devices = io_devices(runtime)
    if devices:
        message["io"] = {
            "devices": [
                io_device_snapshot(device, include_raw=False)
                for device in devices
            ],
        }
    return message


def server_status_message(runtime, state):
    return {
        "type": "system/server/status",
        "ok": True,
        "server_mode": state.get("server_mode", "basic"),
        "drive_initialized": bool(state.get("drive_initialized", True)),
        "initialization_error": state.get("initialization_error", ""),
        "axis_count": len(runtime.slaves),
        "cycle_time": float(runtime.cycle_time),
        "feedback_type": "system/feedback",
    }


def bus_status_message(runtime, state):
    expected_wkc = runtime.expected_wkc()
    actual_wkc = int(getattr(runtime, "wkc", 0))
    return {
        "type": "system/bus/status",
        "ok": True,
        "drive_initialized": bool(state.get("drive_initialized", True)),
        "initialization_error": state.get("initialization_error", ""),
        "device_count": len(runtime.ethercat_devices),
        "axis_count": len(runtime.slaves),
        "wkc": actual_wkc,
        "expected_wkc": expected_wkc,
        "wkc_ok": actual_wkc == expected_wkc,
        "statuswords": [
            int(slave.txpdo.statusword)
            for slave in runtime.slaves
        ],
        "mode_displays": [
            int(slave.txpdo.mode_of_operation_display)
            for slave in runtime.slaves
        ],
    }


def io_status_message(runtime, state, include_raw=False):
    return {
        "type": "system/io/status",
        "ok": True,
        "drive_initialized": bool(state.get("drive_initialized", True)),
        "initialization_error": state.get("initialization_error", ""),
        "io_count": len(io_devices(runtime)),
        "devices": [
            io_device_snapshot(device, include_raw=include_raw)
            for device in io_devices(runtime)
        ],
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
        "motion_limits": motion_limits_api_values(state["motion_limits"], state),
        "profile_settings": profile_settings_api_values(
            state["profile_settings"],
            state,
        ),
        "software_position_limits": software_position_limits_api_values(
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
