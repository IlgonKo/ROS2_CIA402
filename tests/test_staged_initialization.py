import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from motion_server.app.initialization import (
    INITIALIZATION_CAUSE_DEFINITIONS,
    InitializationCause,
    InitializationException,
    InitializationStage,
    initialization_failure_from_exception,
)
from motion_server.app.startup import (
    build_device_models,
    close_initialization_resource,
    connect_bus,
    create_axis_runtime,
    initialize_drive,
)
from device.exceptions import (
    DeviceLayoutInvalidException,
    PdoCatalogMismatchException,
)


OCCURRED_AT = datetime(2026, 8, 25, 4, 0, tzinfo=timezone.utc)


class InitializationExceptionMappingTest(unittest.TestCase):
    def failure(self, stage, exception):
        return initialization_failure_from_exception(
            stage,
            exception,
            occurred_at=OCCURRED_AT,
        )

    def test_configuration_validation_and_unexpected_failure_are_distinct(self):
        invalid = self.failure(
            InitializationStage.CONFIGURATION,
            ValueError("invalid setting"),
        )
        failed = self.failure(
            InitializationStage.CONFIGURATION,
            OSError("private file detail"),
        )

        self.assertIs(invalid.cause, InitializationCause.CONFIGURATION_INVALID)
        self.assertIs(failed.cause, InitializationCause.CONFIGURATION_FAILED)

    def test_device_model_uses_specific_typed_cause_or_stage_fallback(self):
        specific = self.failure(
            InitializationStage.DEVICE_MODEL_BUILD,
            InitializationException(InitializationCause.PDO_CATALOG_MISMATCH),
        )
        fallback = self.failure(
            InitializationStage.DEVICE_MODEL_BUILD,
            RuntimeError("private builder failure"),
        )

        self.assertIs(specific.cause, InitializationCause.PDO_CATALOG_MISMATCH)
        self.assertIs(
            fallback.cause,
            InitializationCause.DEVICE_MODEL_BUILD_FAILED,
        )

    def test_runtime_bus_and_device_stages_have_stable_fallbacks(self):
        expected = {
            InitializationStage.RUNTIME_CREATION: (
                InitializationCause.RUNTIME_CREATION_FAILED
            ),
            InitializationStage.BUS_CONNECTION: (
                InitializationCause.BUS_CONNECTION_FAILED
            ),
            InitializationStage.DEVICE_INITIALIZATION: (
                InitializationCause.DEVICE_INITIALIZATION_FAILED
            ),
        }

        for stage, cause in expected.items():
            with self.subTest(stage=stage):
                failure = self.failure(stage, RuntimeError("private detail"))
                self.assertIs(failure.cause, cause)
                self.assertEqual(
                    failure.message,
                    INITIALIZATION_CAUSE_DEFINITIONS[cause].message,
                )
                self.assertNotIn("private detail", failure.message)

    def test_typed_cause_must_match_current_stage(self):
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            self.failure(
                InitializationStage.BUS_CONNECTION,
                InitializationException(
                    InitializationCause.REQUIRED_PARAMETER_READ_FAILED
                ),
            )


