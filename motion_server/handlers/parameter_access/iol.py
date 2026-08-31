import struct
import time

from device.cpx_ap_i_ec.isdu_gateway import isdu_access_object_index
from motion_server.api.validator import parse_int
from motion_server.failure import (
    DeviceAccessException,
    DeviceRejectedException,
    InvalidArgumentException,
    InvalidRequestException,
    OperationTimeoutException,
    PermissionDeniedException,
    ResourceNotFoundException,
)


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


def read_iol_parameter(message, runtime, client):
    return _read_iol_parameter(message, runtime)


def write_iol_parameter(message, runtime, client):
    return _write_iol_parameter(message, runtime)


def _read_iol_parameter(message, runtime):
    request = parse_isdu_request(message, require_value=False)
    validate_isdu_request_against_iodd(runtime, request, access="read")
    slave_index = validate_isdu_target(runtime, request)
    write_isdu_header(
        runtime, slave_index, request, direction=ISDU_DIRECTION_READ,
        write_length=False,
    )
    status = poll_isdu_status(runtime, slave_index, request)
    require_isdu_success(status, request)
    data_length = isdu_sdo_step(
        "read data length", request,
        runtime.ethercat_master.sdo.read_uint8,
        slave_index, request["object_index"], 6,
    )
    read_length = min(request["length"], max(0, int(data_length)), ISDU_MAX_DATA_BYTES)
    payload = read_isdu_data_payload(runtime, slave_index, request, read_length)
    value = decode_isdu_payload(payload, request["data_type"])
    return isdu_data(
        request, status=status, length=data_length,
        data=bytes(payload).hex(), value=value,
    )


