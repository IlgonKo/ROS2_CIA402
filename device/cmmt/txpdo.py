from device.cmmt.object_dictionary import (
    padding,
    pdo_mapping_entries,
    pdo_objects_from_mapping_entries,
)


class TxPDO:
    MAPPING_ITEMS = [
        "statusword",
        "mode_of_operation_display",
        "actual_position",
        "actual_velocity",
        "actual_torque",
        padding(8),
    ]
    MAPPING_ENTRIES = pdo_mapping_entries(MAPPING_ITEMS)

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

    @classmethod
    def objects_from_mapping_entries(cls, mapping_entries):
        return pdo_objects_from_mapping_entries(mapping_entries)
