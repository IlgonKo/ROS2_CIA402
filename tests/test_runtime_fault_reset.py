import unittest
from types import SimpleNamespace
from unittest.mock import patch

from motion_server.api.specification import command_spec
from motion_server.api.validator import validate_command
from motion_server.app.initialization import InitializationStatus
from motion_server.app.session import ServerRuntimeState, ServerSession
from motion_server.diagnostic import (
    AXIS_DRIVE_FAULT,
    BUS_PROCESS_DATA_INCOMPLETE,
    DiagnosticManager,
    DiagnosticSource,
    DiagnosticSourceType,
)
from motion_server.diagnostic.runtime import BUS_SOURCE
from motion_server.handlers.command.axis_state import fault_reset_axes
from motion_server.handlers.command.server import fault_reset_bus


def runtime_state():
    manager = DiagnosticManager(id_factory=lambda: "fault-id")
    runtime = SimpleNamespace(
        diagnostic_manager=manager,
        slaves=[SimpleNamespace()],
    )
    session = ServerSession(
        InitializationStatus.ready(),
        diagnostic_manager=manager,
        runtime=runtime,
    )
    state = {
        "server_session": session,
        "diagnostic_manager": manager,
        "initialization_status": session.initialization_status,
    }
    return runtime, session, state


class RuntimeFaultResetTest(unittest.TestCase):
    def test_bus_fault_reset_clears_resolved_fault_and_returns_normal(self):
        runtime, session, state = runtime_state()
        fault = session.diagnostic_manager.detect(
            BUS_PROCESS_DATA_INCOMPLETE,
            BUS_SOURCE,
        )
        session.diagnostic_manager.resolve(
            BUS_PROCESS_DATA_INCOMPLETE.code,
            BUS_SOURCE,
        )
        session.set_runtime_state(ServerRuntimeState.FAULT)

        result = fault_reset_bus({}, runtime, state, {})

        self.assertEqual(result["fault_count"], 1)
        self.assertIsNone(session.diagnostic_manager.status(fault.diagnostic_id))
        self.assertIs(session.runtime_state, ServerRuntimeState.NORMAL)

    def test_bus_fault_reset_does_not_clear_unresolved_condition(self):
        runtime, session, state = runtime_state()
        fault = session.diagnostic_manager.detect(
            BUS_PROCESS_DATA_INCOMPLETE,
            BUS_SOURCE,
        )
        session.set_runtime_state(ServerRuntimeState.FAULT)

        fault_reset_bus({}, runtime, state, {})

        self.assertIsNotNone(session.diagnostic_manager.status(fault.diagnostic_id))
        self.assertIsNotNone(fault.history.acknowledged_at)
        self.assertIs(session.runtime_state, ServerRuntimeState.FAULT)

    def test_axis_fault_reset_only_acknowledges_selected_axis(self):
        runtime, session, state = runtime_state()
        axis_zero = DiagnosticSource(DiagnosticSourceType.AXIS, 0)
        fault = session.diagnostic_manager.detect(AXIS_DRIVE_FAULT, axis_zero)

        with patch(
            "motion_server.handlers.command.axis_state.reset_faults"
        ) as device_reset:
            result = fault_reset_axes(
                {"cmd": "system/axis/fault_reset", "axis": 0},
                runtime,
                state,
                {},
            )

        device_reset.assert_called_once_with(runtime, state, [0])
        self.assertEqual(result["fault_count"], 1)
        self.assertIsNotNone(fault.history.acknowledged_at)

    def test_global_fault_blocks_motion_but_allows_safety_and_recovery(self):
        runtime, session, state = runtime_state()
        session.set_runtime_state(ServerRuntimeState.FAULT)

        blocked = validate_command(
            command_spec("system/axis/move_abs"),
            {},
            state,
            True,
            message={"axis": 0},
        )
        for command in (
            "system/axis/stop",
            "system/axis/disable",
            "system/bus/fault_reset",
            "system/bus/reconnect",
            "system/server/restart",
        ):
            with self.subTest(command=command):
                self.assertIsNone(
                    validate_command(
                        command_spec(command),
                        {},
                        state,
                        True,
                        message={"axis": 0},
                    )
                )

        self.assertEqual(blocked, "runtime_fault")

    def test_bus_reconnect_is_rejected_while_runtime_is_normal(self):
        _runtime, session, state = runtime_state()

        normal_result = validate_command(
            command_spec("system/bus/reconnect"),
            {},
            state,
            True,
        )
        session.set_runtime_state(ServerRuntimeState.BUS_DISCONNECTED)
        disconnected_result = validate_command(
            command_spec("system/bus/reconnect"),
            {},
            state,
            True,
        )

        self.assertEqual(normal_result, "runtime_fault")
        self.assertIsNone(disconnected_result)

    def test_axis_fault_only_blocks_commands_for_faulted_axis(self):
        runtime, session, state = runtime_state()
        runtime.slaves.append(SimpleNamespace())
        session.diagnostic_manager.detect(
            AXIS_DRIVE_FAULT,
            DiagnosticSource(DiagnosticSourceType.AXIS, 0),
        )

        faulted = validate_command(
            command_spec("system/axis/enable"),
            {},
            state,
            True,
            message={"axis": 0},
        )
        normal = validate_command(
            command_spec("system/axis/enable"),
            {},
            state,
            True,
            message={"axis": 1},
        )
        safe = validate_command(
            command_spec("system/axis/disable"),
            {},
            state,
            True,
            message={"axis": 0},
        )
        recovery = validate_command(
            command_spec("system/axis/restart"),
            {},
            state,
            True,
            message={"axis": 0},
        )

        self.assertEqual(faulted, "runtime_fault")
        self.assertIsNone(normal)
        self.assertIsNone(safe)
        self.assertIsNone(recovery)


if __name__ == "__main__":
    unittest.main()
