from motion_server.api.specification import authority_message_types
from motion_server.config import status_log
from motion_server.failure import AuthorityBusyException, AuthorityRequiredException
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
        status_log(f"Command authority granted to client {client['id']}")
        return _authority_data(payload)

    status_log(
        f"Command authority denied to client {client['id']}; owner={owner}",
    )
    raise AuthorityBusyException(owner)


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

    if owner != client["id"]:
        if owner is None:
            raise AuthorityRequiredException()
        raise AuthorityBusyException(owner)
    return {
        "granted": False,
        "owner": None,
        "owned_by_this_client": False,
        "available": True,
        "message": message,
    }


AUTHORITY_HANDLERS = {
    "system/authority/request": acquire_authority,
    "system/authority/release": release_authority,
    "system/authority/status": (
        lambda client, state: _authority_data(authority_status_payload(client, state))
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
        from motion_server.failure import UnknownCommandException
        raise UnknownCommandException(message_type)
    return handler(client, state)


def _authority_data(payload):
    data = dict(payload)
    data.pop("type", None)
    data.pop("ok", None)
    if data.get("reason") is None:
        data.pop("reason", None)
    return data
