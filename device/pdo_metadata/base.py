from dataclasses import dataclass
import struct

DATA_TYPE_FORMATS = {
    "bool": "<?",
    "uint8": "<B",
    "int8": "<b",
    "uint16": "<H",
    "int16": "<h",
    "uint32": "<I",
    "int32": "<i",
    "uint64": "<Q",
    "int64": "<q",
    "float32": "<f",
}

DATA_TYPE_BITS = {
    data_type: struct.calcsize(fmt) * 8
    for data_type, fmt in DATA_TYPE_FORMATS.items()
}
DATA_TYPE_BITS.update(
    {
        "visible_string": 0,
        "octet_string": 0,
        "unicode_string": 0,
        "byte_array": 0,
    }
)


@dataclass(frozen=True)
class ObjectDictionaryEntry:
    index: int
    subindex: int
    name: str
    data_type: str
    field: str | None = None
    default: int | float = 0

    @property
    def bit_length(self):
        if self.data_type.startswith("padding"):
            return int(self.data_type.removeprefix("padding"))
        return DATA_TYPE_BITS[self.data_type]

    @property
    def byte_length(self):
        return self.bit_length // 8

    def mapping_entry(self):
        return (self.index << 16) | (self.subindex << 8) | self.bit_length


def od_key(index, subindex=0):
    return int(index), int(subindex)


def padding_object(bit_length):
    return ObjectDictionaryEntry(
        0x0000,
        0x00,
        f"Padding {bit_length}",
        f"padding{bit_length}",
    )


@dataclass(frozen=True)
class PdoPadding:
    bit_length: int


def padding(bit_length):
    return PdoPadding(int(bit_length))


def pdo_object_from_dictionary(objects, index, subindex=0):
    return objects[od_key(index, subindex)]


def pdo_object_by_field(objects, field):
    matches = [
        obj
        for obj in objects.values()
        if obj.field == field
    ]
    if not matches:
        raise KeyError(f"Unknown PDO field: {field}")
    if len(matches) > 1:
        locations = ", ".join(
            f"0x{obj.index:04X}:{obj.subindex:02X}"
            for obj in matches
        )
        raise KeyError(f"Ambiguous PDO field {field!r}: {locations}")
    return matches[0]


def pdo_mapping_entry(objects, item):
    if isinstance(item, PdoPadding):
        return int(item.bit_length) & 0xFF
    if isinstance(item, str):
        return pdo_object_by_field(objects, item).mapping_entry()
    if isinstance(item, tuple):
        return pdo_object_from_dictionary(objects, *item).mapping_entry()
    return int(item)


def pdo_mapping_entries(objects, items):
    return [
        pdo_mapping_entry(objects, item)
        for item in items
    ]


def pdo_objects_from_mapping_entries(objects, mapping_entries):
    result = []
    for mapping_entry in mapping_entries:
        mapping_entry = int(mapping_entry)
        bit_length = mapping_entry & 0xFF
        if mapping_entry == 0:
            continue
        if (mapping_entry >> 8) == 0:
            result.append(padding_object(bit_length))
            continue
        index = (mapping_entry >> 16) & 0xFFFF
        subindex = (mapping_entry >> 8) & 0xFF
        obj = pdo_object_from_dictionary(objects, index, subindex)
        if obj.bit_length != bit_length:
            raise ValueError(
                "PDO mapping bit length mismatch for "
                f"0x{index:04X}:{subindex:02X}. "
                f"OD={obj.bit_length}, mapping={bit_length}"
            )
        result.append(obj)
    return result
