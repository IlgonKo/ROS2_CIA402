import os
from pathlib import Path
import importlib.util
import tempfile
import unittest
from unittest.mock import patch

from configuration import (
    DeviceRole,
    active_configuration,
    load_configuration,
    parse_bus_config,
    set_active_configuration,
)


WINDOWS_RUNTIME_PATH = (
    Path(__file__).resolve().parents[1] / "packaging" / "windows_runtime.py"
)
WINDOWS_RUNTIME_SPEC = importlib.util.spec_from_file_location(
    "motion_server_windows_runtime",
    WINDOWS_RUNTIME_PATH,
)
WINDOWS_RUNTIME = importlib.util.module_from_spec(WINDOWS_RUNTIME_SPEC)
WINDOWS_RUNTIME_SPEC.loader.exec_module(WINDOWS_RUNTIME)


AVAILABLE_PROFILES = {"cmmt_as", "cmmt_st", "cpx_ap_i_ec"}


class BusConfigTest(unittest.TestCase):
    def test_indexed_axis_io_bus_has_one_typed_interpretation(self):
        bus = parse_bus_config(
            "0: axis:cmmt-as, 1: io:cpx-ap-i-ec:station0, 2: cmmt-st",
            available_profiles=AVAILABLE_PROFILES,
        )

        self.assertEqual(
            bus.device_profile_names,
            ("cmmt_as", "cpx_ap_i_ec", "cmmt_st"),
        )
        self.assertEqual(bus.axis_slave_indices, (0, 2))
        self.assertEqual(bus.devices[0].role, DeviceRole.AXIS)
        self.assertEqual(bus.devices[1].role, DeviceRole.IO)
        self.assertEqual(bus.devices[1].logical_id, "station0")
        self.assertEqual(bus.devices[2].slave_index, 2)

    def test_unknown_role_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported.*role"):
            parse_bus_config(
                "module:cpx_ap_i_ec:io0",
                available_profiles=AVAILABLE_PROFILES,
            )

    def test_unknown_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported.*profile"):
            parse_bus_config(
                "axis:unknown_drive",
                available_profiles=AVAILABLE_PROFILES,
            )


class ConfigurationLoaderTest(unittest.TestCase):
    def tearDown(self):
        set_active_configuration(None)

    def make_project(self, root, filename):
        root = Path(root)
        (root / filename).write_text(
            "MOTION_SERVER_BUS=\\\n"
            "  0: axis:cmmt-as,\\\n"
            "  1: io:cpx-ap-i-ec:io0,\\\n"
            "  2: axis:cmmt-st\n"
            "MOTION_SERVER_DEVICE_CONFIG_ROOT=device\n"
            "COMMON_VALUE=project\n",
            encoding="utf-8",
        )
        for profile, value in (("cmmt", "drive"), ("cpx_ap_i_ec", "io")):
            profile_root = root / "device" / profile
            profile_root.mkdir(parents=True)
            (profile_root / filename).write_text(
                f"{profile.upper()}_VALUE={value}\n"
                "COMMON_VALUE=device\n",
                encoding="utf-8",
            )

    def test_device_defaults_common_values_and_environment_have_fixed_precedence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.make_project(temp_dir, ".env")
            model = load_configuration(
                temp_dir,
                environ={"COMMON_VALUE": "environment"},
                available_profiles=AVAILABLE_PROFILES,
            )

        self.assertEqual(model.value("CMMT_VALUE"), "drive")
        self.assertEqual(model.value("CPX_AP_I_EC_VALUE"), "io")
        self.assertEqual(model.value("COMMON_VALUE"), "environment")
        self.assertEqual(model.bus.axis_slave_indices, (0, 2))

    def test_unused_device_profile_file_is_not_loaded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".env").write_text(
                "MOTION_SERVER_BUS=axis:cmmt-as\n",
                encoding="utf-8",
            )
            unused_root = root / "device" / "cpx_ap_i_ec"
            unused_root.mkdir(parents=True)
            (unused_root / ".env").write_text(
                "UNUSED_DEVICE_VALUE=must-not-load\n",
                encoding="utf-8",
            )

            model = load_configuration(
                root,
                environ={},
                available_profiles=AVAILABLE_PROFILES,
            )

        self.assertNotIn("UNUSED_DEVICE_VALUE", model.values)

    def test_windows_entrypoint_uses_same_model_and_file_grammar(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.make_project(temp_dir, "config.txt")
            expected = load_configuration(
                temp_dir,
                project_filename="config.txt",
                device_filename="config.txt",
                environ={},
                available_profiles=AVAILABLE_PROFILES,
            )
            with patch.dict(os.environ, {}, clear=True):
                actual_values = WINDOWS_RUNTIME.load_axis_env(temp_dir)
                self.assertIsNotNone(active_configuration())

        self.assertEqual(actual_values, dict(expected.values))
        self.assertEqual(expected.bus.axis_slave_indices, (0, 2))


if __name__ == "__main__":
    unittest.main()
