import unittest

from device.cmmt.profile import CMMTASDeviceProfile
from device.virtual_servo_drive.servo_model import VirtualCiA402Servo
from ethercat.mock_master import MockMaster
from ethercat.mock_slave import MockSlave
from motion_server.control.axis import Axis


def create_virtual_axis_slave(axis_index=0):
    profile = CMMTASDeviceProfile(axis_index=axis_index, slave_index=axis_index)
    servo = VirtualCiA402Servo(device_profile=profile)
    return MockSlave(Axis(f"A{axis_index}", servo), profile.pdo_configuration, profile)


class GenericSlave:
    def __init__(self, value):
        self.value = int(value)

    def read_sdo(self, index, subindex, size):
        return self.value.to_bytes(size, "little")

    def write_sdo(self, index, subindex, payload):
        self.value = int.from_bytes(payload, "little")

    def process(self):
        pass


class MockMasterSdoTest(unittest.TestCase):
    def test_master_routes_raw_sdo_without_device_semantics(self):
        first = GenericSlave(10)
        second = GenericSlave(20)
        master = MockMaster([first, second])

        master.sdo.write_uint16(1, 0x7777, 3, 42)

        self.assertEqual(first.value, 10)
        self.assertEqual(master.sdo.read_uint16(1, 0x7777, 3), 42)

    def test_sdo_and_pdo_share_virtual_od_runtime_value(self):
        slave = create_virtual_axis_slave()
        master = MockMaster([slave])

        master.sdo.write_int32(0, 0x607A, 0, 12345)
        self.assertEqual(slave.axis.servo.od.read(0x607A), 12345)
        self.assertEqual(slave.rxpdo.target_position, 12345)

        slave.axis.servo.od.write(0x6064, -2345)
        slave.od_bridge.od_to_txpdo()
        self.assertEqual(master.sdo.read_int32(0, 0x6064, 0), -2345)
        self.assertEqual(slave.txpdo.actual_position, -2345)

    def test_float_and_signed_values_use_od_metadata(self):
        slave = create_virtual_axis_slave()
        master = MockMaster([slave])

        master.sdo.write_float32(0, 0x2183, 0x0C, -12.5)
        master.sdo.write_int8(0, 0x6060, 0, -3)

        self.assertAlmostEqual(master.sdo.read_float32(0, 0x2183, 0x0C), -12.5)
        self.assertEqual(master.sdo.read_int8(0, 0x6060, 0), -3)
        slave.process()
        self.assertEqual(master.sdo.read_int8(0, 0x6061, 0), -3)
        self.assertEqual(slave.txpdo.mode_of_operation_display, -3)

    def test_parameter_save_side_effect_is_owned_by_virtual_device(self):
        slave = create_virtual_axis_slave()
        master = MockMaster([slave])

        master.sdo.write_uint16(0, 0x2005, 0x03, 1)
        master.sdo.write_uint8(0, 0x2005, 0x01, 1)

        self.assertEqual(master.sdo.read_uint8(0, 0x2005, 0x02), 0)
        self.assertEqual(master.sdo.read_uint16(0, 0x2005, 0x04), 0)
        self.assertEqual(master.sdo.read_uint16(0, 0x2005, 0x05), 1)


if __name__ == "__main__":
    unittest.main()
