import unittest
from datetime import datetime, timezone

from motion_server.diagnostic import (
    DiagnosticDefinition,
    DiagnosticLevel,
    DiagnosticManager,
    DiagnosticSource,
    DiagnosticSourceType,
    cleared_at,
)


T0 = datetime(2026, 8, 21, 1, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 8, 21, 1, 1, tzinfo=timezone.utc)
T2 = datetime(2026, 8, 21, 1, 2, tzinfo=timezone.utc)


def definition(code="AXIS_DRIVE_FAULT", *, level=DiagnosticLevel.FAULT, latching=True):
    return DiagnosticDefinition(
        code=code,
        level=level,
        title="Drive fault",
        description="The axis drive reports a fault.",
        latching=latching,
    )


def source(source_type=DiagnosticSourceType.AXIS, index=0):
    return DiagnosticSource(source_type, index)


class DiagnosticModelTest(unittest.TestCase):
    def test_normal_definition_is_not_created(self):
        with self.assertRaises(ValueError):
            definition(level=DiagnosticLevel.NORMAL)

    def test_source_type_and_index_form_the_identity(self):
        axis = source(DiagnosticSourceType.AXIS, 0)
        io = source(DiagnosticSourceType.IO, 0)

        self.assertNotEqual(axis, io)

    def test_server_and_bus_sources_use_index_zero(self):
        for source_type in (
            DiagnosticSourceType.SERVER,
            DiagnosticSourceType.BUS,
        ):
            with self.subTest(source_type=source_type):
                with self.assertRaises(ValueError):
                    source(source_type, 1)