def _write_iol_parameter(message, runtime):
    request = parse_isdu_request(message, require_value=True)
    validate_isdu_request_against_iodd(runtime, request, access="write")
    slave_index = validate_isdu_target(runtime, request)
    payload = encode_isdu_payload(message["value"], request["data_type"])
    if len(payload) > ISDU_MAX_DATA_BYTES:
        raise InvalidArgumentException("value", "exceeds the ISDU payload limit")
    request = dict(request)
    payload = isdu_write_payload(message, request, payload)
    request["length"] = len(payload)
    write_isdu_header(runtime, slave_index, request, direction=None, write_length=True)
    write_isdu_data_payload(runtime, slave_index, request, payload)
    isdu_sdo_step(
        "write direction", request,
        runtime.ethercat_master.sdo.write_uint8,
        slave_index, request["object_index"], 1, ISDU_DIRECTION_WRITE,
    )
    status = poll_isdu_status(runtime, slave_index, request)
    require_isdu_success(status, request)
    return isdu_data(
        request, status=status, length=request["length"],
        data=bytes(payload).hex(),
    )


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
    if status == ISDU_STATUS_BUSY:
        raise OperationTimeoutException(
            "iolink_isdu_access",
            timeout_seconds=ISDU_STATUS_POLL_TIMEOUT,
        )
    raise DeviceRejectedException(
        "iolink_isdu_access",
        device_code=status,
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
        raise InvalidRequestException("IO-Link ISDU commands require io")
    if "module" not in message:
        raise InvalidArgumentException("module", "is required")
    if "port" not in message:
        raise InvalidArgumentException("port", "is required")
    if "index" not in message:
        raise InvalidArgumentException("index", "is required")
    if require_value and "value" not in message:
        raise InvalidArgumentException("value", "is required")

    data_type = str(message.get("data_type", "bytes")).strip().lower()
    module = parse_isdu_int(message, "module")
    port = parse_isdu_int(message, "port")
    index = parse_isdu_int(message, "index")
    subindex = parse_isdu_int(message, "subindex", default=0)
    length = parse_isdu_length(message, data_type)
    object_index = isdu_access_object_index(module)

    if module < 1 or module > 0xFF:
        raise InvalidArgumentException("module", "must be in range 1..255")
    if port < 0 or port > 0xFF:
        raise InvalidArgumentException("port", "is outside uint8 range")
    if index < 0 or index > 0xFFFF:
        raise InvalidArgumentException("index", "is outside uint16 range")
    if subindex < 0 or subindex > 0xFF:
        raise InvalidArgumentException("subindex", "is outside uint8 range")
    if length < 0 or length > ISDU_MAX_DATA_BYTES:
        raise InvalidArgumentException("length", "is outside the ISDU payload range")
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


def parse_isdu_int(message, field, *, default=None):
    if field not in message:
        if default is not None:
            return default
        raise InvalidArgumentException(field, "is required")
    try:
        return parse_int(message.get(field), 0)
    except (TypeError, ValueError) as exception:
        raise InvalidArgumentException(
            field, "must be an integer", public_value=message.get(field),
        ) from exception


def validate_isdu_target(runtime, request):
    try:
        return runtime.device_manager.io.slave_index(request["io"])
    except (TypeError, ValueError) as exception:
        raise ResourceNotFoundException("io", request["io"]) from exception


def validate_isdu_request_against_iodd(runtime, request, access):
    binding = iodd_binding_for_request(runtime, request)
    variable = iodd_variable_for_index(binding, request["index"])
    validate_iodd_variable_access(variable, access, request)
    validate_iodd_subindex(variable, request)


def iodd_binding_for_request(runtime, request):
    try:
        device = runtime.device_manager.io.selected_device(io_id=request["io"])
    except (TypeError, ValueError) as exception:
        raise ResourceNotFoundException("io", request["io"]) from exception
    profile = getattr(device["slave"], "device_profile", None)
    config = getattr(profile, "config", None)
    if config is None:
        raise ResourceNotFoundException("io_configuration", request["io"])

    for binding in config.io_link_devices:
        if (
            int(binding.module) == int(request["module"])
            and int(binding.port) == int(request["port"])
        ):
            return binding

    raise ResourceNotFoundException(
        "iolink_port_binding",
        f"{request['io']}:{request['module']}:{request['port']}",
    )


def iodd_variable_for_index(binding, index):
    for variable in binding.device.variables:
        if int(variable.index) == int(index):
            return variable
    raise ResourceNotFoundException(
        "iolink_parameter",
        int(index),
    )


def validate_iodd_variable_access(variable, access, request):
    rights = str(variable.access or "").strip().lower()
    if access == "read" and "r" in rights:
        return
    if access == "write" and "w" in rights:
        return
    raise PermissionDeniedException(f"iolink_isdu_{access}")


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
        raise ResourceNotFoundException(
            "iolink_subindex",
            f"{request['index']}:{subindex}",
        )
    if subindex not in supported_subindices:
        raise ResourceNotFoundException(
            "iolink_subindex",
            f"{request['index']}:{subindex}",
        )


def isdu_sdo_step(step, request, operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except DeviceRejectedException as exception:
        raise DeviceRejectedException(
            operation=exception.operation,
            device_code=exception.device_code,
            isdu_step=step,
            sdo_index=sdo_index_arg(args),
            sdo_subindex=sdo_subindex_arg(args),
            sdo_value=sdo_value_arg(args),
        ) from exception


def sdo_index_arg(args):
    if len(args) < 2:
        return None
    return f"0x{int(args[1]):04X}"


def sdo_subindex_arg(args):
    if len(args) < 3:
        return None
    return int(args[2])


def sdo_value_arg(args):
    if len(args) < 4:
        return None
    value = args[3]
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    return int(value)


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
        return parse_isdu_int(message, "length")
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
        raise InvalidArgumentException(
            "length", f"must be {expected} for {data_type}",
        )


def validate_raw_isdu_length(message, data_type, length):
    if data_type not in {"bytes", "hex", "byte_array", "char", "string", "ascii"}:
        return
    if "length" not in message and "value" not in message:
        raise InvalidArgumentException("length", "is required for raw ISDU reads")
    if int(length) <= 0 and "value" not in message:
        raise InvalidArgumentException("length", "must be greater than 0")


def encode_isdu_payload(value, data_type):
    try:
        if data_type in {"bytes", "hex", "byte_array"}:
            return parse_hex_payload(value)
        if data_type in {"char", "string", "ascii"}:
            return str(value).encode("ascii")
        data_format = ISDU_DATA_FORMATS.get(data_type)
        if data_format is None:
            raise InvalidArgumentException(
                "data_type", "is not a supported ISDU data type",
                public_value=data_type,
            )
        if data_type == "float32":
            return struct.pack(data_format, float(value))
        return struct.pack(data_format, int(str(value), 0))
    except InvalidArgumentException:
        raise
    except (TypeError, ValueError, OverflowError, struct.error) as exception:
        raise InvalidArgumentException(
            "value", f"is invalid for {data_type}", public_value=value,
        ) from exception


def isdu_write_payload(message, request, payload):
    payload = bytes(payload)
    data_type = request["data_type"]
    if data_type not in {"bytes", "hex", "byte_array", "char", "string", "ascii"}:
        return payload
    if "length" not in message:
        return payload
    length = int(request["length"])
    if len(payload) > length:
        raise InvalidArgumentException(
            "value", "is longer than the requested ISDU payload length",
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
        raise InvalidArgumentException(
            "data_type", "is not a supported ISDU data type",
            public_value=data_type,
        )
    size = struct.calcsize(data_format)
    if len(payload) < size:
        raise DeviceAccessException("iolink_isdu_short_payload")
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


def isdu_data(request, **values):
    data = {
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
    data.update(values)
    return data
