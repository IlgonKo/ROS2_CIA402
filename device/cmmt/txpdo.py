from device.cmmt.pdo_configuration import (
    CMMT_PDO_CONFIGURATIONS,
    DEFAULT_PDO_CONFIGURATION,
)


class TxPDO:
    DEFAULT_CONFIGURATION = CMMT_PDO_CONFIGURATIONS[DEFAULT_PDO_CONFIGURATION]
    MAPPING_ITEMS = DEFAULT_CONFIGURATION.txpdo_items
    MAPPING_ENTRIES = DEFAULT_CONFIGURATION.txpdo_mapping_entries()

    def __init__(self, pdo_configuration=None):
        self.pdo_configuration = pdo_configuration or self.DEFAULT_CONFIGURATION
        self.mapping = self.pdo_configuration.txpdo_objects()
        self.mapped_fields = set()
        self.reset_values()

    def select_mapping(self, mapping_entries):
        if list(mapping_entries) == self.pdo_configuration.txpdo_mapping_entries():
            self.mapping = self.pdo_configuration.txpdo_objects()
        else:
            raise ValueError(
                "TxPDO mapping does not match selected CMMT PDO configuration."
            )
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
