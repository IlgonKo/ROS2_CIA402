from device.cmmt.required_od import required_od_roles
from device.pdo_metadata import ObjectDictionaryEntry


class VirtualObjectDictionary:
    def __init__(self, device_profile):
        self.objects = {}
        device_profile.validate_catalog_support()
        self.load_entries(required_od_entry(role) for role in required_od_roles())
        self.load_entries(device_profile.pdo_configuration.rxpdo_objects())
        self.load_entries(device_profile.pdo_configuration.txpdo_objects())

    def load_entries(self, entries):
        for entry in entries:
            if entry.index == 0:
                continue
            self.objects.setdefault(
                self._storage_key(entry.index, entry.subindex),
                entry.default,
            )

    def read(self, index, subindex=None):
        return self.objects[self._storage_key(index, subindex)]

    def write(self, index, value, subindex=None):
        self.objects[self._storage_key(index, subindex)] = value

    @staticmethod
    def _storage_key(index, subindex=None):
        index = int(index)
        if subindex is None or int(subindex) == 0:
            return index
        return index, int(subindex)


def required_od_entry(role):
    return ObjectDictionaryEntry(
        role.index,
        role.subindex,
        role.name,
        role.data_type,
        default=role.default,
    )
