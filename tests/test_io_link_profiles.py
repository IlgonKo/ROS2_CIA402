from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from configuration.builder import build_cpx_config
from configuration.models import IoLinkPortConfig
from device.cpx_ap_i_ec.io_config import build_cpx_io_config
from device.cpx_ap_i_ec.profile import CPXApIEcDeviceProfile
from device.exceptions import DeviceLayoutInvalidException
from device.io_link.iodd_catalog import (
    IoddDeviceInfo, iodd_device_info, parse_process_data_profiles,
)
from motion_server.handlers.status.io_iol_parameter_catalog import iodd_device_to_dict


def sample_device():
    # Deliberately reverse lexical/size order: the XML order is the default.
    profiles = parse_process_data_profiles(ET.fromstring('''
        <Device xmlns="urn:sample:iodd"><ProcessDataCollection>
          <ProcessData id="Z_First"><Condition variableId="mode" value="7"/>
            <ProcessDataIn bitLength="25"/></ProcessData>
          <ProcessData id="A_Large"><Condition variableId="mode" value="240"/>
            <ProcessDataIn bitLength="128"/>
            <ProcessDataOut bitLength="64"/></ProcessData>
          <ProcessData id="Same_Size"><Condition variableId="mode" value="0"/>
            <ProcessDataIn bitLength="25"/></ProcessData>
        </ProcessDataCollection></Device>
    '''))
    return IoddDeviceInfo("sample", Path("sample.xml"), 1, 2, "Vendor", "Device", profiles, ())


