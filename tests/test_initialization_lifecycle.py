from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from configuration.models import (
    BusDeviceConfig,
    CmmtDeviceConfig,
    CpxApIEcDeviceConfig,
    DeviceRole,
    IoModuleConfig,
)
from device.cpx_ap_i_ec.profile import CPXApIEcDeviceProfile
from device.exceptions import (
    DeviceLayoutInvalidException,
    PdoCatalogMismatchException,
)
from motion_server.app.initialization import (
    INITIALIZATION_CAUSE_DEFINITIONS,
    InitializationCause,
    InitializationException,
    InitializationStage,
    InitializationStatus,
    log_initialization_failure,
)
from motion_server.app.session import ServerSession
from motion_server.application import MotionServerApplication
from motion_server.diagnostic import SERVER_INITIALIZATION_FAILED
from motion_server.diagnostic.definitions import SERVER_SOURCE
from motion_server.handlers.status.server_status import server_status_message
from motion_server.server import initialize_runtime_session, run_main_once


class InitializationLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.device = BusDeviceConfig(
            slave_index=0,
            role=DeviceRole.AXIS,
            profile_name="cmmt_as",
            logical_id=None,
            device=CmmtDeviceConfig(
                profile_name="cmmt_as",
                axis_index=0,
                pdo_configuration="motion_server_default",
            ),
        )
        self.motion = SimpleNamespace(
            initial_motion_mode="pp",
            csp_interpolation_mode=4,
        )

    def initialize(self, session):
        return initialize_runtime_session(
            session,
            ethercat_config=object(),
            motion_config=self.motion,
            logging_config=object(),
            devices=(self.device,),
        )

    def test_each_runtime_stage_has_stable_failure_contract(self):
        cases = (
            (
                "motion_server.server.build_device_models",
                InitializationException(
                    InitializationCause.PDO_CATALOG_MISMATCH
                ),
                InitializationStage.DEVICE_MODEL_BUILD,
                InitializationCause.PDO_CATALOG_MISMATCH,
            ),
            (
                "motion_server.server.create_axis_runtime",
                RuntimeError("private runtime detail"),
                InitializationStage.RUNTIME_CREATION,
                InitializationCause.RUNTIME_CREATION_FAILED,
            ),
            (
                "motion_server.server.connect_bus",
                RuntimeError("private bus detail"),
                InitializationStage.BUS_CONNECTION,
                InitializationCause.BUS_CONNECTION_FAILED,
            ),
            (
                "motion_server.server.initialize_drive",
                InitializationException(
                    InitializationCause.REQUIRED_PARAMETER_READ_FAILED
                ),
                InitializationStage.DEVICE_INITIALIZATION,
                InitializationCause.REQUIRED_PARAMETER_READ_FAILED,
            ),
        )

        for target, source_error, expected_stage, expected_cause in cases:
            with self.subTest(stage=expected_stage):
                session = ServerSession(InitializationStatus.ready())
                runtime = Mock()
                runtime.diagnostic_manager = None
                patches = [
                    patch(
                        "motion_server.server.build_device_models",
                        return_value=(object(),),
                    ),
                    patch(
                        "motion_server.server.create_axis_runtime",
                        return_value=runtime,
                    ),
                    patch("motion_server.server.connect_bus"),
                    patch(
                        "motion_server.server.initialize_drive",
                        return_value=({},),
                    ),
                    patch("motion_server.server.log_initialization_failure"),
                ]
                with patches[0], patches[1], patches[2], patches[3], patches[4]:
                    with patch(target, side_effect=source_error):
                        result = self.initialize(session)

                self.assertEqual(result, (None, None))
                failure = session.initialization_status.failure
                self.assertIs(failure.stage, expected_stage)
                self.assertIs(failure.cause, expected_cause)
                self.assertEqual(
                    failure.message,
                    INITIALIZATION_CAUSE_DEFINITIONS[expected_cause].message,
                )
                status = session.diagnostic_manager.status_for(
                    SERVER_INITIALIZATION_FAILED.code,
                    SERVER_SOURCE,
                )
                self.assertEqual(status.history.occurred_at, failure.occurred_at)
                if expected_stage in (
                    InitializationStage.BUS_CONNECTION,
                    InitializationStage.DEVICE_INITIALIZATION,
                ):
                    runtime.close.assert_called_once_with()
                    self.assertIsNone(session.runtime)

    def test_runtime_success_waits_for_server_state_before_resolving_fault(self):
        session = ServerSession(InitializationStatus.ready())
        failed_runtime = Mock()
        successful_runtime = Mock()
        with (
            patch(
                "motion_server.server.build_device_models",
                return_value=(object(),),
            ),
            patch(
                "motion_server.server.create_axis_runtime",
                side_effect=(failed_runtime, successful_runtime),
            ),
            patch(
                "motion_server.server.connect_bus",
                side_effect=(RuntimeError("offline"), None),
            ),
            patch(
                "motion_server.server.initialize_drive",
                return_value=({},),
            ),
            patch("motion_server.server.log_initialization_failure"),
        ):
            self.assertEqual(self.initialize(session), (None, None))
            fault = session.diagnostic_manager.status_for(
                SERVER_INITIALIZATION_FAILED.code,
                SERVER_SOURCE,
            )
            self.assertIsNotNone(fault)
            self.assertIsNone(fault.history.resolved_at)

            runtime, _startup = self.initialize(session)

        self.assertIs(runtime, successful_runtime)
        self.assertFalse(session.initialization_status.initialized)
        self.assertIs(
            session.diagnostic_manager.status_for(
                SERVER_INITIALIZATION_FAILED.code,
                SERVER_SOURCE,
            ),
            fault,
        )
        self.assertIsNone(fault.history.resolved_at)
        self.assertIsNone(fault.history.acknowledged_at)

    def test_server_state_projection_failure_enters_degraded_state(self):
        session = ServerSession(InitializationStatus.ready())
        runtime = Mock()
        session.attach_runtime(runtime)
        server_config = SimpleNamespace(
            mode=SimpleNamespace(value="basic"),
            port=15000,
        )
        ethercat_config = SimpleNamespace(
            backend=SimpleNamespace(value="mock"),
        )
        motion_config = SimpleNamespace()
        socket_context = Mock()
        socket_context.__enter__ = Mock(return_value=Mock())
        socket_context.__exit__ = Mock(return_value=False)

        with (
            patch(
                "motion_server.server.initialize_runtime_session",
                return_value=(runtime, {}),
            ),
            patch(
                "motion_server.server.build_initialized_server_state",
                side_effect=RuntimeError("projection failed"),
            ),
            patch("motion_server.server.log_initialization_failure"),
            patch("motion_server.server.socket.socket", return_value=socket_context),
            patch("motion_server.server.run_degraded_server_loop", return_value=None),
        ):
            run_main_once(
                session,
                server_config=server_config,
                ethercat_config=ethercat_config,
                motion_config=motion_config,
                logging_config=object(),
                devices=(self.device,),
            )

        failure = session.initialization_status.failure
        self.assertIs(
            failure.cause,
            InitializationCause.DEVICE_INITIALIZATION_FAILED,
        )
        fault = session.diagnostic_manager.status_for(
            SERVER_INITIALIZATION_FAILED.code,
            SERVER_SOURCE,
        )
        self.assertEqual(fault.history.occurred_at, failure.occurred_at)
        runtime.close.assert_called_once_with()
        self.assertIsNone(session.runtime)

    def test_log_and_status_use_same_registry_contract(self):
        session = ServerSession(InitializationStatus.ready())
        with (
            patch(
                "motion_server.server.build_device_models",
                side_effect=RuntimeError("secret builder detail"),
            ),
            patch("motion_server.server.log_initialization_failure"),
        ):
            self.initialize(session)
        failure = session.initialization_status.failure
        state = {
            "server_session": session,
            "initialization_status": session.initialization_status,
            "diagnostic_manager": session.diagnostic_manager,
        }
        response = server_status_message(None, state)["initialization_failure"]

        with (
            patch("builtins.print") as output,
            patch("traceback.print_exception") as traceback_output,
        ):
            log_initialization_failure(failure, RuntimeError("secret detail"))

        line = output.call_args.args[0]
        self.assertIn(f"stage={response['stage']}", line)
        self.assertIn(f"cause={response['cause']}", line)
        self.assertIn(f"message={response['message']}", line)
        self.assertNotIn("secret detail", line)
        traceback_output.assert_called_once()

    def test_cpx_layout_and_catalog_failures_remain_distinct(self):
        invalid_layout = CpxApIEcDeviceConfig(
            profile_name="cpx_ap_i_ec",
            logical_id="io0",
            modules=(),
            io_link_ports=(),
        )
        with self.assertRaises(DeviceLayoutInvalidException):
            CPXApIEcDeviceProfile(device_config=invalid_layout)

        valid_layout = CpxApIEcDeviceConfig(
            profile_name="cpx_ap_i_ec",
            logical_id="io0",
            modules=(
                IoModuleConfig(1, "do:8"),
                IoModuleConfig(2, "di:8"),
            ),
            io_link_ports=(),
        )
        with (
            patch(
                "device.cpx_ap_i_ec.profile.cpx_pdo_configuration"
            ) as configuration_factory,
        ):
            configuration_factory.return_value.validate_catalog_support.side_effect = (
                RuntimeError("ESI PDO mismatch")
            )
            with self.assertRaises(PdoCatalogMismatchException):
                CPXApIEcDeviceProfile(device_config=valid_layout)


class ApplicationRecoveryOwnershipTest(unittest.TestCase):
    def application(self):
        config = SimpleNamespace(
            server=object(),
            ethercat=object(),
            motion=object(),
            logging=object(),
            devices=(),
        )
        return MotionServerApplication(SimpleNamespace(port=15000), config)

        self.assertIs(
            sessions[0].diagnostic_manager,
            sessions[1].diagnostic_manager,
        )


if __name__ == "__main__":
    unittest.main()
