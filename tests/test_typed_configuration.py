from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
import unittest

from configuration import (
    BackendType,
    CspInterpolationMode,
    build_motion_server_config,
    load_configuration,
)
from configuration.models import CmmtDeviceConfig, CpxApIEcDeviceConfig


AVAILABLE_PROFILES = {"cmmt_as", "cmmt_st", "cpx_ap_i_ec"}


class TypedConfigurationTest(unittest.TestCase):
    def write_project(self, root, extra=""):
        root = Path(root)
        (root / ".env").write_text(
            "MOTION_SERVER_BACKEND=mock\n"
            "MOTION_SERVER_BUS=0:axis:cmmt-as,1:io:cpx-ap-i-ec:io0,2:axis:cmmt-st\n"
            "MOTION_SERVER_IO_io0_MODULES=1:do:8,2:di:8\n"
            "MOTION_SERVER_CMMT_AXIS_PDO_CONFIGURATIONS=0:csp_basic,1:profile_position_basic\n"
            "MOTION_SERVER_CSP_INTERPOLATION_MODE=4\n"
            "MOTION_SERVER_PRE_LOGGING_ENABLED=1\n"
            "MOTION_SERVER_PRE_LOGGING_LENGTH=12\n"
            f"{extra}",
            encoding="utf-8",
        )

    def load_typed(self, root, extra=""):
        self.write_project(root, extra)
        source = load_configuration(
            root,
            environ={},
            available_profiles=AVAILABLE_PROFILES,
        )
        return build_motion_server_config(source)

    def test_builds_immutable_typed_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self.load_typed(temp_dir)

        self.assertEqual(config.ethercat.backend, BackendType.MOCK)
        self.assertEqual(config.axis_count, 2)
        self.assertEqual(config.logging.pre_logging.length, 12)
        self.assertIsInstance(config.devices[0].device, CmmtDeviceConfig)
        self.assertIsInstance(config.devices[1].device, CpxApIEcDeviceConfig)
        self.assertEqual(
            config.devices[0].device.csp_interpolation_mode,
            CspInterpolationMode.CSP_V,
        )
        self.assertEqual(config.devices[0].device.pdo_configuration, "csp_basic")
        self.assertEqual(
            config.devices[2].device.pdo_configuration,
            "profile_position_basic",
        )
        with self.assertRaises(FrozenInstanceError):
            config.server.port = 16000

    def test_rejects_spin_wait_at_or_above_cycle_period(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "spin wait"):
                self.load_typed(
                    temp_dir,
                    "PYSOEM_CYCLE_TIME=0.001\nPYSOEM_SPIN_WAIT_TIME=0.001\n",
                )

    def test_rejects_unknown_csp_interpolation_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "CspInterpolationMode"):
                self.load_typed(
                    temp_dir,
                    "MOTION_SERVER_CSP_INTERPOLATION_MODE=3\n",
                )

    def test_rejects_enabled_pre_logging_without_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "pre-logging"):
                self.load_typed(
                    temp_dir,
                    "MOTION_SERVER_PRE_LOGGING_LENGTH=0\n",
                )

    def test_pysoem_requires_interface(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "requires an interface"):
                self.load_typed(
                    temp_dir,
                    "MOTION_SERVER_BACKEND=pysoem\nPYSOEM_INTERFACE=\n",
                )


if __name__ == "__main__":
    unittest.main()
