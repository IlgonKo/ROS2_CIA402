from motion_server.device_manager.profile_access import axis_device_profile
from motion_server.api.decoder import public_command_name
from motion_server.api.validator import parse_int
from motion_server.failure import (
    InvalidArgumentException,
    InvalidRequestException,
    ResourceNotFoundException,
    UnsupportedOperationException,
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


def parse_sdo_request(message, runtime):
    data_type = normalize_sdo_data_type(message.get("data_type", "uint32"))
    if "axes" in message or "axis" not in message:
        raise InvalidRequestException(
            "Parameter commands require axis and do not accept axes",
        )
    axis_index = parse_sdo_int(message, "axis")
    index = parse_sdo_int(message, "index")
    subindex = parse_sdo_int(message, "subindex", default=0)

    if axis_index < 0 or axis_index >= len(runtime.slaves):
        raise ResourceNotFoundException("axis", axis_index)
    length = parse_sdo_length(message, data_type)
    return axis_index, index, subindex, data_type, length


def parse_io_sdo_request(message):
    data_type = normalize_sdo_data_type(message.get("data_type", "uint32"))
    if "io" not in message:
        raise InvalidRequestException("I/O parameter commands require io")
    io_selector = message.get("io")
    index = parse_sdo_int(message, "index")
    subindex = parse_sdo_int(message, "subindex", default=0)
    length = parse_sdo_length(message, data_type)
    return io_selector, index, subindex, data_type, length


def parse_sdo_int(message, field, *, default=None):
    if field not in message:
        if default is not None:
            return default
        raise InvalidArgumentException(field, "is required")
    try:
        return parse_int(message.get(field), 0)
    except (TypeError, ValueError) as exception:
        raise InvalidArgumentException(
            field,
            "must be an integer",
            public_value=message.get(field),
        ) from exception


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
    return _read_axis_parameter(message, runtime)


def write_parameter(message, runtime, client):
    return _write_axis_parameter(message, runtime)


def read_io_parameter(message, runtime, client):
    return _read_io_parameter(message, runtime)


def write_io_parameter(message, runtime, client):
    return _write_io_parameter(message, runtime)


def _read_axis_parameter(message, runtime):
    axis, index, subindex, data_type, length = parse_sdo_request(message, runtime)
    value = read_sdo_value(runtime.sdo, axis, index, subindex, data_type, length)
    data = _parameter_data("axis", axis, index, subindex, data_type, value)
    data["length"] = length
    return data


def _write_axis_parameter(message, runtime):
    axis, index, subindex, data_type, _length = parse_sdo_request(message, runtime)
    value = required_sdo_write_value(message)
    written = write_sdo_value(
        runtime.sdo, axis, index, subindex, data_type, value,
    )
    return _parameter_data("axis", axis, index, subindex, data_type, written)


def _read_io_parameter(message, runtime):
    io_selector, index, subindex, data_type, length = parse_io_sdo_request(message)
    validate_io_selector(runtime, io_selector)
    validate_io_parameter_access(index, subindex)
    value = read_sdo_value(
        runtime.sdo.io, io_selector, index, subindex, data_type, length,
    )
    data = _parameter_data(
        "io", io_selector, index, subindex, data_type, value,
    )
    data["length"] = length
    return data


def _write_io_parameter(message, runtime):
    io_selector, index, subindex, data_type, _length = parse_io_sdo_request(message)
    validate_io_selector(runtime, io_selector)
    validate_io_parameter_access(index, subindex)
    value = required_sdo_write_value(message)
    written = write_sdo_value(
        runtime.sdo.io, io_selector, index, subindex, data_type, value,
    )
    return _parameter_data(
        "io", io_selector, index, subindex, data_type, written,
    )


def _parameter_data(target_name, target, index, subindex, data_type, value):
    return {
        target_name: target,
        "index": index,
        "subindex": subindex,
        "data_type": data_type,
        **sdo_value_response(data_type, value),
    }


def required_sdo_write_value(message):
    if "value" not in message:
        raise InvalidArgumentException("value", "is required")
    return message["value"]


def validate_io_selector(runtime, io_selector):
    try:
        runtime.device_manager.io.slave_index(io_selector)
    except (TypeError, ValueError) as exception:
        raise ResourceNotFoundException("io", io_selector) from exception


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
        length = parse_sdo_int(message, "length")
        if length <= 0:
            raise InvalidArgumentException("length", "must be greater than 0")
        return length
    raw_type = str(message.get("data_type", "")).strip().lower()
    if raw_type.startswith("string(") and raw_type.endswith(")"):
        try:
            length = parse_int(raw_type[len("string("):-1], 0)
        except (TypeError, ValueError) as exception:
            raise InvalidArgumentException(
                "data_type",
                "contains an invalid string length",
            ) from exception
        if length <= 0:
            raise InvalidArgumentException(
                "data_type",
                "string length must be greater than 0",
            )
        return length
    raise InvalidArgumentException(
        "length",
        "is required for string SDO access",
    )


def read_sdo_value(sdo, selector, index, subindex, data_type, length):
    if data_type == "string":
        return sdo.read_string(selector, index, subindex, length)
    reader_name = SDO_READERS.get(data_type)
    if reader_name is None:
        raise InvalidArgumentException(
            "data_type",
            "is not a supported SDO data type",
            public_value=data_type,
        )
    return getattr(sdo, reader_name)(selector, index, subindex)


def write_sdo_value(sdo, selector, index, subindex, data_type, raw_value):
    if data_type == "string":
        value = str(raw_value)
        sdo.write_string(selector, index, subindex, value)
        return value
    writer_name = SDO_WRITERS.get(data_type)
    if writer_name is None:
        raise InvalidArgumentException(
            "data_type",
            "is not a supported SDO data type",
            public_value=data_type,
        )
    try:
        value = (
            float(raw_value)
            if data_type == "float32"
            else int(str(raw_value), 0)
        )
    except (TypeError, ValueError, OverflowError) as exception:
        raise InvalidArgumentException(
            "value",
            f"is invalid for {data_type}",
            public_value=raw_value,
        ) from exception
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
        raise UnsupportedOperationException(
            "io_ethercat_parameter_access",
            "Use the dedicated IO-Link ISDU command for this object",
        )


def is_cpx_isdu_access_object(index):
    index = int(index)
    return 0x2001 <= index <= 0x2FF1 and ((index - 0x2001) % 0x10) == 0


def save_parameters(message, runtime, client):
    response_type = public_command_name(message)
    axis_index = selected_single_axis(message, runtime, response_type)
    result = axis_device_profile(runtime, axis_index).save_parameters(
        runtime,
        axis_index,
    )
    return {"axis": axis_index, "result": result}
