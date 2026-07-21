import json

from motion_server.commands.parameters import read_parameter
from motion_server.commands.routes import COMMAND_ROUTER
from motion_server.config import AXIS_SERVER_COMMAND_LOGS
from motion_server.api.feedback import axis_status_message, feedback_message
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
    "system/stop",
    "system/reset",
    "axis/enable",
    "axis/disable",
    "axis/reset",
    "axis/home",
    "axis/stop",
    "axis/move_abs",
    "axis/move_rel",
    "axis/move_vel",
    "axis/jog_start",
    "axis/jog_stop",
    "axis/profile",
    "axis/motion_limits",
    "axis/software_position_limits",
    "axis/mode",
    "axis/param_write",
    "axis/param_save",
    "debug/controlword",
    "trajectory/move",
    "trajectory/stop",
}

AUTHORITY_MESSAGE_TYPES = {
    "authority/acquire",
    "authority/release",
    "authority/status",
}

ADVANCED_MESSAGE_TYPES = {
    "debug/controlword",
    "trajectory/move",
    "trajectory/stop",
}

ADVANCED_STATUS_MESSAGE_TYPES = {
    "trajectory/status",
}

STATUS_MESSAGE_TYPES = {
    "system/status",
    "axis/status",
    "trajectory/status",
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
        if message_type == "authority/acquire":
            acquire_authority(client, state)
        elif message_type == "authority/release":
            release_authority(client, state)
        elif message_type == "authority/status":
            send_client_message(client, authority_status_payload(client, state))
        return

    if message_type == "system/status":
        status = feedback_message(runtime, state, client["id"])
        status["type"] = message_type
        send_client_message(client, status)
        return

    if message_type == "axis/status":
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
        status = feedback_message(runtime, state, client["id"])
        status["type"] = message_type
        status["trajectory"] = inactive_trajectory_state("advanced_only")
        status["trajectory"]["message"] = (
            f"{message_type} is available only in Axis Server advanced mode."
        )
        send_client_message(client, status)
        return

    if message_type == "axis/param_read":
        read_parameter(message, runtime, client)
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
