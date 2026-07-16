import json


def send_client_message(client, message):
    client["conn"].sendall((json.dumps(message) + "\n").encode("utf-8"))


def command_name(message):
    return str(message.get("cmd", message.get("type", ""))).strip()


def public_command_name(message):
    return command_name(message)


def reject_command_message(client, command, message):
    send_client_message(
        client,
        {
            "type": "command_rejected",
            "command": command,
            "message": message,
        },
    )
