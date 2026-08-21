import struct
import time

from motion_server.api.encoder import send_client_message
from motion_server.api.validator import parse_int
from motion_server.failure import (
    DeviceAccessException,
    DeviceRejectedException,
    InvalidArgumentException,
    InvalidRequestException,
    OperationTimeoutException,
    ResourceNotFoundException,
)


AP_PARAMETER_ACCESS_INDEX = 0x27F0
AP_DIRECTION_READ = 0
AP_DIRECTION_WRITE = 1
AP_MAX_DATA_BYTES = 512
AP_STATUS_BUSY = 0xFFFF
AP_STATUS_POLL_TIMEOUT = 1.0
AP_STATUS_POLL_PERIOD = 0.02

AP_DATA_FORMATS = {
    "int8": "<b",
    "uint8": "<B",
    "uint16": "<H",
    "int16": "<h",
    "int32": "<i",
    "uint32": "<I",
    "udint": "<I",
    "float32": "<f",
}


def read_ap_parameter(message, runtime, client):
    response = parameter_request_response(
        message,
        lambda: _read_ap_parameter(message, runtime),
    )
    send_client_message(client, response)


def write_ap_parameter(message, runtime, client):
    response = parameter_request_response(
        message,
        lambda: _write_ap_parameter(message, runtime),
    )
    send_client_message(client, response)


def parameter_request_response(message, operation):
    # TECH_DEBT[TD-005]: S11 moves this nested boundary to the live router.
    from motion_server.api.router import request_response

    return request_response(message, operation)


def _read_ap_parameter(message, runtime):
    request = parse_ap_parameter_request(message, require_value=False)
    slave_index = validate_ap_target(runtime, request)
    write_ap_access_header(
        runtime, slave_index, request, direction=AP_DIRECTION_READ,
        write_length=False,
    )
    status = poll_ap_status(runtime, slave_index, request)
    require_ap_success(status, request)
    data_length = ap_sdo_step(
        "read data length", request,
        runtime.ethercat_master.sdo.read_uint16,
        slave_index, AP_PARAMETER_ACCESS_INDEX, 6,
    )
    read_length = min(request["length"], max(0, int(data_length)), AP_MAX_DATA_BYTES)
    payload = read_ap_data_payload(runtime, slave_index, request, read_length)
    value = decode_ap_payload(payload, request["data_type"])
    return ap_parameter_data(
        request, status=status, length=data_length,
        data=bytes(payload).hex(), value=value,
    )


def _write_ap_parameter(message, runtime):
    request = parse_ap_parameter_request(message, require_value=True)
    slave_index = validate_ap_target(runtime, request)
    payload = encode_ap_payload(message["value"], request["data_type"])
    if len(payload) > AP_MAX_DATA_BYTES:
        raise InvalidArgumentException("value", "exceeds the AP payload limit")
    request = dict(request)
    payload = ap_write_payload(message, request, payload)
    request["length"] = len(payload)
    write_ap_access_header(
        runtime, slave_index, request, direction=None, write_length=True,
    )
    write_ap_data_payload(runtime, slave_index, request, payload)
    ap_sdo_step(
        "write direction", request,
        runtime.ethercat_master.sdo.write_uint8,
        slave_index, AP_PARAMETER_ACCESS_INDEX, 1, AP_DIRECTION_WRITE,
    )
    status = poll_ap_status(runtime, slave_index, request)
    require_ap_success(status, request)
    return ap_parameter_data(
        request, status=status, length=request["length"],
        data=bytes(payload).hex(),
    )


def write_ap_access_header(
    runtime,
    slave_index,
    request,
    direction,
    write_length,
):
    sdo = runtime.ethercat_master.sdo
    ap_sdo_step(
        "write module address",
        request,
        sdo.write_uint16,
        slave_index,
        AP_PARAMETER_ACCESS_INDEX,
        2,
        request["ap_access_module"],
    )
    ap_sdo_step(
        "write parameter id",
        request,
        sdo.write_uint32,
        slave_index,
        AP_PARAMETER_ACCESS_INDEX,
        3,
        request["parameter_id"],
    )
    ap_sdo_step(
        "write parameter instance",
        request,
        sdo.write_uint16,
        slave_index,
        AP_PARAMETER_ACCESS_INDEX,
        4,
        request["instance"],
    )
    if write_length:
        ap_sdo_step(
            "write data length",
            request,
            sdo.write_uint16,
            slave_index,
            AP_PARAMETER_ACCESS_INDEX,
            6,
            request["length"],
        )
    if direction is not None:
        ap_sdo_step(
            "write direction",
            request,
            sdo.write_uint8,
            slave_index,
            AP_PARAMETER_ACCESS_INDEX,
            1,
            direction,
        )


