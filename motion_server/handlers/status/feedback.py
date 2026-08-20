from motion_server.api.decoder import io_devices
from motion_server.api.encoder import io_device_snapshot
from motion_server.control.axis_units import (
    axis_motion_drive_to_api,
    axis_position_drive_to_api,
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
