import struct
import time

from motion_server.api import (
    command_name,
    parse_int,
    public_command_name,
    send_client_message,
)


ISDU_ACCESS_BASE_INDEX = 0x2001
ISDU_ACCESS_INDEX_STEP = 0x10
ISDU_DIRECTION_READ = 0
ISDU_DIRECTION_WRITE = 1
ISDU_MAX_DATA_BYTES = 238
ISDU_STATUS_BUSY = 0xFFFF
ISDU_STATUS_POLL_TIMEOUT = 1.0
ISDU_STATUS_POLL_PERIOD = 0.02

ISDU_DATA_FORMATS = {
    "int8": "<b",
    "uint8": "<B",
    "uint16": "<H",
    "int16": "<h",
    "int32": "<i",
    "uint32": "<I",
    "udint": "<I",
    "float32": "<f",
}


def read_isdu(message, runtime, client):
    response_type = command_name(message) or "system/io/iolink/isdu_read"
    try:
        request = parse_isdu_request(message, require_value=False)
        validate_isdu_request_against_iodd(runtime, request, access="read")
        slave_index = runtime.device_manager.io.slave_index(request["io"])
        write_isdu_header(
            runtime,
            slave_index,
            request,
            direction=ISDU_DIRECTION_READ,
            write_length=False,
        )
        status = poll_isdu_status(runtime, slave_index, request)
        require_isdu_success(status, request)
        data_length = isdu_sdo_step(
            "read data length",
            request,
            runtime.ethercat_master.sdo.read_uint8,
            slave_index,
            request["object_index"],
            6,
        )
        read_length = min(
            request["length"],
            max(0, int(data_length)),
            ISDU_MAX_DATA_BYTES,
        )
        payload = read_isdu_data_payload(
            runtime,
            slave_index,
            request,
            read_length,
        )
        value = decode_isdu_payload(payload, request["data_type"])
    except Exception as exc:
        send_client_message(
            client,
            isdu_error_response(response_type, message, exc),
        )
        return

    response = isdu_response(response_type, request)
    response.update({
        "ok": True,
        "status": status,
        "length": data_length,
        "data": bytes(payload).hex(),
        "value": value,
    })
    send_client_message(client, response)


def write_isdu(message, runtime, client):
    response_type = public_command_name(message)
    try:
        request = parse_isdu_request(message, require_value=True)
        validate_isdu_request_against_iodd(runtime, request, access="write")
        slave_index = runtime.device_manager.io.slave_index(request["io"])
        payload = encode_isdu_payload(message["value"], request["data_type"])
        if len(payload) > ISDU_MAX_DATA_BYTES:
            raise ValueError(
                f"ISDU payload too large: {len(payload)} bytes; "
                f"max {ISDU_MAX_DATA_BYTES}"
            )
        request = dict(request)
        payload = isdu_write_payload(message, request, payload)
        request["length"] = len(payload)
        write_isdu_header(
            runtime,
            slave_index,
            request,
            direction=None,
            write_length=True,
        )
        write_isdu_data_payload(runtime, slave_index, request, payload)
        isdu_sdo_step(
            "write direction",
            request,
            runtime.ethercat_master.sdo.write_uint8,
            slave_index,
            request["object_index"],
            1,
            ISDU_DIRECTION_WRITE,
        )
        status = poll_isdu_status(runtime, slave_index, request)
        require_isdu_success(status, request)
    except Exception as exc:
        send_client_message(
            client,
            isdu_error_response(response_type, message, exc),
        )
        return

    response = isdu_response(response_type, request)
    response.update({
        "ok": True,
        "status": status,
        "length": request["length"],
        "data": bytes(payload).hex(),
    })
    send_client_message(client, response)