class IoLinkProfileTest(unittest.TestCase):
    def test_two_and_three_field_declarations_round_trip(self):
        for text, expected in (
            ("0:sample", IoLinkPortConfig("0", "sample")),
            (" iol1.2 : sample : 240 ", IoLinkPortConfig("iol1.2", "sample", 240)),
            ("3.1:sample:7", IoLinkPortConfig("3.1", "sample", 7)),
            ("0:sample:0", IoLinkPortConfig("0", "sample", 0)),
        ):
            with self.subTest(text=text):
                parsed = IoLinkPortConfig.from_declaration(text)
                self.assertEqual(parsed, expected)
                self.assertEqual(IoLinkPortConfig.from_declaration(parsed.to_declaration()), expected)

    def test_malformed_declarations_rejected(self):
        for text in ("0", ":sample", "0:sample:", "0:sample:2:extra", "0:none:2", "0::2",
                     "0:sample:A_Large", "0:sample:2.5", "0:sample:-1"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                IoLinkPortConfig.from_declaration(text)

    def test_default_is_first_xml_profile_even_with_different_sizes(self):
        device = sample_device()
        self.assertEqual(device.select_process_data_profile().profile_id, "Z_First")
        self.assertEqual(device.process_data_size, (4, 0))
        self.assertEqual(device.select_process_data_profile(240).input_bytes, 16)
        self.assertEqual(device.select_process_data_profile(0).profile_id, "Same_Size")
        self.assertEqual(device.select_process_data_profile().condition_value, 7)

    def test_missing_unknown_and_ambiguous_profile_rejected(self):
        device = sample_device()
        for value in (1, 2, 999):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "available: 7 .*240"):
                device.select_process_data_profile(value)
        with self.assertRaisesRegex(ValueError, "no process data profiles"):
            replace(device, process_data_profiles=()).select_process_data_profile()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            replace(device, process_data_profiles=device.process_data_profiles * 2).select_process_data_profile(7)

    def test_names_and_non_integer_selectors_are_rejected(self):
        for value in ("A_Large", "240", 240.0, True, -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                sample_device().select_process_data_profile(value)

    def test_unconditional_profile_is_default_only(self):
        device = sample_device()
        unconditional = replace(device.process_data_profiles[0], condition_value=None)
        device = replace(device, process_data_profiles=(unconditional,))
        self.assertIs(device.select_process_data_profile(), unconditional)
        with self.assertRaisesRegex(ValueError, "omit the profile"):
            device.select_process_data_profile(0)

    def test_bindings_keep_independent_profiles_and_infer_variant(self):
        device = sample_device()
        with patch("device.cpx_ap_i_ec.io_config.iodd_device_info", return_value=device):
            config = build_cpx_io_config("io0", "1:iol:4", "0:sample,1:sample:240")
            small = build_cpx_io_config("io0", "1:iol:4", "0:sample")
        first, second = config.io_link_devices
        self.assertIs(first.device, second.device)
        self.assertEqual(first.process_data_size, (4, 0))
        self.assertEqual(second.process_data_size, (16, 8))
        self.assertEqual(config.output_bytes, 64)
        self.assertEqual(small.output_bytes, 16)
        self.assertEqual(device.process_data_size, (4, 0))
        for binding, expected in ((first, 7), (second, 240)):
            for snapshot in (binding.to_dict(), iodd_device_to_dict(binding)):
                self.assertEqual(snapshot["process_data_profile"], expected)
                self.assertEqual(snapshot["process_data_profile_id"], binding.process_data_profile.profile_id)
                self.assertEqual((snapshot["input_bytes"], snapshot["output_bytes"]), binding.process_data_size)

    def test_typed_configuration_reaches_device_profile(self):
        with patch("device.cpx_ap_i_ec.io_config.iodd_device_info", return_value=sample_device()):
            config = build_cpx_config({
                "MOTION_SERVER_IO_io0_MODULES": "1:iol:4",
                "MOTION_SERVER_IO_io0_IOL_PORTS": "0:sample:240,1:sample",
            }, SimpleNamespace(logical_id="io0", profile="cpx_ap_i_ec"))
            self.assertEqual(config.io_link_ports[0].process_data_profile, 240)
            self.assertIsNone(config.io_link_ports[1].process_data_profile)
            profile = CPXApIEcDeviceProfile(device_config=config)
        self.assertEqual(profile.config.io_link_devices[0].process_data_size, (16, 8))
        self.assertEqual(profile.config.io_link_devices[1].process_data_size, (4, 0))

    def test_unknown_profile_is_a_device_model_build_failure(self):
        config = build_cpx_config({
            "MOTION_SERVER_IO_io0_MODULES": "1:iol:4",
            "MOTION_SERVER_IO_io0_IOL_PORTS": "0:sample:999",
        }, SimpleNamespace(logical_id="io0", profile="cpx_ap_i_ec"))
        with patch("device.cpx_ap_i_ec.io_config.iodd_device_info", return_value=sample_device()):
            with self.assertRaises(DeviceLayoutInvalidException) as caught:
                CPXApIEcDeviceProfile(device_config=config)
        self.assertIn("999", str(caught.exception.__cause__))

    def test_multiple_module_selectors_and_none_remain_supported(self):
        with patch("device.cpx_ap_i_ec.io_config.iodd_device_info", return_value=sample_device()):
            config = build_cpx_io_config(
                "io0", "1:iol:4,3:iol:4", "iol0.0:sample,3.2:sample:240,iol1.3:none",
            )
        self.assertEqual([(b.module, b.port) for b in config.io_link_devices], [(1, 0), (3, 2)])

    def test_duplicate_and_out_of_range_ports_remain_rejected(self):
        with patch("device.cpx_ap_i_ec.io_config.iodd_device_info", return_value=sample_device()):
            for raw in ("0:sample,0:sample:240", "4:sample:240"):
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    build_cpx_io_config("io0", "1:iol:4", raw)

    def test_explicit_module_name_resolves_binding_and_checks_capacity(self):
        with patch("device.cpx_ap_i_ec.io_config.iodd_device_info", return_value=sample_device()):
            config = build_cpx_io_config("io0", "1:CPX-AP-I-4IOL-M12 Variant 32", "0:sample:240")
            self.assertEqual(config.io_link_devices[0].process_data_profile.profile_id, "A_Large")
            with self.assertRaisesRegex(ValueError, "does not fit"):
                build_cpx_io_config("io0", "1:iol:4:in16:out16", "0:sample:240")

    def test_bundled_iodd_default_and_explicit_profile(self):
        key = "Balluff_BCM_R16E_004_CI01"
        device = iodd_device_info(key)
        config = build_cpx_io_config("io0", "1:iol:4", f"0:{key},1:{key}:2,2:{key}:240")
        self.assertEqual(config.io_link_devices[0].process_data_profile.profile_id, "P_Vibration_Veloc")
        self.assertEqual(config.io_link_devices[1].process_data_profile.profile_id, "P_Vibration_Accel")
        self.assertEqual(config.io_link_devices[1].to_dict()["process_data_profile"], 2)
        self.assertEqual(config.io_link_devices[2].process_data_profile.profile_id, "P_Custom_Profile")
        self.assertEqual(config.output_bytes, 128)
        self.assertEqual(device.process_data_size, (32, 3))


if __name__ == "__main__":
    unittest.main()
