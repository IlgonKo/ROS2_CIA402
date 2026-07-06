from device.cmmt.object_dictionary import padding_object, pdo_object


class RxPDO:
    MAPPING_ENTRIES = [
        0x60400010,  # Controlword
        0x60600008,  # Mode of operation
        0x607A0020,  # Target position
        0x60810020,  # Profile velocity
        0x60FF0020,  # Target velocity
        0x60710010,  # Target torque
        0x60B10020,  # Velocity offset
        0x60B20010,  # Torque offset
        0x00000008,  # Padding
    ]

    def __init__(self):
        self.mapping = self.objects_from_mapping_entries(
            self.MAPPING_ENTRIES
        )
        self.mapped_fields = set()
        self.reset_values()

    def select_mapping(self, mapping_entries):
        self.mapping = self.objects_from_mapping_entries(mapping_entries)
        self.reset_values()

    def mapping_size(self):
        return sum(obj.byte_length for obj in self.mapping)

    def reset_values(self):
        for field in self.mapped_fields:
            if hasattr(self, field):
                delattr(self, field)
        self.mapped_fields = set()
        for obj in self.mapping:
            if obj.field is not None:
                setattr(self, obj.field, obj.default)
                self.mapped_fields.add(obj.field)

    def has_field(self, field):
        return field in self.mapped_fields

    @classmethod
    def objects_from_mapping_entries(cls, mapping_entries):
        objects = []
        for mapping_entry in mapping_entries:
            mapping_entry = int(mapping_entry)
            bit_length = mapping_entry & 0xFF
            if mapping_entry == 0:
                continue
            if (mapping_entry >> 8) == 0:
                objects.append(padding_object(bit_length))
                continue
            index = (mapping_entry >> 16) & 0xFFFF
            subindex = (mapping_entry >> 8) & 0xFF
            obj = pdo_object(index, subindex)
            if obj.bit_length != bit_length:
                raise ValueError(
                    "PDO mapping bit length mismatch for "
                    f"0x{index:04X}:{subindex:02X}. "
                    f"OD={obj.bit_length}, mapping={bit_length}"
                )
            objects.append(obj)
        return objects