def write_isdu_header(
    runtime,
    slave_index,
    request,
    direction,
    write_length,
):
    sdo = runtime.ethercat_master.sdo
    object_index = request["object_index"]
    isdu_sdo_step(
        "write port",
        request,
        sdo.write_uint8,
        slave_index,
        object_index,
        2,
        request["port"],
    )
    isdu_sdo_step(
        "write isdu index",
        request,
        sdo.write_uint16,
        slave_index,
        object_index,
        3,
        request["index"],
    )
    isdu_sdo_step(
        "write isdu subindex",
        request,
        sdo.write_uint8,
        slave_index,
        object_index,
        4,
        request["subindex"],
    )
    if write_length:
        isdu_sdo_step(
            "write data length",
            request,
            sdo.write_uint8,
            slave_index,
            object_index,
            6,
            request["length"],
        )
    if direction is not None:
        isdu_sdo_step(
            "write direction",
            request,
            sdo.write_uint8,
            slave_index,
            object_index,
            1,
            direction,
        )


def require_isdu_success(status, request):
    status = int(status)
    if status == 0:
        return
    raise RuntimeError(
        "IO-Link ISDU access failed: "
        f"status=0x{status:04X} "
        f"module={request['module']} "
        f"port={request['port']} "
        f"index=0x{request['index']:04X} "
        f"subindex=0x{request['subindex']:02X}"
    )


def poll_isdu_status(runtime, slave_index, request):
    deadline = time.monotonic() + ISDU_STATUS_POLL_TIMEOUT
    while True:
        status = isdu_sdo_step(
            "read isdu error",
            request,
            runtime.ethercat_master.sdo.read_uint16,
            slave_index,
            request["object_index"],
            5,
        )
        if int(status) != ISDU_STATUS_BUSY:
            return status
        if time.monotonic() >= deadline:
            return status
        time.sleep(ISDU_STATUS_POLL_PERIOD)


def parse_isdu_request(message, require_value):
    if "io" not in message:
        raise ValueError("IO-Link ISDU commands require io")
    if "module" not in message:
        raise ValueError("IO-Link ISDU commands require module")
    if "port" not in message:
        raise ValueError("IO-Link ISDU commands require port")
    if "index" not in message:
        raise ValueError("IO-Link ISDU commands require index")
    if require_value and "value" not in message:
        raise ValueError("system/io/iolink/isdu_write requires value")

    data_type = str(message.get("data_type", "bytes")).strip().lower()
    module = parse_int(message.get("module"), 0)
    port = parse_int(message.get("port"), 0)
    index = parse_int(message.get("index"), 0)
    subindex = parse_int(message.get("subindex", 0), 0)
    length = parse_isdu_length(message, data_type)
    object_index = isdu_access_object_index(module)

    if module < 1 or module > 0xFF:
        raise ValueError(
            f"Invalid IO-Link module: {module}. CPX AP module numbering starts at 1."
        )
    if port < 0 or port > 0xFF:
        raise ValueError(f"Invalid IO-Link port: {port}")
    if index < 0 or index > 0xFFFF:
        raise ValueError(f"Invalid IO-Link ISDU index: {index}")
    if subindex < 0 or subindex > 0xFF:
        raise ValueError(f"Invalid IO-Link ISDU subindex: {subindex}")
    if length < 0 or length > ISDU_MAX_DATA_BYTES:
        raise ValueError(f"Invalid IO-Link ISDU length: {length}")
    validate_isdu_length(data_type, length)
    validate_raw_isdu_length(message, data_type, length)

    return {
        "io": message.get("io"),
        "module": module,
        "port": port,
        "index": index,
        "subindex": subindex,
        "length": length,
        "data_type": data_type,
        "object_index": object_index,
    }


def isdu_access_object_index(module):
    return ISDU_ACCESS_BASE_INDEX + int(module) * ISDU_ACCESS_INDEX_STEP


def validate_isdu_request_against_iodd(runtime, request, access):
    binding = iodd_binding_for_request(runtime, request)
    variable = iodd_variable_for_index(binding, request["index"])
    validate_iodd_variable_access(variable, access, request)
    validate_iodd_subindex(variable, request)


