import struct

from device.pdo_metadata import DATA_TYPE_FORMATS


_DATA_TYPE_ALIASES = {
    "BOOL": "bool",
    "USINT": "uint8",
    "BYTE": "uint8",
    "SINT": "int8",
    "UINT": "uint16",
    "WORD": "uint16",
    "INT": "int16",
    "UDINT": "uint32",
    "DWORD": "uint32",
    "DINT": "int32",
    "ULINT": "uint64",
    "LINT": "int64",
    "REAL": "float32",
}


def normalize_od_data_type(data_type):
    name = str(data_type).strip()
    return _DATA_TYPE_ALIASES.get(name.upper(), name.lower())


def encode_od_value(data_type, value, size=None):
    normalized = normalize_od_data_type(data_type)
    if "string" in normalized:
        payload = str(value).encode("ascii", errors="replace")
        return payload if size is None else payload[:int(size)]

    data_format = DATA_TYPE_FORMATS.get(normalized)
    if data_format is not None:
        if normalized != "float32":
            value = int(value)
        return struct.pack(data_format, value)

    if size is None:
        raise ValueError(f"OD data type {data_type!r} requires an explicit size")
    return int(value).to_bytes(
        int(size),
        "little",
        signed=int(value) < 0,
    )


def decode_od_value(data_type, payload):
    normalized = normalize_od_data_type(data_type)
    payload = bytes(payload)
    if "string" in normalized:
        return payload.split(b"\x00", 1)[0].decode("ascii", errors="replace")

    data_format = DATA_TYPE_FORMATS.get(normalized)
    if data_format is not None:
        size = struct.calcsize(data_format)
        return struct.unpack(data_format, payload[:size])[0]

    return int.from_bytes(payload, "little", signed=False)
