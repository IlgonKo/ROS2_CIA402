import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from motion_server.diagnostic import (
    AXIS_DRIVE_FAULT,
    AXIS_DRIVE_WARNING,
    BUS_PROCESS_DATA_INCOMPLETE,
    DiagnosticManager,
    DiagnosticSource,
    DiagnosticSourceType,
    diagnostic_status_data,
    diagnostic_status_snapshot,
)
from motion_server.handlers.status.server_status import server_status_message
from motion_server.app.initialization import InitializationStatus
from motion_server.app.session import ServerSession


NOW = datetime(2026, 8, 21, 1, 2, 3, tzinfo=timezone.utc)


def runtime(manager=None):
    result = SimpleNamespace(slaves=[], cycle_time=0.008)
    if manager is not None:
        result.diagnostic_manager = manager
    return result


class DiagnosticStatusSerializationTest(unittest.TestCase):
    def test_runtime_without_manager_has_normal_empty_snapshot(self):
        self.assertEqual(
            diagnostic_status_snapshot(runtime()),
            {"level": "normal", "statuses": []},
        )

    def test_status_preserves_definition_source_and_history_structure(self):
        manager = DiagnosticManager(id_factory=lambda: "diag-1")
        status = manager.detect(
            AXIS_DRIVE_FAULT,
            DiagnosticSource(DiagnosticSourceType.AXIS, 2),
            detail="internal detail",
            context={"raw": object()},
            at=NOW,
        )
        manager.acknowledge("diag-1", at=NOW + timedelta(seconds=1))

        data = diagnostic_status_data(status)

        self.assertEqual(data["diagnostic_id"], "diag-1")
        self.assertEqual(data["definition"]["code"], "AXIS_DRIVE_FAULT")
        self.assertEqual(data["definition"]["level"], "fault")
        self.assertTrue(data["definition"]["latching"])
        self.assertEqual(data["source"], {"type": "axis", "index": 2})
        self.assertEqual(data["history"]["occurred_at"], "2026-08-21T01:02:03Z")
        self.assertEqual(
            data["history"]["acknowledged_at"],
            "2026-08-21T01:02:04Z",
        )
        self.assertIsNone(data["history"]["resolved_at"])
        self.assertNotIn("detail", data)
        self.assertNotIn("context", data)

    def test_snapshot_filters_source_and_calculates_filtered_level(self):
        ids = iter(("bus", "axis-warning", "axis-fault"))
        manager = DiagnosticManager(id_factory=lambda: next(ids))
        manager.detect(
            BUS_PROCESS_DATA_INCOMPLETE,
            DiagnosticSource(DiagnosticSourceType.BUS, 0),
            at=NOW,
        )
        manager.detect(
            AXIS_DRIVE_WARNING,
            DiagnosticSource(DiagnosticSourceType.AXIS, 0),
            at=NOW,
        )
        manager.detect(
            AXIS_DRIVE_FAULT,
            DiagnosticSource(DiagnosticSourceType.AXIS, 1),
            at=NOW,
        )

        axes = diagnostic_status_snapshot(
            runtime(manager),
            source_type=DiagnosticSourceType.AXIS,
        )
        axis_zero = diagnostic_status_snapshot(
            runtime(manager),
            source=DiagnosticSource(DiagnosticSourceType.AXIS, 0),
        )

        self.assertEqual(axes["level"], "fault")
        self.assertEqual(
            [item["diagnostic_id"] for item in axes["statuses"]],
            ["axis-fault", "axis-warning"],
        )
        self.assertEqual(axis_zero["level"], "alarm")
        self.assertEqual(len(axis_zero["statuses"]), 1)

    def test_server_status_exposes_all_active_diagnostics(self):
        manager = DiagnosticManager(id_factory=lambda: "bus-fault")
        manager.detect(
            BUS_PROCESS_DATA_INCOMPLETE,
            DiagnosticSource(DiagnosticSourceType.BUS, 0),
            at=NOW,
        )

        session = ServerSession(
            InitializationStatus.ready(),
            diagnostic_manager=manager,
        )
        data = server_status_message(
            runtime(manager),
            {
                "server_session": session,
                "initialization_status": session.initialization_status,
                "diagnostic_manager": manager,
            },
        )

        self.assertEqual(data["diagnostic_status"]["level"], "fault")
        self.assertEqual(
            data["diagnostic_status"]["statuses"][0]["diagnostic_id"],
            "bus-fault",
        )


if __name__ == "__main__":
    unittest.main()
