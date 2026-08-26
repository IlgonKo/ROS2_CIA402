import struct

from motion_server.failure import (
    DeviceRejectedException,
    SdoObjectNotFoundException,
)


_INTEGER_TYPES = {
    "BOOL": (False, 1), "USINT": (False, 1), "BYTE": (False, 1),
    "SINT": (True, 1), "UINT": (False, 2), "WORD": (False, 2),
    "INT": (True, 2), "UDINT": (False, 4), "DWORD": (False, 4),
    "DINT": (True, 4), "ULINT": (False, 8), "LINT": (True, 8),
}
_TYPE_ALIASES = {
    "UINT8": "USINT", "INT8": "SINT", "UINT16": "UINT", "INT16": "INT",
    "UINT32": "UDINT", "INT32": "DINT", "UINT64": "ULINT", "INT64": "LINT",
}


class VirtualOdBridge:
    """Connect EtherCAT OD access and process images to one OD Model."""

    def __init__(self, od_model, rxpdo, txpdo):
        self.od_model = od_model
        self.rxpdo = rxpdo
        self.txpdo = txpdo

    def read(self, index, subindex=0):
        return self.od_model.read(index, subindex)

    def write(self, index, value, subindex=0):
        self.od_model.write(index, value, subindex)

    def read_sdo(self, index, subindex, size):
        definition = self._sdo_definition(index, subindex)
        return self._encode(definition.data_type, self.read(index, subindex), size)

    def write_sdo(self, index, subindex, payload):
        definition = self._sdo_definition(index, subindex)
        if definition.access.lower() == "ro":
            raise DeviceRejectedException("sdo_write")
        value = self._decode(definition.data_type, payload)
        self.write(index, value, subindex)
        self._update_rxpdo_field(definition, value)
        return definition, value

    def _sdo_definition(self, index, subindex):
        try:
            return self.od_model.definition(index, subindex)
        except KeyError as exception:
            raise SdoObjectNotFoundException(index, subindex) from exception

    def _update_rxpdo_field(self, definition, value):
        if definition.rxpdo and definition.role and self.rxpdo.has_field(definition.role):
            setattr(self.rxpdo, definition.role, value)

    @staticmethod
    def _normalized_type(data_type):
        name = str(data_type).strip().upper()
        return _TYPE_ALIASES.get(name, name)

    @classmethod
    def _decode(cls, data_type, payload):
        name = cls._normalized_type(data_type)
        if name == "REAL" or name == "FLOAT32":
            return struct.unpack("<f", bytes(payload[:4]))[0]
        if "STRING" in name:
            return bytes(payload).split(b"\x00", 1)[0].decode("ascii", errors="replace")
        signed, _size = _INTEGER_TYPES.get(name, (False, len(payload)))
        return int.from_bytes(payload, "little", signed=signed)

    @classmethod
    def _encode(cls, data_type, value, size):
        name = cls._normalized_type(data_type)
        if name == "REAL" or name == "FLOAT32":
            return struct.pack("<f", float(value))
        if "STRING" in name:
            return str(value).encode("ascii", errors="replace")[:int(size)]
        signed, _type_size = _INTEGER_TYPES.get(name, (int(value) < 0, int(size)))
        return int(value).to_bytes(int(size), "little", signed=signed)

    def rxpdo_to_od(self):
        for obj in self.rxpdo.mapping:
            if obj.index != 0 and obj.field is not None:
                self.write(obj.index, getattr(self.rxpdo, obj.field), obj.subindex)

    def od_to_txpdo(self):
        for obj in self.txpdo.mapping:
            if obj.index != 0 and obj.field is not None:
                setattr(self.txpdo, obj.field, self.read(obj.index, obj.subindex))
