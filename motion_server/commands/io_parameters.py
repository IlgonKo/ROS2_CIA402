import struct
import time

from motion_server.api import (
    command_name,
    parse_int,
    public_command_name,
    send_client_message,
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
    "int32": "<i",
    "uint32": "<I",
    "udint": "<I",
    "float32": "<f",
}


def read_ap_parameter(message, runtime, client):
    response_type = command_name(message) or "system/io/ap/param_read"
    try:
        request = parse_ap_parameter_request(message, require_value=False)
        slave_index = runtime.device_manager.io.slave_index(request["io"])
        write_ap_access_header(
            runtime,
            slave_index,
            request,
            direction=AP_DIRECTION_READ,
            write_length=False,
        )
        status = poll_ap_status(
            runtime,
            slave_index,
            request,
        )
        require_ap_success(status, request)
        data_length = ap_sdo_step(
            "read data length",
            request,
            runtime.ethercat_master.sdo.read_uint16,
            slave_index,
            AP_PARAMETER_ACCESS_INDEX,
            6,
        )
        read_length = min(
            request["length"],
            max(0, int(data_length)),
            AP_MAX_DATA_BYTES,
        )
        payload = read_ap_data_payload(
            runtime,
            slave_index,
            request,
            read_length,
        )
        value = decode_ap_payload(payload, request["data_type"])
    except Exception as exc:
        send_client_message(
            client,
            ap_parameter_error_response(response_type, message, exc),
        )
        return

    response = ap_parameter_response(response_type, request)
    response.update({
        "ok": True,
        "status": status,
        "length": data_length,
        "data": bytes(payload).hex(),
        "value": value,
    })
    send_client_message(client, response)


