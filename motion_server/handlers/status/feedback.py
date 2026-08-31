from motion_server.api.decoder import io_devices
from motion_server.api.encoder import io_device_snapshot
from motion_server.control.axis_units import (
    axis_motion_drive_to_api,
    axis_position_drive_to_api,
)
from motion_server.handlers.status.server_health import (
    process_data_is_valid,
    server_health_snapshot,
)


def system_feedback_message(runtime, state, client_id=None):
    message = {
        "type": "system/feedback",
        "process_data_valid": process_data_is_valid(state),
        "server_health": server_health_snapshot(state),
        "target_positions": [
            axis_position_drive_to_api(state, axis_index, value)
            for axis_index, value in enumerate(state.get("target_positions", []))
        ],
        "actual_positions": [
            axis_position_drive_to_api(state, axis_index, slave.txpdo.actual_position)
            for axis_index, slave in enumerate(_slaves(runtime))
        ],
        "actual_velocities": [
            axis_motion_drive_to_api(state, axis_index, slave.txpdo.actual_velocity)
            for axis_index, slave in enumerate(_slaves(runtime))
        ],
        "statuswords": [
            int(slave.txpdo.statusword)
            for slave in _slaves(runtime)
        ],
        "mode_displays": [
            int(slave.txpdo.mode_of_operation_display)
            for slave in _slaves(runtime)
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
    devices = [] if runtime is None else io_devices(runtime)
    if devices:
        message["io"] = {
            "devices": [
                io_device_snapshot(
                    device, include_raw=False,
                    process_data_valid=message["process_data_valid"],
                )
                for device in devices
            ],
        }
    return message


def _slaves(runtime):
    return () if runtime is None else runtime.slaves
