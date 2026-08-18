import struct


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

    def _write(self, data_type, slave_index, index, subindex, value):
        payload = struct.pack(self._FORMATS[data_type], value)
        try:
            self.transport.write_sdo(slave_index, index, subindex, payload)
        except Exception as exc:
            raise RuntimeError(
                "SDO write failed: "
                f"slave={slave_index} object=0x{index:04X}:{subindex:02X} "
                f"type={data_type} value={value!r} payload={payload.hex()} "
                f"error={exc}"
            ) from exc

    def _read(self, data_type, slave_index, index, subindex):
        data_format = self._FORMATS[data_type]
        size = struct.calcsize(data_format)
        try:
            payload = self.transport.read_sdo(
                slave_index, index, subindex, size
            )
        except Exception as exc:
            raise RuntimeError(
                "SDO read failed: "
                f"slave={slave_index} object=0x{index:04X}:{subindex:02X} "
                f"type={data_type} size={size} error={exc}"
            ) from exc
        if len(payload) < size:
            raise RuntimeError(
                "SDO read returned a short payload: "
                f"slave={slave_index} object=0x{index:04X}:{subindex:02X} "
                f"type={data_type} expected={size} actual={len(payload)}"
            )
        return struct.unpack(data_format, payload[:size])[0]
