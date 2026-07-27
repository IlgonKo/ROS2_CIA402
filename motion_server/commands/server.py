from motion_server.api import public_command_name, send_client_message


def request_server_reset(message, runtime, state, client):
    command = public_command_name(message)
    state["server_reset_requested"] = True
    send_client_message(
        client,
        {
            "type": command,
            "accepted": True,
            "message": (
                "Motion Server reset accepted. "
                "Runtime and EtherCAT bus will be reinitialized."
            ),
        },
    )


def request_server_restart(message, runtime, state, client):
    command = public_command_name(message)
    state["server_restart_requested"] = True
    send_client_message(
        client,
        {
            "type": command,
            "accepted": True,
            "message": "Motion Server restart accepted. Process will restart.",
        },
    )


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
