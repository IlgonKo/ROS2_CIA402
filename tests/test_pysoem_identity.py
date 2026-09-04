import unittest
from types import SimpleNamespace

from ethercat.pysoem_master import PySOEMMaster


class FakeIdentitySdo:
    def __init__(self, values):
        self.values = dict(values)
        self.reads = []

    def read_uint32(self, slave_index, index, subindex):
        self.reads.append((slave_index, index, subindex))
        return self.values[(index, subindex)]


class FakePdoCodec:
    @staticmethod
    def encode_rxpdo(rxpdo):
        return b""

    @staticmethod
    def decode_txpdo(payload, txpdo):
        return None


class FakeDeviceProfile:
    pdo_codec = FakePdoCodec

    def create_rxpdo(self):
        return SimpleNamespace()

    def create_txpdo(self):
        return SimpleNamespace()


def pysoem_master():
    return PySOEMMaster("adapter", device_profiles=[FakeDeviceProfile()])


class PysoemIdentityTest(unittest.TestCase):
    def test_zero_vendor_attribute_falls_back_to_identity_sdo(self):
        master = pysoem_master()
        master._master = SimpleNamespace(
            slaves=[
                SimpleNamespace(
                    man=0,
                    id=0x007B6451,
                    rev=0x00010000,
                    serial=0,
                ),
            ],
        )
        master.sdo = FakeIdentitySdo({
            (0x1018, 1): 0x0000001D,
        })

        identity = master.read_slave_identity(0)

        self.assertEqual(identity["vendor_id"], 0x0000001D)
        self.assertEqual(identity["product_code"], 0x007B6451)
        self.assertEqual(identity["revision"], 0x00010000)
        self.assertEqual(identity["serial_number"], 0)
        self.assertEqual(master.sdo.reads, [(0, 0x1018, 1)])

    def test_zero_product_and_revision_attributes_fall_back_to_identity_sdo(self):
        master = pysoem_master()
        master._master = SimpleNamespace(
            slaves=[
                SimpleNamespace(
                    man=0x0000001D,
                    id=0,
                    rev=0,
                    serial=0,
                ),
            ],
        )
        master.sdo = FakeIdentitySdo({
            (0x1018, 2): 0x007B6451,
            (0x1018, 3): 0x00010000,
        })

        identity = master.read_slave_identity(0)

        self.assertEqual(identity["vendor_id"], 0x0000001D)
        self.assertEqual(identity["product_code"], 0x007B6451)
        self.assertEqual(identity["revision"], 0x00010000)
        self.assertEqual(master.sdo.reads, [(0, 0x1018, 2), (0, 0x1018, 3)])


if __name__ == "__main__":
    unittest.main()
