import unittest
from dataclasses import fields
import math
from unittest.mock import DEFAULT, patch

from configuration import CspInterpolationMode
from configuration.models import CmmtDeviceConfig
from device.cmmt.pdo_configuration import (
    CMMT_PDO_CONFIGURATIONS,
    get_pdo_configuration,
)
from device.cmmt.profile import CMMTASDeviceProfile
from device.virtual_servo_drive.od_bridge import VirtualOdBridge
from device.virtual_servo_drive.od_model import VirtualObjectDictionary
from device.cmmt.required_non_pdo_od import RequiredNonPdoOdRole
from device.cmmt.required_non_pdo_od import NON_PDO_CONFIGURATION_OD_ROLES
from device.cmmt.required_non_pdo_od import required_non_pdo_od_roles
from device.cmmt.non_pdo_configuration import (
    CMMT_NON_PDO_CONFIGURATIONS,
    NonPdoConfiguration,
    NonPdoOdValue,
)
from device.cmmt.esi_catalog import cmmt_catalog_by_profile_name
from motion_server.app.startup import (
    create_axis_runtime,
    read_startup_axis_sdo,
    refresh_axis_parameter_cache,
)
from motion_server.app.initialization import (
    InitializationCause,
    InitializationException,
)
from motion_server.handlers.command.axis_settings import (
    set_software_position_limits,
    update_axis_motion_limits,
    update_axis_profile_settings,
)
from motion_server.failure import OperationException


