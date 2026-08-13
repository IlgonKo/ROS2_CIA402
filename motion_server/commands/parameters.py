from motion_server.config import DEVICE_PROFILE
from motion_server.api import (
    command_name,
    parse_int,
    public_command_name,
    send_client_message,
)


SDO_READERS = {
    "uint8": "read_uint8",
    "int8": "read_int8",
    "uint16": "read_uint16",
    "int32": "read_int32",
    "uint32": "read_uint32",
    "udint": "read_uint32",
    "float32": "read_float32",
}

SDO_WRITERS = {
    "uint8": "write_uint8",
    "int8": "write_int8",
    "uint16": "write_uint16",
    "int32": "write_int32",
    "uint32": "write_uint32",
    "udint": "write_uint32",
    "float32": "write_float32",
}


def sdo_response_type(message, default_type):
    return command_name(message) or default_type


def parse_sdo_request(message, runtime):
    data_type = str(message.get("data_type", "uint32")).strip().lower()
    if "axes" in message or "axis" not in message:
        raise ValueError("Parameter commands require axis and do not accept axes")
    axis_index = parse_int(message.get("axis", 0))
    index = parse_int(message.get("index"), 0)
    subindex = parse_int(message.get("subindex", 0))

    if axis_index < 0 or axis_index >= len(runtime.slaves):
        raise ValueError(f"Invalid axis index: {axis_index}")
    return axis_index, index, subindex, data_type


def parse_io_sdo_request(message):
    data_type = str(message.get("data_type", "uint32")).strip().lower()
    if "io" not in message:
        raise ValueError("I/O parameter commands require io")
    io_selector = message.get("io")
    index = parse_int(message.get("index"), 0)
    subindex = parse_int(message.get("subindex", 0))
    return io_selector, index, subindex, data_type


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
        axis_index, index, subindex, data_type = parse_sdo_request(message, runtime)
        reader_name = SDO_READERS.get(data_type)
        if reader_name is None:
            raise ValueError(f"Unsupported SDO data type: {data_type}")
        reader = getattr(runtime.sdo, reader_name)
        value = reader(axis_index, index, subindex)
    except (TypeError, ValueError) as exc:
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
            "value": float(value) if data_type == "float32" else int(value),
            "hex": (
                None
                if data_type == "float32"
                else f"0x{int(value) & 0xFFFFFFFF:08X}"
            ),
        },
    )


def write_parameter(message, runtime, client):
    response_type = public_command_name(message)
    try:
        axis_index, index, subindex, data_type = parse_sdo_request(message, runtime)
        writer_name = SDO_WRITERS.get(data_type)
        if writer_name is None:
            raise ValueError(f"Unsupported SDO data type: {data_type}")
        if "value" not in message:
            raise ValueError("param_write requires value")
        value = float(message["value"]) if data_type == "float32" else int(
            str(message["value"]),
            0,
        )
        getattr(runtime.sdo, writer_name)(axis_index, index, subindex, value)
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
        io_selector, index, subindex, data_type = parse_io_sdo_request(message)
        validate_io_parameter_access(index, subindex)
        reader_name = SDO_READERS.get(data_type)
        if reader_name is None:
            raise ValueError(f"Unsupported SDO data type: {data_type}")
        reader = getattr(runtime.sdo.io, reader_name)
        value = reader(io_selector, index, subindex)
    except (TypeError, ValueError) as exc:
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
            "value": float(value) if data_type == "float32" else int(value),
            "hex": (
                None
                if data_type == "float32"
                else f"0x{int(value) & 0xFFFFFFFF:08X}"
            ),
        },
    )


def write_io_parameter(message, runtime, client):
    response_type = public_command_name(message)
    try:
        io_selector, index, subindex, data_type = parse_io_sdo_request(message)
        validate_io_parameter_access(index, subindex)
        writer_name = SDO_WRITERS.get(data_type)
        if writer_name is None:
            raise ValueError(f"Unsupported SDO data type: {data_type}")
        if "value" not in message:
            raise ValueError("param_write requires value")
        value = float(message["value"]) if data_type == "float32" else int(
            str(message["value"]),
            0,
        )
        getattr(runtime.sdo.io, writer_name)(io_selector, index, subindex, value)
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
