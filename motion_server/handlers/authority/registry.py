from motion_server.api.encoder import send_client_message
from motion_server.api.specification import authority_message_types
from motion_server.config import status_log
from motion_server.handlers.authority.status import authority_status_payload


def acquire_authority(client, state):
    owner = state.get("command_authority_owner")
    if owner is None or owner == client["id"]:
        state["command_authority_owner"] = client["id"]
        payload = authority_status_payload(client, state, "system/authority/request")
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
            "type": "system/authority/request",
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
            "type": "system/authority/release",
            "ok": owner == client["id"],
            "granted": False,
            "reason": reason,
            "owner": state.get("command_authority_owner"),
            "owned_by_this_client": False,
            "available": state.get("command_authority_owner") is None,
            "message": message,
        },
    )


AUTHORITY_HANDLERS = {
    "system/authority/request": acquire_authority,
    "system/authority/release": release_authority,
    "system/authority/status": (
        lambda client, state: send_client_message(
            client,
            authority_status_payload(client, state),
        )
    ),
}


def validate_authority_registry():
    handler_names = set(AUTHORITY_HANDLERS)
    expected_names = authority_message_types()
    missing = sorted(expected_names - handler_names)
    unknown = sorted(handler_names - expected_names)
    if missing or unknown:
        raise RuntimeError(
            "Motion Server authority registry/specification mismatch. "
            f"missing={missing} unknown={unknown}"
        )


validate_authority_registry()


def handle_authority(message_type, client, state):
    handler = AUTHORITY_HANDLERS.get(message_type)
    if handler is None:
        return False
    handler(client, state)
    return True
