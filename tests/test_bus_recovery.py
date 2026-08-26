import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from device.capabilities import DeviceCapability
from motion_server.app.initialization import InitializationStatus
from motion_server.app.recovery import (
    mark_bus_disconnected,
    reconnect_runtime,
    restart_axis_runtime,
)
from motion_server.app.session import ServerRuntimeState, ServerSession
from motion_server.app.recovery_refresh import RecoveryType
from motion_server.diagnostic import (
    BUS_CONNECTION_LOST,
    BUS_RECONNECT_FAILED,
    AXIS_RESTART_FAILED,
    DiagnosticManager,
    DiagnosticSource,
    DiagnosticSourceType,
)
from motion_server.diagnostic.runtime import BUS_SOURCE
from motion_server.failure import CommunicationException
from motion_server.handlers.command.axis_state import restart_axis


class FakeProfile:
    def mode_code(self, mode_name):
        return {"pp": 1, "csp": 8}[mode_name]

    def configure_mode_code(self, runtime, axis_index, mode_code):
        runtime.configured_modes.append((axis_index, mode_code))


class FakeRuntime:
    def __init__(self, manager, *, connect_error=None):
        self.diagnostic_manager = manager
        self.connect_error = connect_error
        self.events = []
        self.configured_modes = []
        self.wkc = 1
        self._expected_wkc = 1
        self.slaves = [
            SimpleNamespace(
                rxpdo=SimpleNamespace(mode_of_operation=0),
                device_profile=FakeProfile(),
            )
        ]

    def close(self):
        self.events.append("close")

    def connect(self, target_state=None, timeout_s=None):
        self.events.append(f"connect:{target_state}")
        if self.connect_error is not None:
            raise self.connect_error

    def enter_operational(self, timeout_s=None):
        self.events.append("enter_operational")

    def sync_trajectory_to_actual_positions(self):
        self.events.append("sync_trajectory")

    def expected_wkc(self):
        return self._expected_wkc


def recovery_state(*, connect_error=None):
    manager = DiagnosticManager(id_factory=iter(("lost", "failed")).__next__)
    runtime = FakeRuntime(manager, connect_error=connect_error)
    session = ServerSession(
        InitializationStatus.ready(),
        diagnostic_manager=manager,
        runtime=runtime,
    )
    state = {
        "server_session": session,
        "diagnostic_manager": manager,
        "initialization_status": session.initialization_status,
        "bus_reconnect_timeout": 10.0,
        "axis_restart_timeout": 1.0,
        "csp_interpolation_modes": [4],
        "motion_modes": ["pp"],
        "recovery_in_progress": None,
    }
    return runtime, session, state


