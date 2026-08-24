def authority_status_payload(client, state, message_type="system/authority/status"):
    owner = state.get("command_authority_owner")
    owned_by_this_client = owner is not None and owner == client["id"]
    return {
        "type": message_type,
        "owner": owner,
        "owned_by_this_client": owned_by_this_client,
        "available": owner is None,
    }


def client_has_command_authority(client, state):
    return state.get("command_authority_owner") == client["id"]
