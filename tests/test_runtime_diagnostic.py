import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from motion_server.api.router import request_response
from motion_server.diagnostic import (
    AXIS_DRIVE_FAULT,
    AXIS_DRIVE_WARNING,
    BUS_PROCESS_DATA_INCOMPLETE,
    DiagnosticLevel,
    DiagnosticManager,
    DiagnosticSource,
    DiagnosticSourceType,
)
from motion_server.diagnostic.runtime import (
    BUS_SOURCE,
    RuntimeDiagnosticMonitor,
)
from motion_server.failure import CommunicationTimeoutException


NOW = datetime(2026, 8, 21, 3, 0, tzinfo=timezone.utc)


class Runtime:
    def __init__(self, statuswords=(0x0027,), *, wkc=2, expected_wkc=2):
        self.slaves = [
            SimpleNamespace(txpdo=SimpleNamespace(statusword=statusword))
            for statusword in statuswords
        ]
        self.wkc = wkc
        self._expected_wkc = expected_wkc

    def expected_wkc(self):
        return self._expected_wkc


def manager(*ids):
    values = iter(ids or ("diag-1",))
    return DiagnosticManager(clock=lambda: NOW, id_factory=lambda: next(values))


class BusDiagnosticTest(unittest.TestCase):
    def test_single_wkc_mismatch_does_not_create_diagnostic(self):
        diagnostics = manager()
        monitor = RuntimeDiagnosticMonitor(diagnostics)
        runtime = Runtime(wkc=1, expected_wkc=2)

        monitor.update(runtime, at=NOW)

        self.assertEqual(diagnostics.active_statuses(), ())

    def test_three_consecutive_wkc_mismatches_create_latching_bus_fault(self):
        diagnostics = manager("bus-fault")
        monitor = RuntimeDiagnosticMonitor(diagnostics)
        runtime = Runtime(wkc=1, expected_wkc=2)

        for _ in range(3):
            monitor.update(runtime, at=NOW)

        fault = diagnostics.status_for(
            BUS_PROCESS_DATA_INCOMPLETE.code,
            BUS_SOURCE,
        )
        self.assertIsNotNone(fault)
        self.assertIs(fault.definition.level, DiagnosticLevel.FAULT)
        self.assertTrue(fault.definition.latching)

    def test_good_cycle_breaks_wkc_mismatch_sequence(self):
        diagnostics = manager()
        monitor = RuntimeDiagnosticMonitor(diagnostics)
        runtime = Runtime(wkc=1, expected_wkc=2)

        monitor.update(runtime)
        monitor.update(runtime)
        runtime.wkc = 2
        monitor.update(runtime)
        runtime.wkc = 1
        monitor.update(runtime)
        monitor.update(runtime)

        self.assertIsNone(
            diagnostics.status_for(
                BUS_PROCESS_DATA_INCOMPLETE.code,
                BUS_SOURCE,
            ),
        )

    def test_bus_recovery_resolves_but_acknowledge_clears_latching_fault(self):
        diagnostics = manager("bus-fault")
        monitor = RuntimeDiagnosticMonitor(diagnostics)
        runtime = Runtime(wkc=0, expected_wkc=2)
        for _ in range(3):
            monitor.update(runtime, at=NOW)
        fault = diagnostics.status_for(
            BUS_PROCESS_DATA_INCOMPLETE.code,
            BUS_SOURCE,
        )

        runtime.wkc = 2
        monitor.update(runtime, at=NOW)

        self.assertEqual(fault.history.resolved_at, NOW)
        self.assertIsNotNone(diagnostics.status(fault.diagnostic_id))
        diagnostics.acknowledge(fault.diagnostic_id, at=NOW)
        self.assertIsNone(diagnostics.status(fault.diagnostic_id))


class AxisDiagnosticTest(unittest.TestCase):
    def test_axis_fault_bit_creates_source_specific_latching_fault(self):
        diagnostics = manager("axis-fault")
        monitor = RuntimeDiagnosticMonitor(diagnostics)
        runtime = Runtime(statuswords=(0x0008, 0x0027))

        monitor.update(runtime, at=NOW)

        axis_zero = DiagnosticSource(DiagnosticSourceType.AXIS, 0)
        fault = diagnostics.status_for(AXIS_DRIVE_FAULT.code, axis_zero)
        self.assertIsNotNone(fault)
        self.assertTrue(fault.definition.latching)
        self.assertIsNone(
            diagnostics.status_for(
                AXIS_DRIVE_FAULT.code,
                DiagnosticSource(DiagnosticSourceType.AXIS, 1),
            ),
        )

    def test_axis_warning_is_alarm_and_clears_when_bit_clears(self):
        diagnostics = manager("axis-warning")
        monitor = RuntimeDiagnosticMonitor(diagnostics)
        runtime = Runtime(statuswords=(0x00A7,))
        axis = DiagnosticSource(DiagnosticSourceType.AXIS, 0)

        monitor.update(runtime, at=NOW)
        warning = diagnostics.status_for(AXIS_DRIVE_WARNING.code, axis)

        self.assertIs(warning.definition.level, DiagnosticLevel.ALARM)
        self.assertFalse(warning.definition.latching)
        runtime.slaves[0].txpdo.statusword = 0x0027
        monitor.update(runtime, at=NOW)
        self.assertIsNone(diagnostics.status(warning.diagnostic_id))

    def test_axis_fault_recovery_waits_for_acknowledge(self):
        diagnostics = manager("axis-fault")
        monitor = RuntimeDiagnosticMonitor(diagnostics)
        runtime = Runtime(statuswords=(0x0008,))
        axis = DiagnosticSource(DiagnosticSourceType.AXIS, 0)
        monitor.update(runtime, at=NOW)
        fault = diagnostics.status_for(AXIS_DRIVE_FAULT.code, axis)

        runtime.slaves[0].txpdo.statusword = 0x0027
        monitor.update(runtime, at=NOW)

        self.assertEqual(fault.history.resolved_at, NOW)
        self.assertIsNotNone(diagnostics.status(fault.diagnostic_id))


class DiagnosticBoundaryTest(unittest.TestCase):
    def test_single_api_timeout_does_not_create_runtime_diagnostic(self):
        diagnostics = manager()

        def timeout():
            raise CommunicationTimeoutException("sdo_read")

        response = request_response(
            {"type": "system/axis/param_read"},
            timeout,
        )

        self.assertEqual(response["failure"]["code"], "TIMEOUT")
        self.assertEqual(diagnostics.active_statuses(), ())


if __name__ == "__main__":
    unittest.main()
