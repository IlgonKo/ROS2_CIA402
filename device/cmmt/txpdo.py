from device.cmmt.object_dictionary import padding_object, pdo_object


class TxPDO:
    MAPPING_ENTRIES = [
        0x60410010,  # Statusword
        0x60610008,  # Mode of operation display
        0x60640020,  # Position actual value
        0x606C0020,  # Velocity actual value
        0x60770010,  # Torque actual value
        0x00000008,  # Padding
    ]   
    SETPOINT_REPLACE_ENTRIES = [
        0x60410010,  # Statusword
        0x60610008,  # Mode of operation display
        0x60620020,  # Position demand value / set-point position
        0x606C0020,  # Velocity actual value
        0x60770010,  # Torque actual value
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

    def reset_mapped_values(self):
        for obj in self.mapping:
            if obj.field is not None:
                setattr(self, obj.field, obj.default)
                self.mapped_fields.add(obj.field)

    def reset_values(self):
        for field in self.mapped_fields:
            if hasattr(self, field):
                delattr(self, field)
        self.mapped_fields = set()
        self.reset_mapped_values()

    def has_field(self, field):
        return field in self.mapped_fields

    def __getattr__(self, name):
        if name == "actual_position" and self.has_field("setpoint_position"):
            return self.setpoint_position
        if name == "setpoint_position" and self.has_field("actual_position"):
            return self.actual_position
        raise AttributeError(name)
    
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
