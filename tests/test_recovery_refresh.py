import unittest
from types import SimpleNamespace
from unittest.mock import call, patch

from motion_server.app.recovery_refresh import (
    RecoveryType,
    refresh_after_recovery,
)


class RecoveryRefreshContractTest(unittest.TestCase):
    def runtime(self, axis_count=2):
        return SimpleNamespace(slaves=[object() for _ in range(axis_count)])

    def test_bus_reconnect_refreshes_every_axis(self):
        runtime = self.runtime()
        with patch(
            "motion_server.app.recovery_refresh.refresh_axis_parameter_cache",
            side_effect=("axis-0", "axis-1"),
        ) as refresh:
            result = refresh_after_recovery(
                runtime,
                RecoveryType.BUS_RECONNECT,
                (0, 1),
            )

        self.assertEqual(result, ("axis-0", "axis-1"))
        self.assertEqual(refresh.call_args_list, [call(runtime, 0), call(runtime, 1)])

    def test_axis_restart_requires_exactly_one_axis(self):
        runtime = self.runtime()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            refresh_after_recovery(
                runtime,
                RecoveryType.AXIS_RESTART,
                (0, 1),
            )

    def test_bus_reconnect_rejects_partial_refresh(self):
        with self.assertRaisesRegex(ValueError, "every Axis"):
            refresh_after_recovery(
                self.runtime(),
                RecoveryType.BUS_RECONNECT,
                (0,),
            )


if __name__ == "__main__":
    unittest.main()