class BusRecoveryTest(unittest.TestCase):
    def test_disconnect_preserves_runtime_and_creates_bus_fault(self):
        runtime, session, state = recovery_state()

        mark_bus_disconnected(state, OSError("cable removed"))

        self.assertIs(session.runtime, runtime)
        self.assertIs(session.runtime_state, ServerRuntimeState.BUS_DISCONNECTED)
        self.assertEqual(runtime.events, ["close"])
        self.assertIsNotNone(
            session.diagnostic_manager.status_for(
                BUS_CONNECTION_LOST.code,
                BUS_SOURCE,
            )
        )

    def test_reconnect_uses_same_runtime_and_clears_bus_fault(self):
        runtime, session, state = recovery_state()
        mark_bus_disconnected(state, OSError("cable removed"))

        with (
            patch("motion_server.app.recovery.clear_axis_restart_commands"),
            patch("motion_server.app.recovery.write_csp_interpolation_modes"),
            patch("motion_server.app.recovery.exchange"),
            patch("motion_server.app.recovery.refresh_after_recovery") as refresh,
        ):
            result = reconnect_runtime(runtime, state)

        self.assertTrue(result["connected"])
        self.assertIs(session.runtime, runtime)
        self.assertIs(session.runtime_state, ServerRuntimeState.NORMAL)
        self.assertEqual(
            runtime.events,
            [
                "close",
                "close",
                "connect:preop",
                "enter_operational",
                "sync_trajectory",
            ],
        )
        refresh.assert_called_once_with(
            runtime,
            RecoveryType.BUS_RECONNECT,
            range(0, 1),
        )
        self.assertIsNone(
            session.diagnostic_manager.status_for(
                BUS_CONNECTION_LOST.code,
                BUS_SOURCE,
            )
        )

    def test_reconnect_refreshes_in_preop_before_entering_operational(self):
        runtime, _session, state = recovery_state()

        with (
            patch("motion_server.app.recovery.clear_axis_restart_commands"),
            patch("motion_server.app.recovery.write_csp_interpolation_modes"),
            patch(
                "motion_server.app.recovery.refresh_after_recovery",
                side_effect=lambda *_args: runtime.events.append("refresh"),
            ),
            patch(
                "motion_server.app.recovery.exchange",
                side_effect=lambda *_args, **_kwargs: runtime.events.append(
                    "exchange"
                ),
            ),
        ):
            reconnect_runtime(runtime, state)

        self.assertLess(
            runtime.events.index("refresh"),
            runtime.events.index("enter_operational"),
        )
        self.assertLess(
            runtime.events.index("enter_operational"),
            runtime.events.index("exchange"),
        )
        self.assertEqual(runtime.events.count("exchange"), 3)

    def test_reconnect_rejects_processdata_that_never_reaches_expected_wkc(self):
        runtime, session, state = recovery_state()
        runtime.wkc = 1
        runtime._expected_wkc = 3
        state["bus_reconnect_timeout"] = 0.001

        with (
            patch("motion_server.app.recovery.clear_axis_restart_commands"),
            patch("motion_server.app.recovery.write_csp_interpolation_modes"),
            patch("motion_server.app.recovery.refresh_after_recovery"),
            patch("motion_server.app.recovery.exchange"),
            self.assertRaises(CommunicationException),
        ):
            reconnect_runtime(runtime, state)

        self.assertIs(
            session.runtime_state,
            ServerRuntimeState.BUS_DISCONNECTED,
        )
        self.assertIsNotNone(
            session.diagnostic_manager.status_for(
                BUS_RECONNECT_FAILED.code,
                BUS_SOURCE,
            )
        )

    def test_bus_reconnect_resolves_prior_axis_restart_failure(self):
        runtime, session, state = recovery_state()
        source = DiagnosticSource(DiagnosticSourceType.AXIS, 0)
        fault = session.diagnostic_manager.detect(AXIS_RESTART_FAILED, source)
        session.set_runtime_state(ServerRuntimeState.BUS_DISCONNECTED)

        with (
            patch("motion_server.app.recovery.clear_axis_restart_commands"),
            patch("motion_server.app.recovery.write_csp_interpolation_modes"),
            patch("motion_server.app.recovery.exchange"),
            patch("motion_server.app.recovery.refresh_after_recovery"),
        ):
            reconnect_runtime(runtime, state)

        self.assertIsNotNone(fault.history.resolved_at)
        self.assertIsNone(fault.history.acknowledged_at)
        self.assertIs(session.runtime_state, ServerRuntimeState.NORMAL)

    def test_failed_reconnect_stays_disconnected_and_records_fault(self):
        runtime, session, state = recovery_state(
            connect_error=OSError("still disconnected")
        )
        state["bus_reconnect_timeout"] = 0.001
        mark_bus_disconnected(state, OSError("cable removed"))

        with self.assertRaises(CommunicationException):
            reconnect_runtime(runtime, state)

        self.assertIs(session.runtime, runtime)
        self.assertIs(session.runtime_state, ServerRuntimeState.BUS_DISCONNECTED)
        self.assertIsNotNone(
            session.diagnostic_manager.status_for(
                BUS_RECONNECT_FAILED.code,
                BUS_SOURCE,
            )
        )
        self.assertIsNone(state["recovery_in_progress"])

    def test_axis_restart_rebuilds_bus_but_refreshes_target_axis_only(self):
        runtime, session, state = recovery_state()
        runtime.slaves.append(
            SimpleNamespace(
                rxpdo=SimpleNamespace(mode_of_operation=0),
                device_profile=FakeProfile(),
            )
        )
        state["csp_interpolation_modes"] = [4, 4]
        state["motion_modes"] = ["pp", "csp"]

        with (
            patch("motion_server.app.recovery.clear_axis_restart_commands"),
            patch("motion_server.app.recovery.write_csp_interpolation_modes"),
            patch("motion_server.app.recovery.exchange"),
            patch("motion_server.app.recovery.refresh_after_recovery") as refresh,
        ):
            result = restart_axis_runtime(runtime, state, 1)

        self.assertEqual(result["axis"], 1)
        self.assertIs(session.runtime_state, ServerRuntimeState.NORMAL)
        self.assertEqual(runtime.configured_modes, [(0, 1), (1, 8)])
        refresh.assert_called_once_with(
            runtime,
            RecoveryType.AXIS_RESTART,
            (1,),
        )
        self.assertIsNone(state["recovery_in_progress"])

    def test_axis_restart_timeout_records_axis_fault_and_disconnects_bus(self):
        runtime, session, state = recovery_state(
            connect_error=OSError("axis is restarting")
        )
        state["axis_restart_timeout"] = 0.001

        with self.assertRaises(CommunicationException):
            restart_axis_runtime(runtime, state, 0)

        self.assertIs(session.runtime_state, ServerRuntimeState.BUS_DISCONNECTED)
        self.assertIsNotNone(
            session.diagnostic_manager.status_for(
                "AXIS_RESTART_FAILED",
                DiagnosticSource(DiagnosticSourceType.AXIS, 0),
            )
        )

    def test_axis_refresh_failure_before_op_disconnects_bus(self):
        runtime, session, state = recovery_state()

        with (
            patch("motion_server.app.recovery.clear_axis_restart_commands"),
            patch("motion_server.app.recovery.write_csp_interpolation_modes"),
            patch("motion_server.app.recovery.exchange"),
            patch(
                "motion_server.app.recovery.refresh_after_recovery",
                side_effect=RuntimeError("readback failed"),
            ),
            self.assertRaises(CommunicationException),
        ):
            restart_axis_runtime(runtime, state, 0)

        self.assertIs(
            session.runtime_state,
            ServerRuntimeState.BUS_DISCONNECTED,
        )
        self.assertEqual(runtime.events.count("close"), 2)
        self.assertNotIn("enter_operational", runtime.events)


