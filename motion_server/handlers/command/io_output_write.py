from motion_server.api import public_command_name, reject_command_message, send_client_message
from motion_server.api.decoder import selected_io_device
from motion_server.api.encoder import io_device_snapshot
from motion_server.failure import (
    DeviceAccessException,
    InvalidArgumentException,
    ItemFailure,
    MotionServerException,
    PartialFailure,
    ResourceNotFoundException,
)


def output_write(message, runtime, state, client):
    command = public_command_name(message)
    try:
        result = write_outputs(message, runtime)
    except MotionServerException as exc:
        reject_command_message(client, command, str(exc))
        return

    if isinstance(result, PartialFailure):
        reject_command_message(client, command, "I/O output command partially failed.")
        return result

    if isinstance(result, list):
        send_client_message(
            client,
            {"type": command, "accepted": True, "targets": result},
        )
        return result

    response = io_device_snapshot(
        result["device"],
        include_raw=bool(message.get("raw", False)),
    )
    response["type"] = command
    response["accepted"] = True
    send_client_message(client, response)
    return result


def write_outputs(message, runtime):
    writes = message.get("writes")
    if writes is None:
        request = dict(message)
        return write_output_target(request, runtime)
    if not isinstance(writes, list) or not writes:
        raise InvalidArgumentException("writes", "must be a non-empty list")

    requests = []
    for index, item in enumerate(writes):
        if not isinstance(item, dict):
            raise InvalidArgumentException(
                "writes",
                f"item {index} must be an object",
            )
        request = {
            key: value
            for key, value in message.items()
            if key not in {"writes", "request_id"}
        }
        request.update(item)
        requests.append(request)

    targets = [
        output_target(request, index)
        for index, request in enumerate(requests)
    ]
    succeeded = []
    failed = []
    for target, request in zip(targets, requests):
        try:
            write_output_target(request, runtime)
        except MotionServerException as exception:
            failed.append(ItemFailure(target, exception))
        else:
            succeeded.append(target)
    if not failed:
        return succeeded
    if not succeeded:
        raise failed[0].exception
    return PartialFailure(succeeded, failed)


def output_target(message, index=0):
    target = {
        "io": message.get("io", message.get("id")),
        "slot": message.get("slot"),
    }
    if "channel" in message:
        target["channel"] = message.get("channel")
    if target["io"] is None:
        target["io"] = index
    return target


def write_output_target(message, runtime):
    selector = message.get("io", message.get("id"))
    try:
        device = selected_io_device(
            runtime,
            io_id=selector,
            slave_index=message.get("slave_index"),
        )
    except (TypeError, ValueError) as exc:
        raise ResourceNotFoundException("io", selector) from exc
    try:
        apply_output_write(device["slave"].rxpdo, message)
    except InvalidArgumentException:
        raise
    except (AttributeError, OSError) as exc:
        raise DeviceAccessException("io_output_write") from exc
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentException(
            "output",
            "is invalid for the selected I/O target",
        ) from exc
    return {"target": output_target(message), "device": device}


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
        raise InvalidArgumentException(field, "is required")
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
        raise InvalidArgumentException("value", "must be boolean")
    return bool(value)