def write_ap_parameter(message, runtime, client):
    response_type = public_command_name(message)
    try:
        request = parse_ap_parameter_request(message, require_value=True)
        slave_index = runtime.device_manager.io.slave_index(request["io"])
        payload = encode_ap_payload(message["value"], request["data_type"])
        if len(payload) > AP_MAX_DATA_BYTES:
            raise ValueError(
                f"AP parameter payload too large: {len(payload)} bytes; "
                f"max {AP_MAX_DATA_BYTES}"
        )
        request = dict(request)
        payload = ap_write_payload(message, request, payload)
        request["length"] = len(payload)
        write_ap_access_header(
            runtime,
            slave_index,
            request,
            direction=None,
            write_length=True,
        )
        write_ap_data_payload(runtime, slave_index, request, payload)
        ap_sdo_step(
            "write direction",
            request,
            runtime.ethercat_master.sdo.write_uint8,
            slave_index,
            AP_PARAMETER_ACCESS_INDEX,
            1,
            AP_DIRECTION_WRITE,
        )
        status = poll_ap_status(
            runtime,
            slave_index,
            request,
        )
        require_ap_success(status, request)
    except Exception as exc:
        send_client_message(
            client,
            ap_parameter_error_response(response_type, message, exc),
        )
        return

    response = ap_parameter_response(response_type, request)
    response.update({
        "ok": True,
        "status": status,
        "length": request["length"],
        "data": bytes(payload).hex(),
    })
    send_client_message(client, response)


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
        request["module"],
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
    raise RuntimeError(
        "AP parameter access failed: "
        f"status=0x{status:04X} "
        f"module={request['module']} "
        f"parameter_id=0x{request['parameter_id']:08X} "
        f"instance={request['instance']}"
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
        raise ValueError("AP parameter commands require io")
    if "module" not in message and "slot" not in message:
        raise ValueError("AP parameter commands require module")
    if "parameter_id" not in message:
        raise ValueError("AP parameter commands require parameter_id")
    if require_value and "value" not in message:
        raise ValueError("system/io/ap/param_write requires value")

    data_type = str(message.get("data_type", "bytes")).strip().lower()
    module = parse_int(message.get("module", message.get("slot")), 0)
    parameter_id = parse_int(message.get("parameter_id"), 0)
    instance = parse_int(message.get("instance", 0), 0)
    length = parse_ap_length(message, data_type)
    if module < 1 or module > 0xFFFF:
        raise ValueError(
            f"Invalid AP module: {module}. AP module numbering starts at 1."
        )
    if parameter_id < 0 or parameter_id > 0xFFFFFFFF:
        raise ValueError(f"Invalid AP parameter_id: {parameter_id}")
    if instance < 0 or instance > 0xFFFF:
        raise ValueError(f"Invalid AP parameter instance: {instance}")
    if length < 0 or length > AP_MAX_DATA_BYTES:
        raise ValueError(f"Invalid AP parameter length: {length}")
    validate_ap_length(data_type, length)
    validate_raw_ap_length(message, data_type, length)

    return {
        "io": message.get("io"),
        "module": module,
        "parameter_id": parameter_id,
        "instance": instance,
        "length": length,
        "data_type": data_type,
    }


def ap_sdo_step(step, request, operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except Exception as exc:
        raise RuntimeError(
            "AP parameter SDO step failed: "
            f"step={step} "
            f"module={request.get('module')} "
            f"parameter_id=0x{request['parameter_id']:08X} "
            f"instance={request['instance']} "
            f"error={exc}"
        ) from exc


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
        return parse_int(message.get("length"), 0)
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
        raise ValueError(
            f"AP parameter length mismatch for {data_type}: "
            f"expected {expected}, got {length}"
        )


def validate_raw_ap_length(message, data_type, length):
    if data_type not in {"bytes", "hex", "byte_array", "char", "string", "ascii"}:
        return
    if "length" not in message and "value" not in message:
        raise ValueError("AP raw byte parameter read requires length")
    if int(length) <= 0 and "value" not in message:
        raise ValueError("AP raw byte parameter length must be greater than 0")


def encode_ap_payload(value, data_type):
    if data_type in {"bytes", "hex", "byte_array"}:
        return parse_hex_payload(value)
    if data_type in {"char", "string", "ascii"}:
        return str(value).encode("ascii")
    data_format = AP_DATA_FORMATS.get(data_type)
    if data_format is None:
        raise ValueError(f"Unsupported AP parameter data_type: {data_type}")
    if data_type == "float32":
        return struct.pack(data_format, float(value))
    return struct.pack(data_format, int(str(value), 0))


def ap_write_payload(message, request, payload):
    payload = bytes(payload)
    data_type = request["data_type"]
    if data_type not in {"bytes", "hex", "byte_array", "char", "string", "ascii"}:
        return payload
    if "length" not in message:
        return payload
    length = int(request["length"])
    if len(payload) > length:
        raise ValueError(
            f"AP parameter payload too long for requested length: "
            f"payload={len(payload)} length={length}"
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
        raise ValueError(f"Unsupported AP parameter data_type: {data_type}")
    size = struct.calcsize(data_format)
    if len(payload) < size:
        raise ValueError(
            f"AP parameter payload too short for {data_type}: "
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


def ap_parameter_response(response_type, request):
    return {
        "type": response_type,
        "io": request["io"],
        "object_index": f"0x{AP_PARAMETER_ACCESS_INDEX:04X}",
        "module": request["module"],
        "parameter_id": request["parameter_id"],
        "parameter_id_hex": f"0x{request['parameter_id']:08X}",
        "instance": request["instance"],
        "data_type": request["data_type"],
    }


def ap_parameter_error_response(response_type, message, exc):
    parameter_id = message.get("parameter_id")
    try:
        parameter_id_hex = f"0x{parse_int(parameter_id, 0):08X}"
    except Exception:
        parameter_id_hex = None
    return {
        "type": response_type,
        "ok": False,
        "io": message.get("io"),
        "object_index": f"0x{AP_PARAMETER_ACCESS_INDEX:04X}",
        "module": message.get("module", message.get("slot")),
        "parameter_id": parameter_id,
        "parameter_id_hex": parameter_id_hex,
        "instance": message.get("instance", 0),
        "data_type": str(message.get("data_type", "bytes")).strip().lower(),
        "error": str(exc),
    }
