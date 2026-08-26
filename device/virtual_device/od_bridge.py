from device.od_value_codec import decode_od_value, encode_od_value
from motion_server.failure import (
    DeviceRejectedException,
    SdoObjectNotFoundException,
)


class VirtualOdBridge:
    """Connect mock SDO/PDO object access to one virtual OD model."""

    def __init__(self, od_model, pdo_configuration):
        self.od_model = od_model
        self.pdo_configuration = pdo_configuration

    def read_sdo(self, index, subindex, size):
        definition = self._definition(index, subindex)
        value = self.od_model.read(index, subindex)
        return encode_od_value(definition.data_type, value, size)

    def write_sdo(self, index, subindex, payload):
        definition = self._definition(index, subindex)
        if definition.access.lower() == "ro":
            raise DeviceRejectedException("sdo_write")
        value = decode_od_value(definition.data_type, payload)
        self.od_model.write(index, value, subindex)

    def rxpdo_payload_to_od(self, payload):
        payload = bytes(payload)
        offset = 0
        for obj in self.pdo_configuration.rxpdo_objects():
            end = offset + obj.byte_length
            if end > len(payload):
                raise ValueError(
                    "RxPDO payload is too small for configured OD mapping. "
                    f"Expected at least {end} bytes, got {len(payload)} bytes."
                )
            raw_value = payload[offset:end]
            offset = end
            if obj.index == 0 or obj.field is None:
                continue
            self.od_model.write(
                obj.index,
                decode_od_value(obj.data_type, raw_value),
                obj.subindex,
            )

    def od_to_txpdo_payload(self):
        payload = bytearray()
        for obj in self.pdo_configuration.txpdo_objects():
            if obj.index == 0 or obj.field is None:
                payload.extend(b"\x00" * obj.byte_length)
                continue
            payload.extend(
                encode_od_value(
                    obj.data_type,
                    self.od_model.read(obj.index, obj.subindex),
                    obj.byte_length,
                )
            )
        return bytes(payload)

    def _definition(self, index, subindex):
        try:
            return self.od_model.definition(index, subindex)
        except KeyError as exception:
            raise SdoObjectNotFoundException(index, subindex) from exception
