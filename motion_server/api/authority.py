from motion_server.api.messages import command_name, send_client_message
from motion_server.config import status_log


def authority_status_payload(client, state, message_type="authority/status"):
    owner = state.get("command_authority_owner")
    owned_by_this_client = owner is not None and owner == client["id"]
    return {
        "type": message_type,
        "ok": True,
        "owner": owner,
        "owned_by_this_client": owned_by_this_client,
        "available": owner is None,
        "reason": None,
    }


def acquire_authority(client, state):
    owner = state.get("command_authority_owner")
    if owner is None or owner == client["id"]:
        state["command_authority_owner"] = client["id"]
        payload = authority_status_payload(client, state, "authority/acquire")
        payload["granted"] = True
        payload["message"] = (
            "Command authority granted."
            if owner is None
            else "This connection already owns command authority."
        )
        send_client_message(client, payload)
        status_log(f"Command authority granted to client {client['id']}")
        return

    send_client_message(
        client,
        {
            "type": "authority/acquire",
            "ok": False,
            "granted": False,
            "reason": "authority_busy",
            "owner": owner,
            "owned_by_this_client": False,
            "available": False,
            "message": f"Command authority is already held by client {owner}.",
        },
    )
    status_log(
        f"Command authority denied to client {client['id']}; owner={owner}",
    )


def release_authority(client, state):
    owner = state.get("command_authority_owner")
    if owner == client["id"]:
        state["command_authority_owner"] = None
        reason = None
        message = "Command authority released."
        status_log(f"Command authority released by client {client['id']}")
    elif owner is None:
        reason = "authority_required"
        message = "This connection does not hold command authority."
    else:
        reason = "authority_busy"
        message = "This client does not hold command authority."

    send_client_message(
        client,
        {
            "type": "authority/release",
            "ok": owner == client["id"],
            "granted": False,
            "reason": reason,
            "owner": state.get("command_authority_owner"),
            "owned_by_this_client": False,
            "available": state.get("command_authority_owner") is None,
            "message": message,
        },
    )


def client_has_command_authority(client, state):
    return state.get("command_authority_owner") == client["id"]


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
