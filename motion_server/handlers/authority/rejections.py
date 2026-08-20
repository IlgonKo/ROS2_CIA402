from motion_server.api.decoder import command_name
from motion_server.api.encoder import send_client_message


def reject_command_without_authority(client, message, state):
    owner = state.get("command_authority_owner")
    reason = "authority_required" if owner is None else "authority_busy"
    send_client_message(
        client,
        {
            "type": "command_rejected",
            "ok": False,
            "reason": reason,
            "command": command_name(message),
            "owner": owner,
            "available": owner is None,
            "owned_by_this_client": False,
            "message": (
                "Command authority is required."
                if owner is None
                else f"Command authority is held by client {owner}."
            ),
        },
    )


def reject_command_when_not_initialized(client, message, state):
    send_client_message(
        client,
        {
            "type": "command_rejected",
            "command": command_name(message),
            "message": (
                "Axis Server is running, but EtherCAT drive initialization "
                f"failed: {state.get('initialization_error', 'unknown error')}"
            ),
        },
    )
