from motion_server.api import public_command_name, reject_command_message, send_client_message
from motion_server.api.decoder import selected_io_device
from motion_server.api.encoder import io_device_snapshot


def input_read(message, runtime, state, client):
    command = public_command_name(message)
    try:
        device = selected_io_device(
            runtime,
            io_id=message.get("io", message.get("id")),
            slave_index=message.get("slave_index"),
        )
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return

    response = io_device_snapshot(
        device,
        include_raw=bool(message.get("raw", False)),
    )
    response["type"] = command
    send_client_message(client, response)
