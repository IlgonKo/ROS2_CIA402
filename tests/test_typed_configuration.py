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
from configuration.models import CmmtDeviceConfig, CpxApIEcDeviceConfig, ServerConfig
from configuration.builder import CliOverrides
from motion_server.app.startup import get_device_profile_for_device
from tests.configuration_fixtures import TEST_NON_PDO_SELECTION


AVAILABLE_PROFILES = {"cmmt_as", "cmmt_st", "cpx_ap_i_ec"}
class TypedConfigurationTest(unittest.TestCase):
    def test_legacy_server_motion_limit_overrides_are_absent(self):
        fields = CliOverrides.__dataclass_fields__
        for name in ("max_velocity", "acceleration", "deceleration", "jerk", "pp_jerk"):
            self.assertNotIn(name, fields)
        project_root = Path(__file__).resolve().parents[1]
        legacy_names = (
            "MOTION_SERVER_MAX_VELOCITY",
            "MOTION_SERVER_ACCELERATION",
            "MOTION_SERVER_DECELERATION",
            "MOTION_SERVER_JERK",
            "MOTION_SERVER_PP_JERK",
        )
        for relative_path in (
            ".env",
            ".env.example",
            "device/cmmt/.env",
            "device/cmmt/.env.example",
            "docker/motion_server/compose.yaml",
            "motion_server/start_server.sh",
        ):
            path = project_root / relative_path
            if path.name == ".env" and not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            for legacy_name in legacy_names:
                self.assertNotIn(legacy_name, text, relative_path)

    def test_motion_server_bind_host_is_fixed_outside_configuration(self):
        project_root = Path(__file__).resolve().parents[1]
        fields = CliOverrides.__dataclass_fields__
        server_fields = ServerConfig.__dataclass_fields__
        cli_text = (project_root / "configuration" / "cli.py").read_text(
            encoding="utf-8"
        )
        launcher_text = (project_root / "motion_server" / "start_server.sh").read_text(
            encoding="utf-8"
        )
        server_text = (project_root / "motion_server" / "server.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("host", fields)
        self.assertNotIn("host", server_fields)
        self.assertNotIn('add_argument("--host")', cli_text)
        self.assertNotIn("--host", launcher_text)
        self.assertIn('MOTION_SERVER_BIND_HOST = "0.0.0.0"', server_text)

    def test_motion_and_cmmt_settings_keep_their_owner_boundary(self):
        project_root = Path(__file__).resolve().parents[1]
        common = (project_root / ".env.example").read_text(encoding="utf-8")
        cmmt = (project_root / "device/cmmt/.env.example").read_text(encoding="utf-8")

        self.assertIn("MOTION_SERVER_MOTION_MODE=", common)
        self.assertNotIn("MOTION_SERVER_MOTION_MODE=", cmmt)
        self.assertNotIn("MOTION_SERVER_CSP_COUNTS_PER_UNIT", common + cmmt)
        self.assertIn("MOTION_SERVER_CSP_INTERPOLATION_MODE=", common)
        self.assertIn("MOTION_SERVER_CSP_VELOCITY_OFFSET=", common)
        self.assertNotIn("MOTION_SERVER_CSP_INTERPOLATION_MODE=", cmmt)
        self.assertNotIn("MOTION_SERVER_CSP_VELOCITY_OFFSET=", cmmt)
        self.assertIn("MOTION_SERVER_CMMT_PDO_CONFIGURATION=", cmmt)

    def write_project(self, root, extra=""):
        root = Path(root)
        (root / ".env").write_text(
            "MOTION_SERVER_BACKEND=mock\n"
            "MOTION_SERVER_BUS=0:axis:cmmt-as,1:io:cpx-ap-i-ec:io0,2:axis:cmmt-st\n"
            "MOTION_SERVER_IO_io0_MODULES=1:do:8,2:di:8\n"
            "MOTION_SERVER_IO_io0_MODULE_PDO_INDEX_STRIDE=0x0010\n"
            "MOTION_SERVER_CMMT_AXIS_PDO_CONFIGURATIONS=0:csp_basic,1:profile_position_basic\n"
            "MOTION_SERVER_CSP_INTERPOLATION_MODE=4\n"
            "MOTION_SERVER_PRE_LOGGING_ENABLED=1\n"
            "MOTION_SERVER_PRE_LOGGING_LENGTH=12\n"
            f"{TEST_NON_PDO_SELECTION}"
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
        self.assertEqual(config.server.bus_reconnect_timeout, 10.0)
        self.assertEqual(config.server.axis_restart_timeout, 30.0)
        self.assertFalse(config.server.simulation_api_enabled)
        self.assertFalse(config.server.expert_mode)
        self.assertIsInstance(config.devices[0].device, CmmtDeviceConfig)
        self.assertIsInstance(config.devices[1].device, CpxApIEcDeviceConfig)
        self.assertEqual(
            config.motion.csp_interpolation_mode,
            CspInterpolationMode.CSP_V,
        )
        self.assertEqual(config.devices[0].device.pdo_configuration, "csp_basic")
        self.assertEqual(
            config.devices[2].device.pdo_configuration,
            "profile_position_basic",
        )
        with self.assertRaises(FrozenInstanceError):
            config.server.port = 16000

    def test_simulation_api_requires_explicit_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self.load_typed(
                temp_dir,
                "MOTION_SERVER_SIMULATION_API_ENABLED=1\n",
            )

        self.assertTrue(config.server.simulation_api_enabled)

    def test_expert_mode_requires_hidden_explicit_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self.load_typed(
                temp_dir,
                "MOTION_SERVER_EXPERT_MODE=1\n",
            )

        self.assertTrue(config.server.expert_mode)

    def test_device_profiles_consume_typed_instance_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self.load_typed(temp_dir)

        cmmt_profile = get_device_profile_for_device(config.devices[0])
        cpx_profile = get_device_profile_for_device(config.devices[1])
        second_cmmt_profile = get_device_profile_for_device(config.devices[2])

        self.assertEqual(cmmt_profile.pdo_configuration.name, "csp_basic")
        self.assertEqual(
            second_cmmt_profile.pdo_configuration.name,
            "profile_position_basic",
        )
        self.assertEqual(cpx_profile.config.io_id, "io0")
        self.assertEqual(
            [module.module_type for module in cpx_profile.config.layout.modules],
            ["do", "di"],
        )
        self.assertEqual(cpx_profile.config.module_pdo_index_stride, 0x0010)

    def test_non_pdo_configuration_is_typed_and_selected_by_slave(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self.load_typed(temp_dir)

        first = config.devices[0].device.non_pdo_configuration
        second = config.devices[2].device.non_pdo_configuration
        self.assertEqual(first.name, "linear_mm")
        self.assertEqual(second.name, "rotary_deg")
        self.assertEqual(len(first.values), 20)
        self.assertEqual(
            next(value.value for value in first.values if value.index == 0x6098),
            37,
        )

    def test_slave_specific_non_pdo_selection_overrides_list(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self.load_typed(
                temp_dir,
                "MOTION_SERVER_CMMT_SLAVE_2_NON_PDO_CONFIGURATION=linear_mm\n",
            )

        self.assertEqual(
            config.devices[2].device.non_pdo_configuration.name,
            "linear_mm",
        )

    def test_mock_rejects_missing_non_pdo_selection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "slaves require.*2"):
                self.load_typed(
                    temp_dir,
                    "MOTION_SERVER_CMMT_SLAVE_NON_PDO_CONFIGURATIONS=0:linear_mm\n",
                )

    def test_rejects_unknown_non_pdo_selection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "Unsupported.*unknown"):
                self.load_typed(
                    temp_dir,
                    "MOTION_SERVER_CMMT_SLAVE_0_NON_PDO_CONFIGURATION=unknown\n",
                )

    def test_rejects_spin_wait_at_or_above_cycle_period(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "spin wait"):
                self.load_typed(
                    temp_dir,
                    "PYSOEM_CYCLE_TIME=0.001\nPYSOEM_SPIN_WAIT_TIME=0.001\n",
                )

    def test_rejects_non_positive_recovery_timeout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "Bus reconnect timeout"):
                self.load_typed(
                    temp_dir,
                    "MOTION_SERVER_BUS_RECONNECT_TIMEOUT=0\n",
                )
            with self.assertRaisesRegex(ValueError, "Axis restart timeout"):
                self.load_typed(
                    temp_dir,
                    "MOTION_SERVER_AXIS_RESTART_TIMEOUT=-1\n",
                )

    def test_rejects_unknown_csp_interpolation_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "CspInterpolationMode"):
                self.load_typed(
                    temp_dir,
                    "MOTION_SERVER_CSP_INTERPOLATION_MODE=3\n",
                )

    def test_keeps_but_does_not_validate_dc_details_when_dc_is_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self.load_typed(
                temp_dir,
                "PYSOEM_DC_ENABLED=0\n"
                "PYSOEM_DC_PHASE_LOCK=1\n"
                "PYSOEM_DC_ABSOLUTE_SHIFT=1\n",
            )

        self.assertFalse(config.ethercat.dc.enabled)
        self.assertTrue(config.ethercat.dc.phase_lock)
        self.assertTrue(config.ethercat.dc.absolute_shift)

    def test_rejects_absolute_shift_without_phase_lock(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "requires DC phase lock"):
                self.load_typed(
                    temp_dir,
                    "PYSOEM_DC_ENABLED=1\n"
                    "PYSOEM_DC_PHASE_LOCK=0\n"
                    "PYSOEM_DC_ABSOLUTE_SHIFT=1\n",
                )

    def test_rejects_unknown_initial_motion_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "Initial motion mode"):
                self.load_typed(
                    temp_dir,
                    "MOTION_SERVER_MOTION_MODE=typo\n",
                )

    def test_accepts_jog_as_initial_motion_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self.load_typed(
                temp_dir,
                "MOTION_SERVER_MOTION_MODE=jog\n",
            )

        self.assertEqual(config.motion.initial_motion_mode, "jog")

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
