from dataclasses import dataclass, replace


@dataclass(frozen=True)
class VirtualOdDefinition:
    index: int
    subindex: int
    name: str
    data_type: str
    bit_size: int
    access: str = ""
    default: int | float | str = 0
    role: str | None = None
    rxpdo: bool = False
    txpdo: bool = False


@dataclass
class VirtualOdEntry:
    definition: VirtualOdDefinition
    value: int | float | str


class VirtualObjectDictionary:
    """Profile-defined virtual Object Dictionary and its runtime values."""

    def __init__(self, device_profile):
        self.device_profile = device_profile
        self.entries = {}
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
        self.objects = _RuntimeValueView(self)

    def _load_catalog(self, entries):
        for catalog_key, entry in entries:
            index, subindex = catalog_key
            key = self._storage_key(index, subindex)
            definition = VirtualOdDefinition(
                index=int(index),
                subindex=int(subindex),
                name=entry.name,
                data_type=entry.data_type,
                bit_size=int(entry.bit_size),
                access=getattr(entry, "access", ""),
                default=self._catalog_default(entry.data_type),
            )
            self.entries[key] = VirtualOdEntry(definition, definition.default)

    def _overlay_required_non_pdo_od(self, roles):
        for role in roles:
            self._overlay(
                role.index, role.subindex, name=role.name,
                data_type=role.data_type, access=role.access,
                role=role.role,
            )

    def _apply_non_pdo_configuration(self, configuration):
        if configuration is None:
            return
        for configured in configuration.values:
            key = self._storage_key(configured.index, configured.subindex)
            if key not in self.entries:
                raise ValueError(
                    "Non-PDO configuration references missing OD "
                    f"0x{configured.index:04X}:{configured.subindex:02X}"
                )
            self.entries[key].value = configured.value

    def reset_non_pdo_configuration(self):
        self._apply_non_pdo_configuration(
            self.device_profile.non_pdo_configuration
        )

    def _overlay_pdo(self, entries, direction):
        for entry in entries:
            if entry.index == 0:
                continue
            self._overlay(
                entry.index, entry.subindex, name=entry.name,
                data_type=entry.data_type, default=entry.default,
                role=entry.field, **{direction: True},
            )

    def _overlay(self, index, subindex, **changes):
        key = self._storage_key(index, subindex)
        current = self.entries.get(key)
        if current is None:
            bit_size = self.device_profile.expected_data_type_bits(changes["data_type"])
            definition = VirtualOdDefinition(
                index=int(index), subindex=int(subindex or 0),
                bit_size=bit_size, **changes,
            )
            self.entries[key] = VirtualOdEntry(definition, definition.default)
            return
        supplied = {name: value for name, value in changes.items() if value not in (None, "")}
        definition = replace(current.definition, **supplied)
        value = changes["default"] if "default" in changes else current.value
        self.entries[key] = VirtualOdEntry(definition, value)

    def definition(self, index, subindex=None):
        return self.entries[self._storage_key(index, subindex)].definition

    def definition_by_role(self, role):
        matches = [
            entry.definition
            for entry in self.entries.values()
            if entry.definition.role == role
        ]
        if len(matches) != 1:
            raise KeyError(f"Expected one OD definition for role {role!r}, found {len(matches)}")
        return matches[0]

    def write_role(self, role, value):
        definition = self.definition_by_role(role)
        self.write(definition.index, value, definition.subindex)

    def read_role(self, role):
        definition = self.definition_by_role(role)
        return self.read(definition.index, definition.subindex)

    def read(self, index, subindex=None):
        return self.entries[self._storage_key(index, subindex)].value

    def write(self, index, value, subindex=None):
        self.entries[self._storage_key(index, subindex)].value = value

    def has_entry(self, index, subindex=None):
        return self._storage_key(index, subindex) in self.entries

    @staticmethod
    def _catalog_default(data_type):
        return "" if "STRING" in str(data_type).upper() else 0

    @staticmethod
    def _storage_key(index, subindex=None):
        index = int(index)
        if subindex is None or int(subindex) == 0:
            return index
        return index, int(subindex)


class _RuntimeValueView:
    def __init__(self, od_model):
        self.od_model = od_model

    def __getitem__(self, key):
        return self.od_model.read(*key) if isinstance(key, tuple) else self.od_model.read(key)

    def __setitem__(self, key, value):
        if isinstance(key, tuple):
            self.od_model.write(key[0], value, key[1])
        else:
            self.od_model.write(key, value)

    def __contains__(self, key):
        return self.od_model.has_entry(*key) if isinstance(key, tuple) else self.od_model.has_entry(key)

    def __len__(self):
        return len(self.od_model.entries)
