import unittest

from configuration import CspInterpolationMode
from configuration.models import CmmtDeviceConfig
from device.cmmt.pdo_configuration import get_pdo_configuration
from device.cmmt.profile import CMMTASDeviceProfile
from device.virtual_servo_drive.od_bridge import VirtualOdBridge
from device.virtual_servo_drive.od_model import VirtualObjectDictionary


class VirtualOdModelTest(unittest.TestCase):
    def test_esi_catalog_and_profile_metadata_build_one_od_model(self):
        profile = CMMTASDeviceProfile(axis_index=0, slave_index=0)
        od = VirtualObjectDictionary(profile)

        self.assertEqual(len(od.entries), len(profile.esi_catalog.objects))
        self.assertEqual(od.read(0x6041), 0x0040)
        self.assertTrue(od.definition(0x6041).txpdo)
        self.assertEqual(od.definition(0x216E, 1).access, "ro")

    def test_pdo_and_direct_od_access_share_runtime_value(self):
        profile = CMMTASDeviceProfile(axis_index=0, slave_index=0)
        od = VirtualObjectDictionary(profile)
        rxpdo = profile.create_rxpdo()
        txpdo = profile.create_txpdo()
        bridge = VirtualOdBridge(od, rxpdo, txpdo)

        rxpdo.target_position = 12345
        bridge.rxpdo_to_od()
        self.assertEqual(bridge.read(0x607A), 12345)

        bridge.write(0x6064, 54321)
        bridge.od_to_txpdo()
        self.assertEqual(txpdo.actual_position, 54321)

    def test_axis_specific_configuration_uses_real_profile_policy(self):
        def config(axis_index, pdo_configuration):
            return CmmtDeviceConfig(
                profile_name="cmmt_as",
                axis_index=axis_index,
                pdo_configuration=pdo_configuration,
                csp_interpolation_mode=CspInterpolationMode.CSP,
                csp_velocity_offset=False,
            )

        axis0 = CMMTASDeviceProfile(
            axis_index=0,
            slave_index=0,
            device_config=config(0, "profile_position_basic"),
        )
        axis1 = CMMTASDeviceProfile(
            axis_index=1,
            slave_index=1,
            device_config=config(1, "csp_basic"),
        )
        self.assertEqual(axis0.pdo_configuration.name, "profile_position_basic")
        self.assertEqual(axis1.pdo_configuration.name, "csp_basic")

    def test_invalid_configuration_is_a_startup_error(self):
        with self.assertRaisesRegex(ValueError, "Unsupported test configuration"):
            get_pdo_configuration("does_not_exist", context="test configuration")


if __name__ == "__main__":
    unittest.main()