class RuntimeFactoryCleanupTest(unittest.TestCase):
    def factory_inputs(self):
        ethercat = SimpleNamespace(
            backend=SimpleNamespace(value="mock"),
            sync_mode=None,
            cycle=SimpleNamespace(period=0.01),
            dc=SimpleNamespace(
                enabled=False,
                sync0_shift_time_ns=0,
            ),
        )
        motion = SimpleNamespace(
            csp_velocity_offset=False,
            csp_profile=SimpleNamespace(value="quintic"),
            initial_motion_mode="pp",
        )
        logging_config = SimpleNamespace(
            csp_command_step=SimpleNamespace(
                step_threshold=0.0,
                error_threshold=0.0,
            ),
        )
        device = SimpleNamespace(
            profile_name="test_axis",
            slave_index=0,
            role=SimpleNamespace(value="axis"),
        )
        return ethercat, motion, logging_config, (device,)

    def test_runtime_constructor_failure_closes_highest_owner(self):
        inputs = self.factory_inputs()
        manager = Mock()
        with (
            patch("motion_server.app.startup.RuntimeLogger"),
            patch("motion_server.app.startup.VirtualCiA402Servo"),
            patch("motion_server.app.startup.MockSlave"),
            patch("motion_server.app.startup.MockMaster"),
            patch("motion_server.app.startup.MotionController"),
            patch("motion_server.app.startup.DeviceManager", return_value=manager),
            patch(
                "motion_server.app.startup.AxisRuntime",
                side_effect=RuntimeError("runtime failed"),
            ),
            patch("motion_server.app.startup.LOGGER"),
        ):
            with self.assertRaisesRegex(RuntimeError, "runtime failed"):
                create_axis_runtime(
                    *inputs,
                    device_profiles=(SimpleNamespace(pdo_configuration=object()),),
                )

        manager.close.assert_called_once_with()

    def test_device_manager_constructor_failure_closes_master(self):
        inputs = self.factory_inputs()
        master = Mock()
        with (
            patch("motion_server.app.startup.RuntimeLogger"),
            patch("motion_server.app.startup.VirtualCiA402Servo"),
            patch("motion_server.app.startup.MockSlave"),
            patch("motion_server.app.startup.MockMaster", return_value=master),
            patch("motion_server.app.startup.MotionController"),
            patch(
                "motion_server.app.startup.DeviceManager",
                side_effect=RuntimeError("manager failed"),
            ),
            patch("motion_server.app.startup.LOGGER"),
        ):
            with self.assertRaisesRegex(RuntimeError, "manager failed"):
                create_axis_runtime(
                    *inputs,
                    device_profiles=(SimpleNamespace(pdo_configuration=object()),),
                )

        master.close.assert_called_once_with()

    def test_cleanup_error_is_logged_and_not_raised(self):
        resource = Mock()
        resource.close.side_effect = RuntimeError("cleanup failed")
        logger = Mock()

        error = close_initialization_resource(resource, logger=logger)

        self.assertIsInstance(error, RuntimeError)
        logger.exception.assert_called_once()

    def test_bus_connection_is_separate_stage_operation(self):
        runtime = Mock()

        connect_bus(runtime)

        runtime.connect.assert_called_once_with(target_state="preop")

    def test_device_model_domain_errors_map_without_message_parsing(self):
        device = object()
        cases = (
            (
                DeviceLayoutInvalidException(),
                InitializationCause.DEVICE_LAYOUT_INVALID,
            ),
            (
                PdoCatalogMismatchException(),
                InitializationCause.PDO_CATALOG_MISMATCH,
            ),
        )

        for source_error, expected_cause in cases:
            with self.subTest(cause=expected_cause), patch(
                "motion_server.app.startup.get_device_profile_for_device",
                side_effect=source_error,
            ):
                with self.assertRaises(InitializationException) as raised:
                    build_device_models((device,))
                self.assertIs(raised.exception.cause, expected_cause)
                self.assertIs(raised.exception.__cause__, source_error)

    def test_profile_velocity_readback_seeds_rxpdo_before_first_exchange(self):
        class RxPdo:
            profile_velocity = 0

            @staticmethod
            def has_field(name):
                return name == "profile_velocity"

        rxpdo = RxPdo()
        runtime = Mock()
        runtime.slaves = [SimpleNamespace(rxpdo=rxpdo)]
        runtime.device_manager.axes.actual_positions.return_value = [0]
        startup_sdo = {
            "profile_settings": [[123, 10, 10, 0]],
            "user_position_units": [0x0100],
        }

        def verify_first_exchange(*_args, **_kwargs):
            self.assertEqual(rxpdo.profile_velocity, 123)

        with (
            patch("motion_server.app.startup.require_txpdo_fields"),
            patch("motion_server.app.startup.clear_axis_restart_commands"),
            patch("motion_server.app.startup.write_csp_interpolation_modes"),
            patch("motion_server.app.startup.configure_motion_mode_without_exchange"),
            patch("motion_server.app.startup.exchange", side_effect=verify_first_exchange),
            patch("motion_server.app.startup.faulted_axes", return_value=[]),
            patch("motion_server.app.startup.wait_status_all", return_value=True),
        ):
            result = initialize_drive(
                runtime,
                "pp",
                (4,),
                startup_sdo_reader=lambda _runtime: startup_sdo,
            )

        self.assertIs(result, startup_sdo)
        self.assertEqual(rxpdo.profile_velocity, 123)


if __name__ == "__main__":
    unittest.main()
