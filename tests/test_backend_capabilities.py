import unittest

from device.capabilities import DeviceCapability, validate_device_capabilities
from device.cmmt.profile import CMMTASDeviceProfile
from ethercat.backend_contract import validate_staged_backend
from ethercat.mock_master import MockMaster
from ethercat.pysoem_master import PySOEMMaster


class EmptySlave:
    pass


class EmptyPdo:
    pass


class EmptyPdoCodec:
    @staticmethod
    def encode_rxpdo(rxpdo):
        return b""

    @staticmethod
    def decode_txpdo(payload, txpdo):
        return None


class EmptyProfile:
    pdo_codec = EmptyPdoCodec

    @staticmethod
    def create_rxpdo():
        return EmptyPdo()

    @staticmethod
    def create_txpdo():
        return EmptyPdo()

    @staticmethod
    def prepare_process_image(master, slave_index):
        return None


class RecordingSdo:
    def __init__(self):
        self.writes = []

    def write_uint8(self, axis_index, index, subindex, value):
        self.writes.append((axis_index, index, subindex, value))


class RecordingMaster:
    def __init__(self):
        self.sdo = RecordingSdo()


class BackendCapabilityTest(unittest.TestCase):
    def test_mock_master_enforces_staged_lifecycle_order(self):
        master = MockMaster(
            [EmptySlave()],
            device_profiles=[EmptyProfile()],
        )
        validate_staged_backend(master)

        with self.assertRaisesRegex(RuntimeError, "PRE-OP"):
            master.enter_operational()
        master.connect(target_state="preop")
        master.enter_operational()

        self.assertEqual(
            master.lifecycle_events,
            ["connect:preop", "enter_operational"],
        )

    def test_missing_lifecycle_method_is_rejected(self):
        class IncompleteBackend:
            def connect(self, target_state=None):
                pass

        with self.assertRaisesRegex(TypeError, "enter_operational"):
            validate_staged_backend(IncompleteBackend())

    def test_pysoem_master_implements_staged_lifecycle_contract(self):
        profile = CMMTASDeviceProfile(axis_index=0, slave_index=0)
        master = PySOEMMaster("unused", device_profiles=[profile])

        self.assertIs(validate_staged_backend(master), master)

    def test_axis_restart_capability_requires_complete_contract(self):
        class InvalidProfile:
            name = "invalid"
            capabilities = frozenset({DeviceCapability.AXIS_RESTART})

        with self.assertRaisesRegex(TypeError, "request_axis_restart"):
            validate_device_capabilities(InvalidProfile())

    def test_axis_restart_contract_does_not_require_write_helper(self):
        class RestartProfile:
            name = "restart"
            capabilities = frozenset({DeviceCapability.AXIS_RESTART})

            def request_axis_restart(self, master, axis_index):
                pass

            def clear_axis_restart_request(self, master, axis_index):
                pass

        self.assertEqual(
            validate_device_capabilities(RestartProfile()),
            frozenset({DeviceCapability.AXIS_RESTART}),
        )

    def test_axis_restart_request_writes_zero_then_one(self):
        profile = CMMTASDeviceProfile(axis_index=0, slave_index=0)
        master = RecordingMaster()

        result = profile.request_axis_restart(master, 2)

        self.assertEqual([write[3] for write in master.sdo.writes], [0, 1])
        self.assertEqual(result["command"], 1)

    def test_axis_restart_clear_writes_zero(self):
        profile = CMMTASDeviceProfile(axis_index=0, slave_index=0)
        master = RecordingMaster()

        result = profile.clear_axis_restart_request(master, 1)

        self.assertEqual([write[3] for write in master.sdo.writes], [0])
        self.assertEqual(result["command"], 0)


if __name__ == "__main__":
    unittest.main()
