import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from motion_server.api.specification import command_spec
from motion_server.api.router import request_response
from motion_server.api.validator import validate_command
from motion_server.app.runtime import AxisRuntime
from motion_server.diagnostic import (
    DiagnosticLevel,
    DiagnosticManager,
    SERVER_INITIALIZATION_FAILED,
    SERVER_SOURCE,
)
from motion_server.diagnostic.startup import (
    detect_initialization_fault,
    resolve_initialization_fault,
)
from motion_server.failure import ServerNotReadyException


OCCURRED_AT = datetime(2026, 8, 21, 2, 0, tzinfo=timezone.utc)


class RuntimeOwnerTest(unittest.TestCase):
    def test_axis_runtime_owns_diagnostic_manager_separately_from_raw_readback(self):
        device_manager = SimpleNamespace(
            axis_devices=[],
            last_diagnostics=[{"error_code": 0}],
        )
        motion_controller = SimpleNamespace(axis_count=0)

        runtime = AxisRuntime(device_manager, motion_controller)

        self.assertIsInstance(runtime.diagnostic_manager, DiagnosticManager)
        self.assertEqual(runtime.last_diagnostics, [{"error_code": 0}])
        self.assertEqual(runtime.diagnostic_manager.active_statuses(), ())

    def test_axis_runtime_accepts_manager_owned_by_reinitialization_loop(self):
        manager = DiagnosticManager()
        device_manager = SimpleNamespace(axis_devices=[], last_diagnostics=[])

        runtime = AxisRuntime(
            device_manager,
            SimpleNamespace(axis_count=0),
            diagnostic_manager=manager,
        )

        self.assertIs(runtime.diagnostic_manager, manager)


class InitializationFaultTest(unittest.TestCase):
    def runtime(self):
        return SimpleNamespace(
            diagnostic_manager=DiagnosticManager(
                clock=lambda: OCCURRED_AT,
                id_factory=lambda: "startup-fault-1",
            ),
        )

    def test_definition_is_server_latching_fault(self):
        self.assertEqual(
            SERVER_INITIALIZATION_FAILED.code,
            "SERVER_INITIALIZATION_FAILED",
        )
        self.assertIs(SERVER_INITIALIZATION_FAILED.level, DiagnosticLevel.FAULT)
        self.assertTrue(SERVER_INITIALIZATION_FAILED.latching)
        self.assertEqual(SERVER_SOURCE.index, 0)

    def test_startup_failure_creates_one_server_fault_without_internal_detail(self):
        runtime = self.runtime()

        first = detect_initialization_fault(runtime)
        repeated = detect_initialization_fault(runtime)

        self.assertIs(repeated, first)
        self.assertEqual(first.source, SERVER_SOURCE)
        self.assertEqual(first.history.occurred_at, OCCURRED_AT)
        self.assertIsNone(first.detail)
        self.assertIsNone(first.context)
        self.assertIs(
            runtime.diagnostic_manager.current_level(),
            DiagnosticLevel.FAULT,
        )

    def test_degraded_command_rejection_does_not_clear_initialization_fault(self):
        runtime = self.runtime()
        fault = detect_initialization_fault(runtime)
        state = {
            "drive_initialized": False,
            "initialization_error": "startup failed",
        }

        validation_error = validate_command(
            command_spec("system/axis/enable"),
            {"id": "client"},
            state,
            has_authority=True,
        )

        self.assertEqual(validation_error, "not_initialized")
        self.assertIs(
            runtime.diagnostic_manager.status(fault.diagnostic_id),
            fault,
        )

    def test_recovery_command_remains_allowed_while_fault_is_active(self):
        runtime = self.runtime()
        detect_initialization_fault(runtime)
        state = {"drive_initialized": False}

        validation_error = validate_command(
            command_spec("system/server/reset"),
            {"id": "client"},
            state,
            has_authority=True,
        )

        self.assertIsNone(validation_error)
        self.assertIs(
            runtime.diagnostic_manager.current_level(),
            DiagnosticLevel.FAULT,
        )

    def test_api_fail_and_initialization_fault_remain_independent(self):
        runtime = self.runtime()
        fault = detect_initialization_fault(runtime)

        def reject_command():
            raise ServerNotReadyException()

        response = request_response(
            {"type": "system/axis/enable"},
            reject_command,
        )

        self.assertEqual(response["failure"]["code"], "SERVER_NOT_READY")
        self.assertIs(
            runtime.diagnostic_manager.status(fault.diagnostic_id),
            fault,
        )

    def test_successful_reinitialization_resolves_but_does_not_clear_fault(self):
        runtime = self.runtime()
        fault = detect_initialization_fault(runtime)

        resolved = resolve_initialization_fault(runtime, at=OCCURRED_AT)

        self.assertIs(resolved, fault)
        self.assertEqual(resolved.history.resolved_at, OCCURRED_AT)
        self.assertIs(
            runtime.diagnostic_manager.status(fault.diagnostic_id),
            fault,
        )

    def test_success_without_previous_fault_has_nothing_to_resolve(self):
        runtime = self.runtime()

        self.assertIsNone(resolve_initialization_fault(runtime))


if __name__ == "__main__":
    unittest.main()