class VirtualOdModelTest(unittest.TestCase):
    def test_code_defined_non_pdo_presets_are_complete_and_catalog_valid(self):
        required = {
            (role.index, role.subindex): role
            for role in NON_PDO_CONFIGURATION_OD_ROLES
        }
        for configuration in CMMT_NON_PDO_CONFIGURATIONS.values():
            configured = {(item.index, item.subindex): item for item in configuration.values}
            self.assertEqual(set(configured), set(required), configuration.name)
            for address, role in required.items():
                value = configured[address].value
                if role.data_type == "float32":
                    self.assertTrue(math.isfinite(value))
                    self.assertLessEqual(abs(value), 3.4028235e38)
                else:
                    bits = int("".join(char for char in role.data_type if char.isdigit()))
                    minimum = 0 if role.data_type.startswith("uint") else -(1 << (bits - 1))
                    maximum = (1 << bits) - 1 if minimum == 0 else (1 << (bits - 1)) - 1
                    self.assertTrue(minimum <= value <= maximum, role.role)
                for profile_name in ("cmmt_as", "cmmt_st"):
                    entry = cmmt_catalog_by_profile_name(profile_name).object_info(*address)
                    expected_bits = int(
                        "".join(char for char in role.data_type if char.isdigit())
                    )
                    self.assertEqual(entry.bit_size, expected_bits)

    def test_required_non_pdo_contract_is_disjoint_from_all_pdo_mappings(self):
        required_addresses = {
            (role.index, role.subindex)
            for role in required_non_pdo_od_roles()
        }
        pdo_addresses = {
            (role.index, role.subindex)
            for configuration in CMMT_PDO_CONFIGURATIONS.values()
            for role in configuration.od_roles()
        }

        self.assertEqual(required_addresses & pdo_addresses, set())
        self.assertNotIn((0x6081, 0), required_addresses)

    def test_required_non_pdo_contract_does_not_own_runtime_default(self):
        self.assertNotIn("default", {field.name for field in fields(RequiredNonPdoOdRole)})

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

    def test_selected_non_pdo_configuration_initializes_runtime_values(self):
        def profile(unit, max_velocity):
            config = CmmtDeviceConfig(
                profile_name="cmmt_as",
                axis_index=0,
                pdo_configuration="motion_server_default",
                non_pdo_configuration=NonPdoConfiguration(
                    "test",
                    (
                        NonPdoOdValue(0x216E, 1, unit),
                        NonPdoOdValue(0x607F, 0, max_velocity),
                    ),
                ),
            )
            return CMMTASDeviceProfile(
                axis_index=0,
                slave_index=0,
                device_config=config,
            )

        linear = VirtualObjectDictionary(profile(0x0100, 200))
        rotary = VirtualObjectDictionary(profile(0x4100, 200000))

        self.assertEqual(linear.read(0x216E, 1), 0x0100)
        self.assertEqual(linear.read(0x607F), 200)
        self.assertEqual(rotary.read(0x216E, 1), 0x4100)
        self.assertEqual(rotary.read(0x607F), 200000)

        linear.write(0x607F, 999)
        self.assertEqual(linear.read(0x607F), 999)
        reset_linear = VirtualObjectDictionary(profile(0x0100, 200))
        self.assertEqual(reset_linear.read(0x607F), 200)

    def test_virtual_device_reset_restores_non_pdo_configuration(self):
        config = CmmtDeviceConfig(
            profile_name="cmmt_as",
            axis_index=0,
            pdo_configuration="motion_server_default",
            non_pdo_configuration=CMMT_NON_PDO_CONFIGURATIONS["linear_mm"],
        )
        profile = CMMTASDeviceProfile(
            axis_index=0,
            slave_index=0,
            device_config=config,
        )
        od_model = VirtualObjectDictionary(profile)
        bridge = VirtualOdBridge(
            od_model,
            profile.create_rxpdo(),
            profile.create_txpdo(),
        )
        od_model.write(0x607F, 999)

        bridge.write_sdo(0x2000, 1, b"\x01")

        self.assertEqual(od_model.read(0x607F), 200)

    def test_mock_runtime_does_not_overwrite_selected_motion_limits(self):
        from configuration.models import (
            BackendType,
            CycleConfig,
            DistributedClockConfig,
            EtherCATConfig,
            LoggingConfig,
            CommandLogConfig,
            StatusLogConfig,
            CycleStatsLogConfig,
            TrajectoryLogConfig,
            VelocityAnomalyLogConfig,
            PositionFeedbackLagLogConfig,
            CspCommandStepLogConfig,
            PreLoggingConfig,
            MotionConfig,
            CspProfile,
            BusDeviceConfig,
        )
        from configuration.bus import DeviceRole

        configured = CMMT_NON_PDO_CONFIGURATIONS["linear_mm"]
        device = CmmtDeviceConfig(
            "cmmt_as", 0, "motion_server_default", configured,
        )
        bus_device = BusDeviceConfig(0, DeviceRole.AXIS, "cmmt_as", None, device)
        ethercat = EtherCATConfig(
            BackendType.MOCK, "", None, CycleConfig(0.01, 0.0),
            DistributedClockConfig(False, 0, False, False, 0, 0.0, 0.0, 0.0),
        )
        motion = MotionConfig(
            "pp", CspProfile.QUINTIC, 100000.0,
            CspInterpolationMode.CSP, False,
        )
        logging = LoggingConfig(
            CommandLogConfig(False), StatusLogConfig(False, 1.0),
            CycleStatsLogConfig(False, 1.0),
            TrajectoryLogConfig(False, False),
            VelocityAnomalyLogConfig(False, 0.0, 0.0, 1.0),
            PositionFeedbackLagLogConfig(False, 1.0),
            CspCommandStepLogConfig(False, 0.0, 0.0),
            PreLoggingConfig(False, 0),
        )

        runtime = create_axis_runtime(ethercat, motion, logging, (bus_device,))

        self.assertEqual(runtime.slaves[0].servo.od.read(0x607F), 200)

    def test_mock_axis_restart_refreshes_cache_and_motion_controller(self):
        from configuration.models import (
            BackendType, BusDeviceConfig, CommandLogConfig, CspCommandStepLogConfig,
            CspProfile, CycleConfig, CycleStatsLogConfig, DistributedClockConfig,
            EtherCATConfig, LoggingConfig, MotionConfig, PositionFeedbackLagLogConfig,
            PreLoggingConfig, StatusLogConfig, TrajectoryLogConfig,
            VelocityAnomalyLogConfig,
        )
        from configuration.bus import DeviceRole

        device = CmmtDeviceConfig(
            "cmmt_as", 0, "motion_server_default",
            CMMT_NON_PDO_CONFIGURATIONS["linear_mm"],
        )
        ethercat = EtherCATConfig(
            BackendType.MOCK, "", None, CycleConfig(0.01, 0.0),
            DistributedClockConfig(False, 0, False, False, 0, 0.0, 0.0, 0.0),
        )
        motion = MotionConfig(
            "pp", CspProfile.QUINTIC, 100000.0,
            CspInterpolationMode.CSP, False,
        )
        logging = LoggingConfig(
            CommandLogConfig(False), StatusLogConfig(False, 1.0),
            CycleStatsLogConfig(False, 1.0), TrajectoryLogConfig(False, False),
            VelocityAnomalyLogConfig(False, 0.0, 0.0, 1.0),
            PositionFeedbackLagLogConfig(False, 1.0),
            CspCommandStepLogConfig(False, 0.0, 0.0), PreLoggingConfig(False, 0),
        )
        runtime = create_axis_runtime(
            ethercat, motion, logging,
            (BusDeviceConfig(0, DeviceRole.AXIS, "cmmt_as", None, device),),
        )
        profile = runtime.slaves[0].device_profile
        refresh_axis_parameter_cache(runtime, 0)
        profile.write_motion_limits(runtime, 0, 100, -100, 500, 500)
        refresh_axis_parameter_cache(runtime, 0)
        self.assertEqual(runtime.axis_parameters.motion_limits[0][0], 100)

        profile.request_axis_restart(runtime, 0)
        refresh_axis_parameter_cache(runtime, 0)

        self.assertEqual(runtime.axis_parameters.motion_limits[0][0], 200)
        self.assertEqual(runtime.slaves[0].motion_server_motion_limits[0], 200)
        self.assertAlmostEqual(runtime.motion_limits[0].max_velocity, 200.0, places=4)

    def test_partial_profile_write_resynchronizes_rxpdo_and_cache(self):
        runtime = self._create_linear_mock_runtime()
        refresh_axis_parameter_cache(runtime, 0)
        profile = runtime.slaves[0].device_profile

        def partial_write(master, axis_index, velocity, acceleration, deceleration):
            master.sdo.write_uint32(
                axis_index, profile.PROFILE_VELOCITY_INDEX, 0, int(velocity)
            )
            raise RuntimeError("acceleration write failed")

        with patch.object(profile, "write_profile_settings", side_effect=partial_write):
            with self.assertRaisesRegex(RuntimeError, "acceleration write failed"):
                update_axis_profile_settings(
                    runtime,
                    {"motion_modes": ["pp"]},
                    0,
                    123,
                    456,
                    789,
                )

        self.assertEqual(runtime.axis_parameters.profile_settings[0][0], 123)
        self.assertEqual(runtime.slaves[0].rxpdo.profile_velocity, 123)

    def test_partial_limit_writes_resynchronize_cache_and_control(self):
        runtime = self._create_linear_mock_runtime()
        refresh_axis_parameter_cache(runtime, 0)
        profile = runtime.slaves[0].device_profile
        state = {"axis_devices": runtime.device_manager.axes}

        def partial_motion(master, axis_index, positive, negative, acceleration, deceleration):
            master.sdo.write_uint32(
                axis_index, profile.MAX_PROFILE_VELOCITY_INDEX, 0, int(positive)
            )
            raise RuntimeError("negative velocity write failed")

        with patch.object(profile, "write_motion_limits", side_effect=partial_motion):
            with self.assertRaisesRegex(RuntimeError, "negative velocity write failed"):
                update_axis_motion_limits(runtime, state, 0, 123, -123, 456, 789)

        self.assertEqual(runtime.axis_parameters.motion_limits[0][0], 123)
        self.assertAlmostEqual(runtime.motion_limits[0].max_velocity, 200.0, places=4)

        def partial_software(master, axis_index, negative, positive):
            master.sdo.write_int32(
                axis_index, profile.SOFTWARE_POSITION_LIMIT_INDEX, 1, int(negative)
            )
            raise RuntimeError("positive limit write failed")

        with patch.object(
            profile, "write_software_position_limits", side_effect=partial_software
        ):
            with self.assertRaises(OperationException):
                set_software_position_limits(
                    {"axis": 0, "negative_limit": -10, "positive_limit": 10},
                    runtime,
                    state,
                    None,
                )

        self.assertEqual(
            runtime.axis_parameters.software_position_limits[0][0], -10000
        )

    @staticmethod
    def _create_linear_mock_runtime():
        from configuration.models import (
            BackendType, BusDeviceConfig, CommandLogConfig, CspCommandStepLogConfig,
            CspProfile, CycleConfig, CycleStatsLogConfig, DistributedClockConfig,
            EtherCATConfig, LoggingConfig, MotionConfig, PositionFeedbackLagLogConfig,
            PreLoggingConfig, StatusLogConfig, TrajectoryLogConfig,
            VelocityAnomalyLogConfig,
        )
        from configuration.bus import DeviceRole

        device = CmmtDeviceConfig(
            "cmmt_as", 0, "motion_server_default",
            CMMT_NON_PDO_CONFIGURATIONS["linear_mm"],
        )
        return create_axis_runtime(
            EtherCATConfig(
                BackendType.MOCK, "", None, CycleConfig(0.01, 0.0),
                DistributedClockConfig(False, 0, False, False, 0, 0.0, 0.0, 0.0),
            ),
            MotionConfig(
                "pp", CspProfile.QUINTIC, 100000.0,
                CspInterpolationMode.CSP, False,
            ),
            LoggingConfig(
                CommandLogConfig(False), StatusLogConfig(False, 1.0),
                CycleStatsLogConfig(False, 1.0), TrajectoryLogConfig(False, False),
                VelocityAnomalyLogConfig(False, 0.0, 0.0, 1.0),
                PositionFeedbackLagLogConfig(False, 1.0),
                CspCommandStepLogConfig(False, 0.0, 0.0),
                PreLoggingConfig(False, 0),
            ),
            (BusDeviceConfig(0, DeviceRole.AXIS, "cmmt_as", None, device),),
        )

    def test_optional_profile_and_motion_readback_use_safe_fallback(self):
        with (
            patch("motion_server.app.startup.read_axis_user_position_units", return_value=[0x0100]),
            patch("motion_server.app.startup.read_axis_converting_unit_exponents", return_value=[[6, 3, 3, 3]]),
            patch("motion_server.app.startup.read_axis_software_position_limits", return_value=[[-1, 1]]),
            patch("motion_server.app.startup.read_axis_profile_settings", return_value=[None]),
            patch("motion_server.app.startup.read_axis_motion_limits", return_value=[None]),
        ):
            values = read_startup_axis_sdo(object())

        self.assertEqual(values["profile_settings"], [[0.0, 0.0, 0.0, 0.0]])
        self.assertEqual(values["motion_limits"], [[0.0, 0.0, 0.0, 0.0]])

    def test_required_unit_readback_failure_stops_startup(self):
        cases = (
            ("read_axis_user_position_units", [None], "user position unit"),
            ("read_axis_converting_unit_exponents", [None], "converting unit"),
        )
        for function_name, failed_value, _expected_message in cases:
            with self.subTest(function_name=function_name), patch.multiple(
                "motion_server.app.startup",
                read_axis_user_position_units=DEFAULT,
                read_axis_converting_unit_exponents=DEFAULT,
                read_axis_software_position_limits=DEFAULT,
                read_axis_profile_settings=DEFAULT,
                read_axis_motion_limits=DEFAULT,
            ) as readers:
                readers["read_axis_user_position_units"].return_value = [0x0100]
                readers["read_axis_converting_unit_exponents"].return_value = [[6, 3, 3, 3]]
                readers["read_axis_software_position_limits"].return_value = [[-1, 1]]
                readers["read_axis_profile_settings"].return_value = [[1, 2, 3, 4]]
                readers["read_axis_motion_limits"].return_value = [[1, -1, 2, 2]]
                readers[function_name].return_value = failed_value

                with self.assertRaises(InitializationException) as raised:
                    read_startup_axis_sdo(object())
                self.assertIs(
                    raised.exception.cause,
                    InitializationCause.REQUIRED_PARAMETER_READ_FAILED,
                )

    def test_invalid_configuration_is_a_startup_error(self):
        with self.assertRaisesRegex(ValueError, "Unsupported test configuration"):
            get_pdo_configuration("does_not_exist", context="test configuration")


if __name__ == "__main__":
    unittest.main()
