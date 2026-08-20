from motion_server.config import DEVICE_PROFILE
from motion_server.api import (
    command_name,
    parse_int,
    public_command_name,
    send_client_message,
)


SDO_STRING_TYPES = {"char", "string", "ascii", "visible_string"}

SDO_READERS = {
    "uint8": "read_uint8",
    "int8": "read_int8",
    "uint16": "read_uint16",
    "int16": "read_int16",
    "int32": "read_int32",
    "uint32": "read_uint32",
    "udint": "read_uint32",
    "float32": "read_float32",
}

SDO_WRITERS = {
    "uint8": "write_uint8",
    "int8": "write_int8",
    "uint16": "write_uint16",
    "int16": "write_int16",
    "int32": "write_int32",
    "uint32": "write_uint32",
    "udint": "write_uint32",
    "float32": "write_float32",
}


def sdo_response_type(message, default_type):
    return command_name(message) or default_type


def parse_sdo_request(message, runtime):
    data_type = normalize_sdo_data_type(message.get("data_type", "uint32"))
    if "axes" in message or "axis" not in message:
        raise ValueError("Parameter commands require axis and do not accept axes")
    axis_index = parse_int(message.get("axis", 0))
    index = parse_int(message.get("index"), 0)
    subindex = parse_int(message.get("subindex", 0))

    if axis_index < 0 or axis_index >= len(runtime.slaves):
        raise ValueError(f"Invalid axis index: {axis_index}")
    length = parse_sdo_length(message, data_type)
    return axis_index, index, subindex, data_type, length


def parse_io_sdo_request(message):
    data_type = normalize_sdo_data_type(message.get("data_type", "uint32"))
    if "io" not in message:
        raise ValueError("I/O parameter commands require io")
    io_selector = message.get("io")
    index = parse_int(message.get("index"), 0)
    subindex = parse_int(message.get("subindex", 0))
    length = parse_sdo_length(message, data_type)
    return io_selector, index, subindex, data_type, length


def selected_single_axis(message, runtime, command):
    if "axes" in message:
        axes = [parse_int(value) for value in message.get("axes", [])]
    elif "axis" in message:
        axes = [parse_int(message.get("axis"))]
    else:
        axes = list(range(len(runtime.slaves)))

    if len(axes) != 1:
        raise ValueError(f"{command} requires exactly one axis")
    axis_index = axes[0]
    if axis_index < 0 or axis_index >= len(runtime.slaves):
        raise ValueError(f"{command} invalid axes: {[axis_index]}")
    return axis_index


def read_parameter(message, runtime, client):
    response_type = sdo_response_type(message, "system/axis/param_read")
    try:
        axis_index, index, subindex, data_type, length = parse_sdo_request(
            message,
            runtime,
        )
        value = read_sdo_value(runtime.sdo, axis_index, index, subindex, data_type, length)
    except (TypeError, ValueError) as exc:
        send_client_message(
            client,
            {
                "type": response_type,
                "ok": False,
                "axis": message.get("axis", 0),
                "index": message.get("index"),
                "subindex": message.get("subindex", 0),
                "data_type": normalize_sdo_data_type(
                    message.get("data_type", "uint32")
                ),
                "error": str(exc),
            },
        )
        return
    except Exception as exc:
        send_client_message(
            client,
            {
                "type": response_type,
                "ok": False,
                "axis": axis_index,
                "index": index,
                "subindex": subindex,
                "data_type": data_type,
                "length": length,
                "error": str(exc),
            },
        )
        return

    send_client_message(
        client,
        {
            "type": response_type,
            "ok": True,
            "axis": axis_index,
            "index": index,
            "subindex": subindex,
            "data_type": data_type,
            "length": length,
            **sdo_value_response(data_type, value),
        },
    )


def write_parameter(message, runtime, client):
    response_type = public_command_name(message)
    try:
        axis_index, index, subindex, data_type, _length = parse_sdo_request(
            message,
            runtime,
        )
        if "value" not in message:
            raise ValueError("param_write requires value")
        value = write_sdo_value(
            runtime.sdo,
            axis_index,
            index,
            subindex,
            data_type,
            message["value"],
        )
    except Exception as exc:
        send_client_message(
            client,
            {
                "type": response_type,
                "ok": False,
                "axis": message.get("axis", 0),
                "index": message.get("index"),
                "subindex": message.get("subindex", 0),
                "data_type": str(message.get("data_type", "uint32")).strip().lower(),
                "error": str(exc),
            },
        )
        return

    send_client_message(
        client,
        {
            "type": response_type,
            "ok": True,
            "axis": axis_index,
            "index": index,
            "subindex": subindex,
            "data_type": data_type,
            "value": value,
        },
    )


