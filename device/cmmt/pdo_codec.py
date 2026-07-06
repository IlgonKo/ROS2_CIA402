import struct

from device.cmmt.object_dictionary import (
    DATA_TYPE_FORMATS,
)


class CiA402PdoCodec:
    @classmethod
    def encode_rxpdo(cls, rxpdo):
        return cls.encode_mapping(rxpdo.mapping, rxpdo)

    @classmethod
    def decode_rxpdo(cls, payload, rxpdo):
        expected_size = rxpdo.mapping_size()
        if len(payload) < expected_size:
            raise ValueError(
                "RxPDO payload is too small. "
                f"Expected at least {expected_size} bytes, "
                f"got {len(payload)} bytes."
            )
        cls.decode_mapping(payload, rxpdo.mapping, rxpdo)

    @classmethod
    def decode_txpdo(cls, payload, txpdo):
        expected_size = txpdo.mapping_size()
        if len(payload) < expected_size:
            raise ValueError(
                "TxPDO payload is too small. "
                f"Expected at least {expected_size} bytes, "
                f"got {len(payload)} bytes."
            )
        txpdo.reset_mapped_values()
        cls.decode_mapping(payload, txpdo.mapping, txpdo)

    @classmethod
    def encode_mapping(cls, mapping, source):
        payload = bytearray()
        for obj in mapping:
            if obj.field is None:
                payload.extend(b"\x00" * obj.byte_length)
                continue
            payload.extend(cls.pack_value(obj.data_type, getattr(source, obj.field)))
        return bytes(payload)

    @classmethod
    def decode_mapping(cls, payload, mapping, target):
        offset = 0
        for obj in mapping:
            raw_value = payload[offset:offset + obj.byte_length]
            offset += obj.byte_length
            if obj.field is None:
                continue
            setattr(target, obj.field, cls.unpack_value(obj.data_type, raw_value))

    @classmethod
    def pack_value(cls, data_type, value):
        if data_type.startswith("padding"):
            bit_length = int(data_type.removeprefix("padding"))
            return b"\x00" * (bit_length // 8)
        if data_type != "float32":
            value = int(value)
        return struct.pack(DATA_TYPE_FORMATS[data_type], value)

    @classmethod
    def unpack_value(cls, data_type, payload):
        if data_type.startswith("padding"):
            return 0
        return struct.unpack(DATA_TYPE_FORMATS[data_type], bytes(payload))[0]
