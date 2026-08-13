from motion_server.api import public_command_name, reject_command_message, send_client_message
from motion_server.api.selection import selected_io_device
from motion_server.api.serializers import io_device_snapshot


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


def output_write(message, runtime, state, client):
    command = public_command_name(message)
    try:
        device = selected_io_device(
            runtime,
            io_id=message.get("io", message.get("id")),
            slave_index=message.get("slave_index"),
        )
        apply_output_write(device["slave"].rxpdo, message)
    except Exception as exc:
        reject_command_message(client, command, str(exc))
        return

    response = io_device_snapshot(
        device,
        include_raw=bool(message.get("raw", False)),
    )
    response["type"] = command
    response["accepted"] = True
    send_client_message(client, response)


def apply_output_write(rxpdo, message):
    slot = require_field(message, "slot")
    kind = str(message.get("kind", message.get("output_type", ""))).strip().lower()
    if kind in {"do", "digital", "digital_output"}:
        channel = require_field(message, "channel")
        value = require_field(message, "value")
        rxpdo.set_module_digital_output(slot, channel, parse_bool(value))
        return

    if kind in {"ao", "analog", "analog_output"}:
        channel = require_field(message, "channel")
        value = require_field(message, "value")
        rxpdo.set_module_analog_output(slot, channel, int(value))
        return

    if kind in {"iol", "io_link", "iolink"}:
        payload = message.get("payload", message.get("data", ""))
        rxpdo.set_io_link_output(slot, parse_output_payload(payload))
        return

    raise ValueError(
        "system/io/output_write requires kind=digital, analog, or io_link"
    )


def require_field(message, field):
    if field not in message:
        raise ValueError(f"system/io/output_write requires {field}")
    return message[field]


def parse_output_payload(payload):
    if isinstance(payload, str):
        value = payload.strip()
        if value.startswith("0x"):
            value = value[2:]
        if value == "":
            return b""
        return bytes.fromhex(value)
    return bytes(int(item) & 0xFF for item in payload)


def parse_bool(value):
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "on", "yes"}:
            return True
        if normalized in {"0", "false", "off", "no"}:
            return False
        raise ValueError(f"Invalid boolean value: {value!r}")
    return bool(value)