def read_io_parameter(message, runtime, client):
    response_type = sdo_response_type(message, "system/io/param_read")
    try:
        io_selector, index, subindex, data_type, length = parse_io_sdo_request(message)
        validate_io_parameter_access(index, subindex)
        value = read_sdo_value(
            runtime.sdo.io,
            io_selector,
            index,
            subindex,
            data_type,
            length,
        )
    except (TypeError, ValueError) as exc:
        send_client_message(
            client,
            {
                "type": response_type,
                "ok": False,
                "io": message.get("io"),
                "index": message.get("index"),
                "subindex": message.get("subindex", 0),
                "data_type": normalize_sdo_data_type(
                    message.get("data_type", "uint32")
                ),
                "error": str(exc),
            },
        )
        return
    except Exception as exc:
        send_client_message(
            client,
            {
                "type": response_type,
                "ok": False,
                "io": io_selector,
                "index": index,
                "subindex": subindex,
                "data_type": data_type,
                "length": length,
                "error": str(exc),
            },
        )
        return

    send_client_message(
        client,
        {
            "type": response_type,
            "ok": True,
            "io": io_selector,
            "index": index,
            "subindex": subindex,
            "data_type": data_type,
            "length": length,
            **sdo_value_response(data_type, value),
        },
    )


def write_io_parameter(message, runtime, client):
    response_type = public_command_name(message)
    try:
        io_selector, index, subindex, data_type, _length = parse_io_sdo_request(message)
        validate_io_parameter_access(index, subindex)
        if "value" not in message:
            raise ValueError("param_write requires value")
        value = write_sdo_value(
            runtime.sdo.io,
            io_selector,
            index,
            subindex,
            data_type,
            message["value"],
        )
    except Exception as exc:
        send_client_message(
            client,
            {
                "type": response_type,
                "ok": False,
                "io": message.get("io"),
                "index": message.get("index"),
                "subindex": message.get("subindex", 0),
                "data_type": str(message.get("data_type", "uint32")).strip().lower(),
                "error": str(exc),
            },
        )
        return

    send_client_message(
        client,
        {
            "type": response_type,
            "ok": True,
            "io": io_selector,
            "index": index,
            "subindex": subindex,
            "data_type": data_type,
            "value": value,
        },
    )


def normalize_sdo_data_type(data_type):
    text = str(data_type or "uint32").strip().lower()
    if text.startswith("string("):
        return "string"
    if text in {"stringt", "visible-string", "visible_string"}:
        return "string"
    if text in SDO_STRING_TYPES:
        return "string"
    return text


def parse_sdo_length(message, data_type):
    if data_type != "string":
        return None
    if "length" in message:
        return parse_int(message.get("length"), 0)
    raw_type = str(message.get("data_type", "")).strip().lower()
    if raw_type.startswith("string(") and raw_type.endswith(")"):
        return parse_int(raw_type[len("string("):-1], 0)
    raise ValueError(
        "String SDO access requires length, for example "
        "'length': 12 or data_type 'STRING(12)'."
    )


def read_sdo_value(sdo, selector, index, subindex, data_type, length):
    if data_type == "string":
        return sdo.read_string(selector, index, subindex, length)
    reader_name = SDO_READERS.get(data_type)
    if reader_name is None:
        raise ValueError(f"Unsupported SDO data type: {data_type}")
    return getattr(sdo, reader_name)(selector, index, subindex)


def write_sdo_value(sdo, selector, index, subindex, data_type, raw_value):
    if data_type == "string":
        value = str(raw_value)
        sdo.write_string(selector, index, subindex, value)
        return value
    writer_name = SDO_WRITERS.get(data_type)
    if writer_name is None:
        raise ValueError(f"Unsupported SDO data type: {data_type}")
    value = float(raw_value) if data_type == "float32" else int(str(raw_value), 0)
    getattr(sdo, writer_name)(selector, index, subindex, value)
    return value


def sdo_value_response(data_type, value):
    if data_type == "string":
        return {
            "value": value,
            "hex": "0x" + str(value).encode("ascii", errors="replace").hex(),
        }
    if data_type == "float32":
        return {
            "value": float(value),
            "hex": None,
        }
    return {
        "value": int(value),
        "hex": f"0x{int(value) & 0xFFFFFFFF:08X}",
    }


def validate_io_parameter_access(index, subindex):
    if is_cpx_isdu_access_object(index):
        raise ValueError(
            "Direct SDO access to CPX IO-Link ISDU objects "
            f"0x{int(index):04X}:xx is blocked. "
            "Use a dedicated IO-Link ISDU command instead; generic "
            "system/io/param_read and param_write are only for ordinary "
            "EtherCAT OD objects."
        )


def is_cpx_isdu_access_object(index):
    index = int(index)
    return 0x2001 <= index <= 0x2FF1 and ((index - 0x2001) % 0x10) == 0


def save_parameters(message, runtime, client):
    response_type = public_command_name(message)
    try:
        axis_index = selected_single_axis(message, runtime, response_type)
        result = DEVICE_PROFILE.save_parameters(runtime, axis_index)
    except Exception as exc:
        send_client_message(
            client,
            {
                "type": response_type,
                "ok": False,
                "axis": message.get("axis", message.get("axes", 0)),
                "error": str(exc),
            },
        )
        return

    send_client_message(
        client,
        {
            "type": response_type,
            "ok": True,
            "axis": axis_index,
            "result": result,
        },
    )