def require_ap_success(status, request):
    status = int(status)
    if status == 0:
        return
    if status == AP_STATUS_BUSY:
        raise OperationTimeoutException(
            "ap_parameter_access",
            timeout_seconds=AP_STATUS_POLL_TIMEOUT,
        )
    raise DeviceRejectedException(
        "ap_parameter_access",
        device_code=status,
    )


def poll_ap_status(runtime, slave_index, request):
    deadline = time.monotonic() + AP_STATUS_POLL_TIMEOUT
    while True:
        status = ap_sdo_step(
            "read status",
            request,
            runtime.ethercat_master.sdo.read_uint16,
            slave_index,
            AP_PARAMETER_ACCESS_INDEX,
            5,
        )
        if int(status) != AP_STATUS_BUSY:
            return status
        if time.monotonic() >= deadline:
            return status
        time.sleep(AP_STATUS_POLL_PERIOD)


def parse_ap_parameter_request(message, require_value):
    if "io" not in message:
        raise InvalidRequestException("AP parameter commands require io")
    if "module" not in message and "slot" not in message:
        raise InvalidRequestException("AP parameter commands require module")
    if "parameter_id" not in message:
        raise InvalidArgumentException("parameter_id", "is required")
    if require_value and "value" not in message:
        raise InvalidArgumentException("value", "is required")

    data_type = str(message.get("data_type", "bytes")).strip().lower()
    module = parse_ap_int(message, "module", alias="slot")
    parameter_id = parse_ap_int(message, "parameter_id")
    instance = parse_ap_int(message, "instance", default=0)
    length = parse_ap_length(message, data_type)
    if module < 0 or module > 0xFFFF:
        raise InvalidArgumentException("module", "is outside uint16 range")
    if parameter_id < 0 or parameter_id > 0xFFFFFFFF:
        raise InvalidArgumentException("parameter_id", "is outside uint32 range")
    if instance < 0 or instance > 0xFFFF:
        raise InvalidArgumentException("instance", "is outside uint16 range")
    if length < 0 or length > AP_MAX_DATA_BYTES:
        raise InvalidArgumentException("length", "is outside the AP payload range")
    validate_ap_length(data_type, length)
    validate_raw_ap_length(message, data_type, length)

    return {
        "io": message.get("io"),
        "module": module,
        "ap_access_module": ap_access_module_number(module),
        "parameter_id": parameter_id,
        "instance": instance,
        "length": length,
        "data_type": data_type,
    }


def parse_ap_int(message, field, *, alias=None, default=None):
    key = field if field in message else alias
    if key is None or key not in message:
        if default is not None:
            return default
        raise InvalidArgumentException(field, "is required")
    try:
        return parse_int(message.get(key), 0)
    except (TypeError, ValueError) as exception:
        raise InvalidArgumentException(
            field,
            "must be an integer",
            public_value=message.get(key),
        ) from exception


def validate_ap_target(runtime, request):
    try:
        slave_index = runtime.device_manager.io.slave_index(request["io"])
        device = runtime.device_manager.io.selected_device(slave_index=slave_index)
    except (TypeError, ValueError) as exception:
        raise ResourceNotFoundException("io", request["io"]) from exception

    module = request["module"]
    if module == 0:
        return slave_index
    layout = device["slave"].rxpdo.config.layout
    if not any(int(item.slot) == module for item in layout.modules):
        raise ResourceNotFoundException(
            "ap_module",
            f"{request['io']}:{module}",
        )
    return slave_index


def ap_sdo_step(step, request, operation, *args, **kwargs):
    return operation(*args, **kwargs)


