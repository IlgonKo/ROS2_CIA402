from device.virtual_cpx_ap_i_ec import VirtualCpxApDevice
from ethercat.mock_master import MockMaster
from motion_server.failure import (
    InvalidArgumentException,
    InvalidRequestException,
    ResourceNotFoundException,
    UnsupportedOperationException,
)


def write_input(message, runtime, state, client):
    io_id = required_io_id(message)
    slot = request_int(message, "slot", required=True)
    kind = str(message.get("kind", "")).strip().lower()
    if kind not in {"digital", "analog", "io_link"}:
        raise InvalidArgumentException(
            "kind",
            "must be digital, analog, or io_link",
        )
    device = selected_virtual_cpx(runtime, state, io_id)
    require_module(device, slot)
    try:
        if kind == "digital":
            channel = request_int(message, "channel", required=True)
            value = message.get("value")
            if not isinstance(value, bool):
                raise InvalidArgumentException(
                    "value",
                    "must be a JSON boolean for digital input",
                )
            device.set_digital_input(slot, channel, value)
        elif kind == "analog":
            channel = request_int(message, "channel", required=True)
            value = message.get("value")
            if isinstance(value, bool) or not isinstance(value, int):
                raise InvalidArgumentException(
                    "value",
                    "must be an integer for analog input",
                )
            device.set_analog_input(slot, channel, value)
        else:
            if "payload" not in message:
                raise InvalidRequestException("payload is required")
            device.set_io_link_input(slot, parse_raw_payload(message["payload"]))
    except InvalidArgumentException:
        raise
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentException(
            "input",
            "is invalid for the selected virtual I/O target",
        ) from exc
    return simulation_snapshot(runtime, state, io_id=io_id)


def read_inputs(message, runtime, state, client):
    io_id = optional_io_id(message)
    return simulation_snapshot(runtime, state, io_id=io_id)


def reset_inputs(message, runtime, state, client):
    io_id = required_io_id(message)
    slot = request_int(message, "slot", required=False)
    device = selected_virtual_cpx(runtime, state, io_id)
    if slot is not None:
        require_module(device, slot)
    device.reset_inputs(slot)
    return simulation_snapshot(runtime, state, io_id=io_id)


def simulation_snapshot(runtime, state, *, io_id=None):
    devices = virtual_cpx_devices(runtime, state)
    if io_id is not None:
        devices = [selected_device_record(devices, io_id)]
    return {
        "available": True,
        "backend": "mock",
        "devices": [
            {
                "id": record["id"],
                "slave_index": record["slave_index"],
                **record["virtual_device"].input_snapshot(),
            }
            for record in devices
        ],
    }


def selected_virtual_cpx(runtime, state, io_id):
    return selected_device_record(
        virtual_cpx_devices(runtime, state),
        io_id,
    )["virtual_device"]


def virtual_cpx_devices(runtime, state):
    require_simulation_available(runtime, state)
    devices = []
    for device in runtime.device_manager.io.devices:
        virtual_device = runtime.ethercat_master.virtual_device(
            device["slave_index"]
        )
        if isinstance(virtual_device, VirtualCpxApDevice):
            devices.append({
                "id": device["id"],
                "slave_index": device["slave_index"],
                "virtual_device": virtual_device,
            })
    return devices


def require_simulation_available(runtime, state):
    if not state.get("simulation_api_enabled", False):
        raise UnsupportedOperationException(
            "virtual_io_simulation",
            "simulation_api_disabled",
        )
    if not state.get("backend_is_mock", False) or not isinstance(
        runtime.ethercat_master,
        MockMaster,
    ):
        raise UnsupportedOperationException(
            "virtual_io_simulation",
            "mock_backend_required",
        )


def selected_device_record(devices, io_id):
    for device in devices:
        if str(device["id"]) == str(io_id):
            return device
    raise ResourceNotFoundException("virtual_io", io_id)


def require_module(device, slot):
    if int(slot) not in device.modules:
        raise ResourceNotFoundException("module", slot)


def required_io_id(message):
    io_id = optional_io_id(message)
    if io_id is None:
        raise InvalidRequestException("io is required")
    return io_id


def optional_io_id(message):
    if "io" not in message:
        return None
    io_id = str(message.get("io", "")).strip()
    if not io_id:
        raise InvalidArgumentException("io", "must not be empty")
    return io_id


def request_int(message, field, *, required):
    if field not in message:
        if required:
            raise InvalidRequestException(f"{field} is required")
        return None
    value = message[field]
    if isinstance(value, bool):
        raise InvalidArgumentException(field, "must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentException(field, "must be an integer") from exc
    if parsed < 0:
        raise InvalidArgumentException(field, "must be >= 0")
    return parsed


def parse_raw_payload(value):
    if isinstance(value, str):
        text = value.strip()
        if text.lower().startswith("0x"):
            text = text[2:]
        try:
            return bytes.fromhex(text)
        except ValueError as exc:
            raise InvalidArgumentException(
                "payload",
                "must be hexadecimal bytes",
            ) from exc
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if not isinstance(value, (list, tuple)):
        raise InvalidArgumentException(
            "payload",
            "must be hexadecimal text or a byte list",
        )
    payload = bytearray()
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 255:
            raise InvalidArgumentException(
                "payload",
                "byte list values must be integers in 0..255",
            )
        payload.append(item)
    return bytes(payload)
