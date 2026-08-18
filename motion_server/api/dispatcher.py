import json

from motion_server.commands.parameters import read_io_parameter, read_parameter
from motion_server.commands.routes import COMMAND_ROUTER
from motion_server.config import AXIS_SERVER_COMMAND_LOGS
from motion_server.api.responses import (
    axis_status_message,
    bus_status_message,
    axes_status_message,
    io_status_message,
    server_status_message,
)
from motion_server.api import (
    command_name,
    public_command_name,
    reject_command_message,
    send_client_message,
    selected_single_axis,
)
from motion_server.api.authority import (
    acquire_authority,
    authority_status_payload,
    client_has_command_authority,
    reject_command_when_not_initialized,
    reject_command_without_authority,
    release_authority,
)
from motion_server.app.state import inactive_trajectory_state


COMMAND_MESSAGE_TYPES = {
    "system/server/reset",
    "system/server/restart",
    "system/bus/reconnect",
    "system/bus/rescan",
    "system/axis/enable",
    "system/axis/disable",
    "system/axis/reset",
    "system/axis/restart",
    "system/axis/home",
    "system/axis/stop",
    "system/axis/move_abs",
    "system/axis/move_rel",
    "system/axis/move_vel",
    "system/axis/jog_start",
    "system/axis/jog_stop",
    "system/axis/profile",
    "system/axis/motion_limits",
    "system/axis/software_position_limits",
    "system/axis/mode",
    "system/axis/manualCW",
    "system/axis/param_write",
    "system/axis/param_save",
    "system/axes/enable",
    "system/axes/disable",
    "system/axes/reset",
    "system/axes/stop",
    "system/axes/move_abs",
    "system/axes/move_rel",
    "system/axes/move_vel",
    "system/axes/trajectory",
    "system/axes/trajectory_stop",
    "system/io/output_write",
    "system/io/reset",
    "system/io/restart",
    "system/io/param_write",
    "system/io/param_save",
    "system/io/ap/param_write",
    "system/io/iolink/isdu_write",
}

AUTHORITY_MESSAGE_TYPES = {
    "system/authority/request",
    "system/authority/release",
    "system/authority/status",
}

ADVANCED_MESSAGE_TYPES = {
    "system/axis/manualCW",
    "system/axes/trajectory",
    "system/axes/trajectory_stop",
}

ADVANCED_STATUS_MESSAGE_TYPES = set()

INITIALIZATION_ERROR_ALLOWED_COMMANDS = {
    "system/bus/reconnect",
    "system/server/reset",
    "system/server/restart",
}

STATUS_MESSAGE_TYPES = {
    "system/server/status",
    "system/bus/status",
    "system/axis/status",
    "system/axes/status",
    "system/io/status",
    "system/io/input_read",
    "system/io/ethercat/param_catalog",
    "system/io/iol/param_catalog",
    "system/io/ap/param_read",
    "system/io/iolink/isdu_read",
}


def is_advanced_mode(state):
    return state.get("server_mode") == "advanced"


def reject_advanced_only_command(client, message, state):
    command = command_name(message)
    send_client_message(
        client,
        {
            "type": "command_rejected",
            "command": command,
            "server_mode": state.get("server_mode"),
            "message": (
                f"{command} is available only in "
                "Axis Server advanced mode."
            ),
        },
    )


def dispatch_message(message, runtime, state, client):
    if AXIS_SERVER_COMMAND_LOGS:
        print(
            "Axis Server received command: "
            f"client={client.get('id')} "
            f"{json.dumps(message, sort_keys=True, ensure_ascii=False)}",
            flush=True,
        )

    raw_message_type = command_name(message)
    message_type = public_command_name(message)

    if message_type in AUTHORITY_MESSAGE_TYPES:
        if message_type == "system/authority/request":
            acquire_authority(client, state)
        elif message_type == "system/authority/release":
            release_authority(client, state)
        elif message_type == "system/authority/status":
            send_client_message(client, authority_status_payload(client, state))
        return

    if message_type == "system/server/status":
        send_client_message(client, server_status_message(runtime, state))
        return

    if message_type == "system/bus/status":
        send_client_message(client, bus_status_message(runtime, state))
        return

    if message_type == "system/axes/status":
        status = axes_status_message(runtime, state, client["id"])
        status["type"] = message_type
        send_client_message(client, status)
        return

    if message_type == "system/io/status":
        send_client_message(
            client,
            io_status_message(
                runtime,
                state,
                include_raw=bool(message.get("raw", False)),
            ),
        )
        return

    if message_type == "system/axis/status":
        if "axes" in message or "axis" not in message:
            reject_command_message(
                client,
                message_type,
                f"{message_type} requires axis and does not accept axes.",
            )
            return
        try:
            axis_index = selected_single_axis(message, runtime, message_type)
        except Exception as exc:
            reject_command_message(client, message_type, str(exc))
            return
        send_client_message(
            client,
            axis_status_message(runtime, state, axis_index, client["id"]),
        )
        return

    if (
        message_type in ADVANCED_STATUS_MESSAGE_TYPES
        and not is_advanced_mode(state)
    ):
        status = axes_status_message(runtime, state, client["id"])
        status["type"] = message_type
        status["trajectory"] = inactive_trajectory_state("advanced_only")
        status["trajectory"]["message"] = (
            f"{message_type} is available only in Axis Server advanced mode."
        )
        send_client_message(client, status)
        return

    if message_type == "system/axis/param_read":
        read_parameter(message, runtime, client)
        return

    if message_type == "system/io/param_read":
        read_io_parameter(message, runtime, client)
        return

    if message_type == "system/io/input_read":
        if COMMAND_ROUTER.dispatch(message_type, message, runtime, state, client):
            return

    if (
        message_type in ADVANCED_MESSAGE_TYPES
        and not is_advanced_mode(state)
    ):
        reject_advanced_only_command(client, message, state)
        return

    if (
        message_type in COMMAND_MESSAGE_TYPES and
        not client_has_command_authority(client, state)
    ):
        reject_command_without_authority(client, message, state)
        return

    if (
        message_type in COMMAND_MESSAGE_TYPES
        and not state.get("drive_initialized", True)
        and message_type not in INITIALIZATION_ERROR_ALLOWED_COMMANDS
    ):
        reject_command_when_not_initialized(client, message, state)
        return

    if COMMAND_ROUTER.dispatch(message_type, message, runtime, state, client):
        return
    if raw_message_type:
        reject_command_message(
            client,
            raw_message_type,
            f"Unknown command: {raw_message_type}",
        )
