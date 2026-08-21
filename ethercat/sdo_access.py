import struct

from motion_server.failure import DeviceAccessException


class SdoAccess:
    """Typed CoE SDO access built on a master's raw SDO transport."""

    _FORMATS = {
        "int8": "<b",
        "uint8": "<B",
        "uint16": "<H",
        "int16": "<h",
        "int32": "<i",
        "uint32": "<I",
        "float32": "<f",
    }

    def __init__(self, transport):
        self.transport = transport

    def write_int8(self, slave_index, index, subindex, value):
        self._write("int8", slave_index, index, subindex, int(value))

    def write_uint8(self, slave_index, index, subindex, value):
        self._write("uint8", slave_index, index, subindex, int(value))

    def write_uint16(self, slave_index, index, subindex, value):
        self._write("uint16", slave_index, index, subindex, int(value))

    def write_int16(self, slave_index, index, subindex, value):
        self._write("int16", slave_index, index, subindex, int(value))

    def write_int32(self, slave_index, index, subindex, value):
        self._write("int32", slave_index, index, subindex, int(value))

    def write_uint32(self, slave_index, index, subindex, value):
        self._write("uint32", slave_index, index, subindex, int(value))

    def write_float32(self, slave_index, index, subindex, value):
        self._write("float32", slave_index, index, subindex, float(value))

    def write_string(self, slave_index, index, subindex, value):
        payload = encode_string_payload(value)
        self.transport.write_sdo(slave_index, index, subindex, payload)

    def read_int8(self, slave_index, index, subindex):
        return self._read("int8", slave_index, index, subindex)

    def read_uint8(self, slave_index, index, subindex):
        return self._read("uint8", slave_index, index, subindex)

    def read_uint16(self, slave_index, index, subindex):
        return self._read("uint16", slave_index, index, subindex)

    def read_int16(self, slave_index, index, subindex):
        return self._read("int16", slave_index, index, subindex)

    def read_int32(self, slave_index, index, subindex):
        return self._read("int32", slave_index, index, subindex)

    def read_uint32(self, slave_index, index, subindex):
        return self._read("uint32", slave_index, index, subindex)

    def read_float32(self, slave_index, index, subindex):
        return self._read("float32", slave_index, index, subindex)

    def read_string(self, slave_index, index, subindex, size):
        payload = self.transport.read_sdo(
            slave_index,
            index,
            subindex,
            int(size),
        )
        return decode_string_payload(payload)

    def _write(self, data_type, slave_index, index, subindex, value):
        payload = struct.pack(self._FORMATS[data_type], value)
        self.transport.write_sdo(slave_index, index, subindex, payload)

    def _read(self, data_type, slave_index, index, subindex):
        data_format = self._FORMATS[data_type]
        size = struct.calcsize(data_format)
        payload = self.transport.read_sdo(
            slave_index, index, subindex, size
        )
        if len(payload) < size:
            raise DeviceAccessException(
                operation="sdo_read_short_payload",
            )
        return struct.unpack(data_format, payload[:size])[0]


def encode_string_payload(value):
    return str(value).encode("ascii", errors="replace")


def decode_string_payload(payload):
    return bytes(payload).split(b"\x00", 1)[0].decode(
        "ascii",
        errors="replace",
    )