class AxisRestartSafetyTest(unittest.TestCase):
    def test_axis_restart_holds_and_disables_every_axis_before_bus_rebuild(self):
        slaves = [
            SimpleNamespace(
                rxpdo=SimpleNamespace(controlword=0x000F),
                txpdo=SimpleNamespace(statusword=0x0027),
            )
            for _ in range(2)
        ]
        runtime = SimpleNamespace(
            slaves=slaves,
            set_target_positions=Mock(),
            sync_trajectory_to_actual_positions=Mock(),
            set_controlword_all=Mock(
                side_effect=lambda value: [
                    setattr(slave.rxpdo, "controlword", value)
                    for slave in slaves
                ]
            ),
            logger=SimpleNamespace(status=Mock()),
        )
        state = {
            "target_positions": [10.0, 20.0],
            "trajectory": {"active": True, "axes": [0, 1]},
            "homing": {"active": True, "axes": [0]},
            "axis_restart_disable_settle_time": 0.0,
        }
        profile = SimpleNamespace(
            name="restartable",
            capabilities=frozenset({DeviceCapability.AXIS_RESTART}),
            request_axis_restart=Mock(return_value={"command": 1}),
        )

        with (
            patch(
                "motion_server.handlers.command.axis_state.axis_device_profile",
                return_value=profile,
            ),
            patch(
                "motion_server.handlers.command.axis_state.finish_homing"
            ) as finish_homing_mock,
            patch(
                "motion_server.handlers.command.axis_state."
                "hold_axis_at_actual_position"
            ) as hold_axis,
            patch(
                "motion_server.handlers.command.axis_state."
                "wait_axis_not_operation_enabled",
                return_value=True,
            ) as wait_disabled,
            patch(
                "motion_server.handlers.command.axis_state."
                "keep_pdo_alive_for_seconds"
            ),
            patch(
                "motion_server.handlers.command.axis_state.restart_axis_runtime",
                return_value={"axis": 1},
            ),
        ):
            result = restart_axis(
                {"cmd": "system/axis/restart", "axis": 1},
                runtime,
                state,
                {},
            )

        finish_homing_mock.assert_called_once()
        self.assertFalse(state["trajectory"]["active"])
        self.assertEqual(
            hold_axis.call_args_list,
            [call(runtime, state, 0), call(runtime, state, 1)],
        )
        runtime.set_controlword_all.assert_called_once_with(0x0007)
        self.assertEqual(
            wait_disabled.call_args_list,
            [call(runtime, 0), call(runtime, 1)],
        )
        self.assertEqual(
            [slave.rxpdo.controlword for slave in slaves],
            [0x0007, 0x0007],
        )
        self.assertEqual(result["axis"], 1)


if __name__ == "__main__":
    unittest.main()
