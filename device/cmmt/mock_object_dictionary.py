from device.cmmt.object_dictionary import CMMT_OBJECTS


class MockObjectDictionary:
    def __init__(self):
        self.objects = {
            self._storage_key(index, subindex): obj.default
            for (index, subindex), obj in CMMT_OBJECTS.items()
        }

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