def ap_access_module_number(module):
    return int(module) + 1


def read_ap_data_payload(runtime, slave_index, request, read_length):
    payload = ap_sdo_step(
        "read data",
        request,
        runtime.ethercat_master.read_sdo,
        slave_index,
        AP_PARAMETER_ACCESS_INDEX,
        7,
        AP_MAX_DATA_BYTES,
    )
    return bytes(payload)[:read_length]


def write_ap_data_payload(runtime, slave_index, request, payload):
    data = bytes(payload)
    if len(data) < AP_MAX_DATA_BYTES:
        data += bytes(AP_MAX_DATA_BYTES - len(data))
    ap_sdo_step(
        "write data",
        request,
        runtime.ethercat_master.write_sdo,
        slave_index,
        AP_PARAMETER_ACCESS_INDEX,
        7,
        data,
    )


def parse_ap_length(message, data_type):
    if "length" in message:
        return parse_ap_int(message, "length")
    data_format = AP_DATA_FORMATS.get(data_type)
    if data_format is not None:
        return struct.calcsize(data_format)
    return 0


def validate_ap_length(data_type, length):
    data_format = AP_DATA_FORMATS.get(data_type)
    if data_format is None:
        return
    expected = struct.calcsize(data_format)
    if int(length) != expected:
        raise InvalidArgumentException(
            "length",
            f"must be {expected} for {data_type}",
        )


def validate_raw_ap_length(message, data_type, length):
    if data_type not in {"bytes", "hex", "byte_array", "char", "string", "ascii"}:
        return
    if "length" not in message and "value" not in message:
        raise InvalidArgumentException("length", "is required for raw AP reads")
    if int(length) <= 0 and "value" not in message:
        raise InvalidArgumentException("length", "must be greater than 0")


def encode_ap_payload(value, data_type):
    try:
        if data_type in {"bytes", "hex", "byte_array"}:
            return parse_hex_payload(value)
        if data_type in {"char", "string", "ascii"}:
            return str(value).encode("ascii")
        data_format = AP_DATA_FORMATS.get(data_type)
        if data_format is None:
            raise InvalidArgumentException(
                "data_type",
                "is not a supported AP parameter data type",
                public_value=data_type,
            )
        if data_type == "float32":
            return struct.pack(data_format, float(value))
        return struct.pack(data_format, int(str(value), 0))
    except InvalidArgumentException:
        raise
    except (TypeError, ValueError, OverflowError, struct.error) as exception:
        raise InvalidArgumentException(
            "value",
            f"is invalid for {data_type}",
            public_value=value,
        ) from exception


def ap_write_payload(message, request, payload):
    payload = bytes(payload)
    data_type = request["data_type"]
    if data_type not in {"bytes", "hex", "byte_array", "char", "string", "ascii"}:
        return payload
    if "length" not in message:
        return payload
    length = int(request["length"])
    if len(payload) > length:
        raise InvalidArgumentException(
            "value",
            "is longer than the requested AP payload length",
        )
    return payload + bytes(length - len(payload))


def decode_ap_payload(payload, data_type):
    payload = bytes(payload)
    if data_type in {"bytes", "hex", "byte_array"}:
        return payload.hex()
    if data_type in {"char", "string", "ascii"}:
        return payload.rstrip(b"\x00").decode("ascii", errors="replace")
    data_format = AP_DATA_FORMATS.get(data_type)
    if data_format is None:
        raise InvalidArgumentException(
            "data_type",
            "is not a supported AP parameter data type",
            public_value=data_type,
        )
    size = struct.calcsize(data_format)
    if len(payload) < size:
        raise DeviceAccessException("ap_parameter_short_payload")
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


def ap_parameter_data(request, **values):
    data = {
        "io": request["io"],
        "object_index": f"0x{AP_PARAMETER_ACCESS_INDEX:04X}",
        "module": request["module"],
        "ap_access_module": request["ap_access_module"],
        "parameter_id": request["parameter_id"],
        "parameter_id_hex": f"0x{request['parameter_id']:08X}",
        "instance": request["instance"],
        "data_type": request["data_type"],
    }
    data.update(values)
    return data