def iodd_binding_for_request(runtime, request):
    device = runtime.device_manager.io.selected_device(io_id=request["io"])
    profile = getattr(device["slave"], "device_profile", None)
    config = getattr(profile, "config", None)
    if config is None:
        raise ValueError(f"I/O device {request['io']} has no CPX configuration")

    for binding in config.io_link_devices:
        if (
            int(binding.module) == int(request["module"])
            and int(binding.port) == int(request["port"])
        ):
            return binding

    raise ValueError(
        "No IODD device binding for IO-Link parameter access: "
        f"io={request['io']} "
        f"module={request['module']} "
        f"port={request['port']}. "
        "Configure MOTION_SERVER_IO_<io>_IOL_PORTS before using ISDU access."
    )


def iodd_variable_for_index(binding, index):
    for variable in binding.device.variables:
        if int(variable.index) == int(index):
            return variable
    raise ValueError(
        "Unsupported IO-Link parameter index for configured IODD: "
        f"device={binding.device.device_name!r} "
        f"module={binding.module} "
        f"port={binding.port} "
        f"index=0x{int(index):04X}"
    )


def validate_iodd_variable_access(variable, access, request):
    rights = str(variable.access or "").strip().lower()
    if access == "read" and "r" in rights:
        return
    if access == "write" and "w" in rights:
        return
    raise ValueError(
        "IO-Link parameter access is not allowed by IODD: "
        f"index=0x{request['index']:04X} "
        f"subindex=0x{request['subindex']:02X} "
        f"requested={access} "
        f"iodd_access={variable.access!r} "
        f"name={variable.name!r}"
    )


def validate_iodd_subindex(variable, request):
    subindex = int(request["subindex"])
    if subindex == 0:
        return

    supported_subindices = {
        int(item["subindex"])
        for item in variable.subindices
        if "subindex" in item
    }
    if not supported_subindices:
        raise ValueError(
            "IO-Link parameter subindex is not defined in IODD: "
            f"index=0x{request['index']:04X} "
            f"subindex=0x{subindex:02X} "
            f"name={variable.name!r}"
        )
    if subindex not in supported_subindices:
        formatted = ", ".join(
            f"0x{item:02X}"
            for item in sorted(supported_subindices)
        )
        raise ValueError(
            "Unsupported IO-Link parameter subindex for configured IODD: "
            f"index=0x{request['index']:04X} "
            f"subindex=0x{subindex:02X} "
            f"supported=[{formatted}] "
            f"name={variable.name!r}"
        )


