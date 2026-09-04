import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from motion_server.app.axis_parameters import (
    AxisParameterRuntimeCache,
    axis_parameter_key,
)
from motion_server.app.recovery_refresh import (
    RecoveryType,
    refresh_after_recovery,
)
from motion_server.app.runtime_parameters import (
    RuntimeParameterAddress,
    RuntimeParameterCache,
    RuntimeParameterDefinition,
)
from motion_server.diagnostic import (
    DiagnosticManager,
    DiagnosticSource,
    DiagnosticSourceType,
    PARAMETER_REFRESH_FAILED,
)


class RuntimeParameterCacheModelTest(unittest.TestCase):
    def test_runtime_parameter_cache_stores_value_with_address_and_validity(self):
        timestamp = datetime(2026, 9, 4, tzinfo=timezone.utc)
        cache = RuntimeParameterCache(clock=lambda: timestamp)
        definition = RuntimeParameterDefinition(
            key="io.io0.iol.port1.vendor_name",
            address=RuntimeParameterAddress(
                "io",
                0,
                "iol_isdu",
                module=1,
                port=1,
                index=0x0012,
                subindex=0,
            ),
            name="Vendor name",
            data_type="string",
            access="ro",
            used_by=("status",),
        )

        cache.register(definition)
        value = cache.update(definition.key, "Balluff")

        self.assertEqual(value.value, "Balluff")
        self.assertTrue(value.valid)
        self.assertEqual(value.updated_at, timestamp)
        self.assertEqual(value.definition.address.domain, "iol_isdu")
        self.assertEqual(cache.get(definition.key), value)

    def test_runtime_parameter_cache_invalidates_existing_value(self):
        cache = RuntimeParameterCache()
        definition = RuntimeParameterDefinition(
            key="axis.0.motion_limits",
            address=RuntimeParameterAddress(
                "axis",
                0,
                "ethercat_od_group",
                role="motion_limits",
            ),
            name="Motion limits",
            data_type="float[]",
        )

        cache.register(definition)
        cache.update(definition.key, [1, 2, 3, 4])
        invalid = cache.invalidate(definition.key, RuntimeError("readback failed"))

        self.assertFalse(invalid.valid)
        self.assertEqual(invalid.value, [1, 2, 3, 4])
        self.assertIn("readback failed", invalid.last_error)


class AxisRuntimeParameterProjectionTest(unittest.TestCase):
    def test_axis_cache_updates_common_runtime_parameter_values(self):
        axis_cache = AxisParameterRuntimeCache(1)

        axis_cache.update_axis(
            0,
            user_position_unit=0x0100,
            converting_unit_exponents=[6, 3, 3, 3],
            motion_limits=[200, -200, 1000, 1000],
            axis_metadata={"position_unit": "mm"},
        )

        unit = axis_cache.parameter_cache.get(
            axis_parameter_key(0, "user_position_unit")
        )
        motion_limits = axis_cache.parameter_cache.get(
            axis_parameter_key(0, "motion_limits")
        )
        metadata = axis_cache.parameter_cache.get(
            axis_parameter_key(0, "axis_metadata")
        )

        self.assertEqual(unit.value, 0x0100)
        self.assertEqual(unit.definition.address.index, 0x216E)
        self.assertEqual(motion_limits.value, [200, -200, 1000, 1000])
        self.assertEqual(metadata.source, "runtime_projection")

    def test_axis_cache_invalidation_marks_parameter_values_invalid(self):
        axis_cache = AxisParameterRuntimeCache(1)
        axis_cache.update_axis(0, motion_limits=[200, -200, 1000, 1000])

        invalidated = axis_cache.invalidate_axis(
            0,
            "refresh failed",
            fields=("motion_limits",),
        )

        self.assertEqual(len(invalidated), 1)
        self.assertFalse(invalidated[0].valid)
        self.assertEqual(invalidated[0].value, [200, -200, 1000, 1000])
        self.assertEqual(axis_cache.parameter_values(0, valid=False), invalidated)


class RecoveryRefreshDiagnosticTest(unittest.TestCase):
    def test_recovery_refresh_failure_invalidates_cache_and_records_diagnostic(self):
        diagnostics = DiagnosticManager(id_factory=lambda: "parameter-refresh")
        runtime = SimpleNamespace(
            slaves=[object()],
            axis_parameters=AxisParameterRuntimeCache(1),
            diagnostic_manager=diagnostics,
        )
        runtime.axis_parameters.update_axis(
            0,
            motion_limits=[200, -200, 1000, 1000],
        )

        with (
            patch(
                "motion_server.app.recovery_refresh.refresh_axis_parameter_cache",
                side_effect=RuntimeError("unit read failed"),
            ),
            self.assertRaisesRegex(RuntimeError, "unit read failed"),
        ):
            refresh_after_recovery(runtime, RecoveryType.AXIS_RESTART, (0,))

        source = DiagnosticSource(DiagnosticSourceType.AXIS, 0)
        status = diagnostics.status_for(PARAMETER_REFRESH_FAILED.code, source)
        self.assertIsNotNone(status)
        self.assertEqual(status.context["recovery_type"], "axis_restart")
        self.assertTrue(runtime.axis_parameters.parameter_values(0, valid=False))

    def test_successful_recovery_refresh_resolves_existing_refresh_fault(self):
        diagnostics = DiagnosticManager(id_factory=lambda: "parameter-refresh")
        source = DiagnosticSource(DiagnosticSourceType.AXIS, 0)
        diagnostics.detect(PARAMETER_REFRESH_FAILED, source)
        runtime = SimpleNamespace(
            slaves=[object()],
            axis_parameters=AxisParameterRuntimeCache(1),
            diagnostic_manager=diagnostics,
        )

        with patch(
            "motion_server.app.recovery_refresh.refresh_axis_parameter_cache",
            return_value="axis-0",
        ):
            result = refresh_after_recovery(
                runtime,
                RecoveryType.AXIS_RESTART,
                (0,),
            )

        self.assertEqual(result, ("axis-0",))
        self.assertIsNotNone(
            diagnostics.status_for(PARAMETER_REFRESH_FAILED.code, source)
            .history
            .resolved_at
        )


if __name__ == "__main__":
    unittest.main()
