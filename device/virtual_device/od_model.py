from dataclasses import dataclass, replace


@dataclass(frozen=True)
class VirtualOdDefinition:
    index: int
    subindex: int
    name: str
    data_type: str
    bit_size: int
    access: str = ""
    default: int | float | str | bytes = 0
    role: str | None = None
    rxpdo: bool = False
    txpdo: bool = False


@dataclass
class VirtualOdEntry:
    definition: VirtualOdDefinition
    value: int | float | str | bytes


class VirtualOdModel:
    """Object Dictionary definitions and runtime values for a virtual device."""

    def __init__(self):
        self.entries = {}
        self.last_write_key = None
        self.write_generation = 0
        self.objects = _RuntimeValueView(self)

    def define(
        self,
        index,
        subindex=0,
        *,
        name,
        data_type,
        bit_size,
        access="",
        default=0,
        role=None,
        rxpdo=False,
        txpdo=False,
    ):
        definition = VirtualOdDefinition(
            index=int(index),
            subindex=int(subindex or 0),
            name=str(name),
            data_type=str(data_type),
            bit_size=int(bit_size),
            access=str(access or ""),
            default=default,
            role=role,
            rxpdo=bool(rxpdo),
            txpdo=bool(txpdo),
        )
        self.entries[self._storage_key(index, subindex)] = VirtualOdEntry(
            definition,
            default,
        )
        return definition

    def overlay(self, index, subindex=0, **changes):
        key = self._storage_key(index, subindex)
        current = self.entries.get(key)
        if current is None:
            return self.define(index, subindex, **changes)
        supplied = {
            name: value
            for name, value in changes.items()
            if value not in (None, "")
        }
        definition = replace(current.definition, **supplied)
        value = changes["default"] if "default" in changes else current.value
        self.entries[key] = VirtualOdEntry(definition, value)
        return definition

    def definition(self, index, subindex=None):
        return self.entries[self._storage_key(index, subindex)].definition

    def definition_by_role(self, role):
        matches = [
            entry.definition
            for entry in self.entries.values()
            if entry.definition.role == role
        ]
        if len(matches) != 1:
            raise KeyError(
                f"Expected one OD definition for role {role!r}, "
                f"found {len(matches)}"
            )
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
        key = self._storage_key(index, subindex)
        self.entries[key].value = value
        self.last_write_key = key
        self.write_generation += 1

    def write_internal(self, index, value, subindex=None):
        self.entries[self._storage_key(index, subindex)].value = value

    def has_entry(self, index, subindex=None):
        return self._storage_key(index, subindex) in self.entries

    @staticmethod
    def default_value(data_type, bit_size):
        normalized = str(data_type or "").strip().lower()
        if "array" in normalized and "byte" in normalized:
            return bytes((int(bit_size) + 7) // 8)
        if normalized in {"byte_array", "octet_string"}:
            return bytes((int(bit_size) + 7) // 8)
        if "string" in normalized:
            return ""
        return 0

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
        return (
            self.od_model.read(*key)
            if isinstance(key, tuple)
            else self.od_model.read(key)
        )

    def __setitem__(self, key, value):
        if isinstance(key, tuple):
            self.od_model.write(key[0], value, key[1])
        else:
            self.od_model.write(key, value)

    def __contains__(self, key):
        return (
            self.od_model.has_entry(*key)
            if isinstance(key, tuple)
            else self.od_model.has_entry(key)
        )

    def __len__(self):
        return len(self.od_model.entries)