def isdu_sdo_step(step, request, operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except Exception as exc:
        raise RuntimeError(
            "IO-Link ISDU SDO step failed: "
            f"step={step} "
            f"object=0x{request['object_index']:04X} "
            f"module={request['module']} "
            f"port={request['port']} "
            f"index=0x{request['index']:04X} "
            f"subindex=0x{request['subindex']:02X} "
            f"error={exc}"
        ) from exc


def read_isdu_data_payload(runtime, slave_index, request, read_length):
    payload = isdu_sdo_step(
        "read data",
        request,
        runtime.ethercat_master.read_sdo,
        slave_index,
        request["object_index"],
        7,
        ISDU_MAX_DATA_BYTES,
    )
    return bytes(payload)[:read_length]


def write_isdu_data_payload(runtime, slave_index, request, payload):
    data = bytes(payload)
    if len(data) < ISDU_MAX_DATA_BYTES:
        data += bytes(ISDU_MAX_DATA_BYTES - len(data))
    isdu_sdo_step(
        "write data",
        request,
        runtime.ethercat_master.write_sdo,
        slave_index,
        request["object_index"],
        7,
        data,
    )


def parse_isdu_length(message, data_type):
    if "length" in message:
        return parse_int(message.get("length"), 0)
    data_format = ISDU_DATA_FORMATS.get(data_type)
    if data_format is not None:
        return struct.calcsize(data_format)
    return 0


def validate_isdu_length(data_type, length):
    data_format = ISDU_DATA_FORMATS.get(data_type)
    if data_format is None:
        return
    expected = struct.calcsize(data_format)
    if int(length) != expected:
        raise ValueError(
            f"IO-Link ISDU length mismatch for {data_type}: "
            f"expected {expected}, got {length}"
        )


def validate_raw_isdu_length(message, data_type, length):
    if data_type not in {"bytes", "hex", "byte_array", "char", "string", "ascii"}:
        return
    if "length" not in message and "value" not in message:
        raise ValueError("IO-Link raw ISDU read requires length")
    if int(length) <= 0 and "value" not in message:
        raise ValueError("IO-Link raw ISDU length must be greater than 0")


def encode_isdu_payload(value, data_type):
    if data_type in {"bytes", "hex", "byte_array"}:
        return parse_hex_payload(value)
    if data_type in {"char", "string", "ascii"}:
        return str(value).encode("ascii")
    data_format = ISDU_DATA_FORMATS.get(data_type)
    if data_format is None:
        raise ValueError(f"Unsupported IO-Link ISDU data_type: {data_type}")
    if data_type == "float32":
        return struct.pack(data_format, float(value))
    return struct.pack(data_format, int(str(value), 0))


def isdu_write_payload(message, request, payload):
    payload = bytes(payload)
    data_type = request["data_type"]
    if data_type not in {"bytes", "hex", "byte_array", "char", "string", "ascii"}:
        return payload
    if "length" not in message:
        return payload
    length = int(request["length"])
    if len(payload) > length:
        raise ValueError(
            f"IO-Link ISDU payload too long for requested length: "
            f"payload={len(payload)} length={length}"
        )
    return payload + bytes(length - len(payload))


def decode_isdu_payload(payload, data_type):
    payload = bytes(payload)
    if data_type in {"bytes", "hex", "byte_array"}:
        return payload.hex()
    if data_type in {"char", "string", "ascii"}:
        return payload.rstrip(b"\x00").decode("ascii", errors="replace")
    data_format = ISDU_DATA_FORMATS.get(data_type)
    if data_format is None:
        raise ValueError(f"Unsupported IO-Link ISDU data_type: {data_type}")
    size = struct.calcsize(data_format)
    if len(payload) < size:
        raise ValueError(
            f"IO-Link ISDU payload too short for {data_type}: "
            f"expected {size}, actual {len(payload)}"
        )
    value = struct.unpack(data_format, payload[:size])[0]
    if data_type == "float32":
        return float(value)
    return int(value)


def parse_hex_payload(value):
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("0x"):
            text = text[2:]
        if len(text) % 2:
            text = "0" + text
        return bytes.fromhex(text)
    return bytes(int(item) & 0xFF for item in value)


def isdu_response(response_type, request):
    return {
        "type": response_type,
        "io": request["io"],
        "object_index": f"0x{request['object_index']:04X}",
        "module": request["module"],
        "port": request["port"],
        "index": request["index"],
        "index_hex": f"0x{request['index']:04X}",
        "subindex": request["subindex"],
        "subindex_hex": f"0x{request['subindex']:02X}",
        "data_type": request["data_type"],
    }


def isdu_error_response(response_type, message, exc):
    try:
        module = parse_int(message.get("module"), 0)
        object_index = f"0x{isdu_access_object_index(module):04X}"
    except Exception:
        object_index = None
    return {
        "type": response_type,
        "ok": False,
        "io": message.get("io"),
        "object_index": object_index,
        "module": message.get("module"),
        "port": message.get("port"),
        "index": message.get("index"),
        "subindex": message.get("subindex", 0),
        "data_type": str(message.get("data_type", "bytes")).strip().lower(),
        "error": str(exc),
    }
