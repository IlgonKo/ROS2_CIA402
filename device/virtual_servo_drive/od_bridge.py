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
        self._apply_write_side_effect(definition.role, value)

    def _sdo_definition(self, index, subindex):
        try:
            return self.od_model.definition(index, subindex)
        except KeyError as exception:
            raise SdoObjectNotFoundException(index, subindex) from exception

    def _update_rxpdo_field(self, definition, value):
        if definition.rxpdo and definition.role and self.rxpdo.has_field(definition.role):
            setattr(self.rxpdo, definition.role, value)

    def _apply_write_side_effect(self, role, value):
        if role == "device_reset_command" and int(value) == 1:
            self._restart_virtual_device()
        elif role == "parameter_save_command" and int(value) == 1:
            self.od_model.write_role("parameter_save_status", 0)
            self.od_model.write_role("parameter_save_return_code", 0)
            self.od_model.write_role("parameter_save_return_value", 1)

    def _restart_virtual_device(self):
        current_position = self.od_model.read_role("actual_position")
        self.od_model.reset_non_pdo_configuration()
        self.rxpdo.reset_values()
        self.txpdo.reset_values()
        if self.rxpdo.has_field("target_position"):
            self.rxpdo.target_position = current_position
        self.rxpdo_to_od()
        self.od_model.write_role("actual_position", current_position)
        self.od_model.write_role("statusword", 0x0027)
        self.od_model.write_role(
            "mode_of_operation_display",
            self.od_model.read_role("mode_of_operation"),
        )
        self.od_to_txpdo()

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
