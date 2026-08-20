from motion_server.api import public_command_name, send_client_message


def request_bus_reconnect(message, runtime, state, client):
    command = public_command_name(message)
    state["bus_reconnect_requested"] = True
    send_client_message(
        client,
        {
            "type": command,
            "accepted": True,
            "message": (
                "EtherCAT bus reconnect accepted. "
                "Runtime will be reinitialized with the current configuration."
            ),
        },
    )