class DiagnosticManagerTest(unittest.TestCase):
    def manager(self, *ids):
        values = iter(ids or ("diag-1",))
        return DiagnosticManager(clock=lambda: T0, id_factory=lambda: next(values))

    def test_detect_creates_one_active_occurrence(self):
        manager = self.manager("diag-1")
        diagnostic = definition()
        axis = source()

        first = manager.detect(diagnostic, axis, detail="first", context={"raw": 1})
        repeated = manager.detect(diagnostic, axis, detail="ignored")

        self.assertIs(repeated, first)
        self.assertEqual(first.diagnostic_id, "diag-1")
        self.assertEqual(first.history.occurred_at, T0)
        self.assertEqual(first.detail, "first")
        self.assertEqual(manager.active_statuses(), (first,))

    def test_non_latching_resolve_clears_without_acknowledge(self):
        manager = self.manager("diag-1")
        diagnostic = definition(level=DiagnosticLevel.ALARM, latching=False)
        alarm = manager.detect(diagnostic, source(), at=T0)

        cleared = manager.resolve(diagnostic.code, source(), at=T1)

        self.assertIs(cleared, alarm)
        self.assertEqual(cleared_at(cleared), T1)
        self.assertEqual(manager.active_statuses(), ())
        self.assertIsNone(manager.status("diag-1"))

    def test_latching_acknowledge_before_resolve_waits_for_condition(self):
        manager = self.manager("diag-1")
        diagnostic = definition()
        fault = manager.detect(diagnostic, source(), at=T0)

        active = manager.acknowledge(fault.diagnostic_id, at=T1)

        self.assertIs(active, fault)
        self.assertEqual(active.history.acknowledged_at, T1)
        self.assertIsNone(cleared_at(active))
        cleared = manager.resolve(diagnostic.code, source(), at=T2)
        self.assertEqual(cleared_at(cleared), T2)
        self.assertEqual(manager.active_statuses(), ())

    def test_latching_resolve_before_acknowledge_waits_for_user(self):
        manager = self.manager("diag-1")
        diagnostic = definition()
        fault = manager.detect(diagnostic, source(), at=T0)

        active = manager.resolve(diagnostic.code, source(), at=T1)

        self.assertIs(active, fault)
        self.assertIsNone(cleared_at(active))
        cleared = manager.acknowledge(fault.diagnostic_id, at=T2)
        self.assertEqual(cleared_at(cleared), T2)
        self.assertEqual(manager.active_statuses(), ())

    def test_redetection_before_latching_clear_restores_active_condition(self):
        manager = self.manager("diag-1")
        diagnostic = definition()
        fault = manager.detect(diagnostic, source(), at=T0)
        manager.resolve(diagnostic.code, source(), at=T1)

        repeated = manager.detect(diagnostic, source(), at=T2)

        self.assertIs(repeated, fault)
        self.assertIsNone(repeated.history.resolved_at)
        self.assertEqual(repeated.history.occurred_at, T0)

    def test_recurrence_after_clear_gets_a_new_id(self):
        manager = self.manager("diag-1", "diag-2")
        diagnostic = definition(latching=False)
        first = manager.detect(diagnostic, source(), at=T0)
        manager.resolve(diagnostic.code, source(), at=T1)

        second = manager.detect(diagnostic, source(), at=T2)

        self.assertEqual(first.diagnostic_id, "diag-1")
        self.assertEqual(second.diagnostic_id, "diag-2")
        self.assertEqual(second.history.occurred_at, T2)

    def test_same_code_is_unique_per_source_type_and_index(self):
        manager = self.manager("axis-0", "io-0", "axis-1")
        diagnostic = definition()

        axis_zero = manager.detect(diagnostic, source(DiagnosticSourceType.AXIS, 0))
        io_zero = manager.detect(diagnostic, source(DiagnosticSourceType.IO, 0))
        axis_one = manager.detect(diagnostic, source(DiagnosticSourceType.AXIS, 1))

        self.assertEqual(
            manager.active_statuses(),
            (axis_zero, io_zero, axis_one),
        )

    def test_current_level_is_fault_alarm_or_normal(self):
        manager = self.manager("alarm", "fault")
        self.assertIs(manager.current_level(), DiagnosticLevel.NORMAL)
        manager.detect(
            definition("BUS_WKC_DEGRADED", level=DiagnosticLevel.ALARM),
            source(DiagnosticSourceType.BUS),
        )
        self.assertIs(manager.current_level(), DiagnosticLevel.ALARM)
        manager.detect(definition(), source())
        self.assertIs(manager.current_level(), DiagnosticLevel.FAULT)
        self.assertIs(
            manager.current_level(source(DiagnosticSourceType.BUS)),
            DiagnosticLevel.ALARM,
        )

    def test_unknown_acknowledge_and_resolve_are_rejected(self):
        manager = self.manager()

        with self.assertRaises(KeyError):
            manager.acknowledge("missing")
        with self.assertRaises(KeyError):
            manager.resolve("MISSING", source())

    def test_active_code_cannot_change_definition(self):
        manager = self.manager("diag-1")
        manager.detect(definition(), source())

        with self.assertRaises(ValueError):
            manager.detect(
                DiagnosticDefinition(
                    code="AXIS_DRIVE_FAULT",
                    level=DiagnosticLevel.ALARM,
                    title="Different",
                    description="Different contract",
                    latching=False,
                ),
                source(),
            )

    def test_acknowledge_faults_selects_source_and_excludes_alarm(self):
        manager = self.manager("axis-fault", "axis-alarm", "other-fault")
        axis_zero = source(DiagnosticSourceType.AXIS, 0)
        axis_one = source(DiagnosticSourceType.AXIS, 1)
        fault = manager.detect(definition(), axis_zero, at=T0)
        alarm = manager.detect(
            definition(
                "AXIS_WARNING",
                level=DiagnosticLevel.ALARM,
                latching=False,
            ),
            axis_zero,
            at=T0,
        )
        other = manager.detect(definition(), axis_one, at=T0)

        acknowledged = manager.acknowledge_faults(source=axis_zero, at=T1)

        self.assertEqual(acknowledged, (fault,))
        self.assertEqual(fault.history.acknowledged_at, T1)
        self.assertIsNone(alarm.history.acknowledged_at)
        self.assertIsNone(other.history.acknowledged_at)
        self.assertTrue(manager.has_active_fault(source=axis_zero))
        self.assertTrue(
            manager.has_active_fault(source_type=DiagnosticSourceType.AXIS)
        )


if __name__ == "__main__":
    unittest.main()
