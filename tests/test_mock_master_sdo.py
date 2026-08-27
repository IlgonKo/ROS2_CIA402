import unittest
from types import SimpleNamespace

from device.cmmt.profile import CMMTASDeviceProfile
from device.virtual_servo_drive.servo_model import VirtualCiA402Servo
from ethercat.mock_master import MockMaster
from ethercat.mock_slave import MockSlave
from motion_server.failure import (
    DeviceRejectedException,
    SdoObjectNotFoundException,
)


def create_virtual_axis(axis_index=0, pdo_configuration=None):
    device_config = None
    if pdo_configuration is not None:
        device_config = SimpleNamespace(
            pdo_configuration=pdo_configuration,
            non_pdo_configuration=None,
        )
    profile = CMMTASDeviceProfile(
        axis_index=axis_index,
        slave_index=axis_index,
        device_config=device_config,
    )
    servo = VirtualCiA402Servo(device_profile=profile)
    return profile, MockSlave(servo, profile.pdo_configuration)


def create_virtual_axis_master(axis_index=0, pdo_configuration=None):
    profile, endpoint = create_virtual_axis(axis_index, pdo_configuration)
    master = MockMaster([endpoint], device_profiles=[profile])
    return master, endpoint


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


class GenericSlave:
    def __init__(self, value):
        self.value = int(value)

    def read_sdo(self, index, subindex, size):
        return self.value.to_bytes(size, "little")

    def write_sdo(self, index, subindex, payload):
        self.value = int.from_bytes(payload, "little")

class MockMasterSdoTest(unittest.TestCase):
    def test_preop_connect_writes_and_reads_back_configured_pdo_mapping(self):
        master, endpoint = create_virtual_axis_master()
        profile = master.slaves[0].device_profile

        self.assertEqual(endpoint.virtual_device.od.read(0x1C12, 0), 0)
        self.assertEqual(endpoint.virtual_device.od.read(0x1C13, 0), 0)

        master.connect(target_state="preop")

        self.assertEqual(master.sdo.read_uint8(0, 0x1C12, 0), 1)
        self.assertEqual(master.sdo.read_uint16(0, 0x1C12, 1), 0x1600)
        self.assertEqual(master.sdo.read_uint8(0, 0x1C13, 0), 1)
        self.assertEqual(master.sdo.read_uint16(0, 0x1C13, 1), 0x1A00)
        self.assertEqual(
            master.read_assigned_pdo_mapping_entries(0, 0x1C12),
            profile.expected_rxpdo_mapping_entries(),
        )
        self.assertEqual(
            master.read_assigned_pdo_mapping_entries(0, 0x1C13),
            profile.expected_txpdo_mapping_entries(),
        )

    def test_preop_identity_mismatch_closes_mock_transport(self):
        master, endpoint = create_virtual_axis_master()
        endpoint.read_identity = lambda: {
            "product_code": 0xDEADBEEF,
            "revision": 0,
        }

        with self.assertRaisesRegex(RuntimeError, "profile mismatch"):
            master.connect(target_state="preop")

        self.assertFalse(master.transport_available())
        self.assertEqual(master.lifecycle_events, ["connect:preop", "close"])

    def test_preop_connect_uses_selected_pdo_configuration(self):
        master, _endpoint = create_virtual_axis_master(
            pdo_configuration="csp_basic",
        )
        profile = master.slaves[0].device_profile

        master.connect(target_state="preop")

        self.assertEqual(
            master.read_assigned_pdo_mapping_entries(0, 0x1C12),
            profile.pdo_configuration.rxpdo_mapping_entries(),
        )
        self.assertEqual(
            master.read_assigned_pdo_mapping_entries(0, 0x1C13),
            profile.pdo_configuration.txpdo_mapping_entries(),
        )
        self.assertFalse(master.slaves[0].rxpdo.has_field("profile_velocity"))

    def test_master_routes_raw_sdo_without_device_semantics(self):
        first = GenericSlave(10)
        second = GenericSlave(20)
        master = MockMaster(
            [first, second],
            device_profiles=[EmptyProfile(), EmptyProfile()],
        )

        master.sdo.write_uint16(1, 0x7777, 3, 42)

        self.assertEqual(first.value, 10)
        self.assertEqual(master.sdo.read_uint16(1, 0x7777, 3), 42)

    def test_sdo_write_does_not_mutate_master_rxpdo_image(self):
        master, endpoint = create_virtual_axis_master()

        master.sdo.write_uint32(0, 0x6081, 0, 12345)
        self.assertEqual(endpoint.virtual_device.od.read(0x6081), 12345)
        self.assertEqual(master.slaves[0].rxpdo.profile_velocity, 0)

    def test_od_bridge_publishes_od_state_to_txpdo(self):
        master, endpoint = create_virtual_axis_master()

        endpoint.virtual_device.od.write(0x6064, -2345)
        txpdo_payload = endpoint.od_bridge.od_to_txpdo_payload()
        payload = master.slaves[0].validate_input_payload(txpdo_payload)
        master.slaves[0].decode_input(payload)
        self.assertEqual(master.sdo.read_int32(0, 0x6064, 0), -2345)
        self.assertEqual(master.slaves[0].txpdo.actual_position, -2345)

    def test_float_and_signed_values_use_od_metadata(self):
        master, _endpoint = create_virtual_axis_master()

        master.sdo.write_float32(0, 0x2183, 0x0C, -12.5)
        master.sdo.write_int8(0, 0x6060, 0, -3)

        self.assertAlmostEqual(master.sdo.read_float32(0, 0x2183, 0x0C), -12.5)
        self.assertEqual(master.sdo.read_int8(0, 0x6060, 0), -3)

        # The next cyclic RxPDO replaces an SDO write to an RxPDO-mapped object,
        # matching the behavior of a real slave.
        master.connect(target_state="preop")
        master.prepare_processdata()
        master.send_processdata()
        master.receive_processdata()
        self.assertEqual(master.sdo.read_int8(0, 0x6060, 0), 8)
        self.assertEqual(master.sdo.read_int8(0, 0x6061, 0), 8)
        self.assertEqual(master.slaves[0].txpdo.mode_of_operation_display, 8)

    def test_parameter_save_side_effect_is_owned_by_virtual_device(self):
        master, _endpoint = create_virtual_axis_master()

        master.sdo.write_uint16(0, 0x2005, 0x03, 1)
        master.sdo.write_uint8(0, 0x2005, 0x01, 1)

        self.assertEqual(master.sdo.read_uint8(0, 0x2005, 0x02), 0)
        self.assertEqual(master.sdo.read_uint16(0, 0x2005, 0x04), 0)
        self.assertEqual(master.sdo.read_uint16(0, 0x2005, 0x05), 1)

    def test_virtual_od_reports_missing_sdo_object(self):
        master, _endpoint = create_virtual_axis_master()

        with self.assertRaises(SdoObjectNotFoundException) as caught:
            master.sdo.read_uint16(0, 0x7777, 3)

        self.assertEqual(caught.exception.index, 0x7777)
        self.assertEqual(caught.exception.subindex, 3)
        self.assertIsInstance(caught.exception.__cause__, KeyError)

    def test_virtual_od_reports_read_only_write_as_device_reject(self):
        master, _endpoint = create_virtual_axis_master()

        with self.assertRaises(DeviceRejectedException):
            master.sdo.write_int32(0, 0x6064, 0, 1)


if __name__ == "__main__":
    unittest.main()
