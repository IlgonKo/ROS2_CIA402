from device.virtual_device.od_model import VirtualOdModel


class VirtualObjectDictionary(VirtualOdModel):
    """CMMT profile-defined virtual Object Dictionary."""

    def __init__(self, device_profile):
        super().__init__()
        self.device_profile = device_profile
        device_profile.validate_catalog_support()
        self._load_catalog(device_profile.object_dictionary_entries())
        self._overlay_required_non_pdo_od(
            device_profile.required_non_pdo_od_roles()
        )
        self._apply_non_pdo_configuration(
            device_profile.non_pdo_configuration
        )
        self._overlay_pdo(device_profile.pdo_configuration.rxpdo_objects(), "rxpdo")
        self._overlay_pdo(device_profile.pdo_configuration.txpdo_objects(), "txpdo")

    def _load_catalog(self, entries):
        for catalog_key, entry in entries:
            index, subindex = catalog_key
            self.define(
                index,
                subindex,
                name=entry.name,
                data_type=entry.data_type,
                bit_size=entry.bit_size,
                access=getattr(entry, "access", ""),
                default=self.default_value(entry.data_type, entry.bit_size),
            )

    def _overlay_required_non_pdo_od(self, roles):
        for role in roles:
            self.overlay(
                role.index,
                role.subindex,
                name=role.name,
                data_type=role.data_type,
                bit_size=self.device_profile.expected_data_type_bits(
                    role.data_type
                ),
                access=role.access,
                role=role.role,
            )

    def _apply_non_pdo_configuration(self, configuration):
        if configuration is None:
            return
        for configured in configuration.values:
            if not self.has_entry(configured.index, configured.subindex):
                raise ValueError(
                    "Non-PDO configuration references missing OD "
                    f"0x{configured.index:04X}:{configured.subindex:02X}"
                )
            self.write_internal(
                configured.index,
                configured.value,
                configured.subindex,
            )

    def reset_non_pdo_configuration(self):
        self._apply_non_pdo_configuration(
            self.device_profile.non_pdo_configuration
        )

    def reset_pdo_values(self):
        for entry in self.entries.values():
            if entry.definition.rxpdo or entry.definition.txpdo:
                entry.value = entry.definition.default

    def _overlay_pdo(self, entries, direction):
        for entry in entries:
            if entry.index == 0:
                continue
            self.overlay(
                entry.index,
                entry.subindex,
                name=entry.name,
                data_type=entry.data_type,
                bit_size=entry.bit_length,
                default=entry.default,
                role=entry.field,
                **{direction: True},
            )
