from types import SimpleNamespace
import unittest

from configuration.models import CspInterpolationMode, CspProfile
from motion_server.app.startup_logging import (
    format_listening_endpoint,
    format_startup_summary,
    startup_summary_fields,
)


def startup_configs(
    *,
    backend="pysoem",
    motion_mode="pp",
    dc_enabled=False,
    phase_lock=False,
    absolute_shift=False,
):
    server = SimpleNamespace(mode=SimpleNamespace(value="basic"))
    ethercat = SimpleNamespace(
        backend=SimpleNamespace(value=backend),
        cycle=SimpleNamespace(period=0.008, spin_wait_time=0.00015),
        dc=SimpleNamespace(
            enabled=dc_enabled,
            phase_lock=phase_lock,
            absolute_shift=absolute_shift,
            phase_offset_ns=800000,
            phase_kp=0.02,
            phase_ki=0.00001,
            phase_max_correction=0.001,
        ),
    )
    motion = SimpleNamespace(
        initial_motion_mode=motion_mode,
        csp_profile=CspProfile.TRAPEZOID,
        csp_jerk=100000.0,
        csp_interpolation_mode=CspInterpolationMode.CSP_V,
        csp_velocity_offset=True,
    )
    return server, ethercat, motion


class StartupLoggingTest(unittest.TestCase):
    def fields(self, **kwargs):
        configs = startup_configs(**kwargs)
        return dict(startup_summary_fields(*configs, axis_count=6))

    def test_common_summary_contains_only_server_runtime_fields(self):
        server, ethercat, motion = startup_configs()
        text = format_startup_summary(server, ethercat, motion, 6)

        self.assertEqual(
            text,
            "Motion Server initialized. backend=pysoem server_mode=basic "
            "axes=6 cycle_time=0.008 spin_wait_time=0.00015 "
            "motion_mode=pp dc_enabled=False",
        )
        for device_field in (
            "axis_position_counts_per_api_unit",
            "statuswords",
            "software_position_limits",
            "actual_positions",
            "AP=",
        ):
            self.assertNotIn(device_field, text)

    def test_listening_log_contains_endpoint_only(self):
        self.assertEqual(
            format_listening_endpoint("0.0.0.0", 15000),
            "Motion Server listening on 0.0.0.0:15000",
        )

    def test_disabled_dc_omits_every_dc_detail(self):
        fields = self.fields(
            dc_enabled=False,
            phase_lock=True,
            absolute_shift=True,
        )

        self.assertFalse(fields["dc_enabled"])
        self.assertNotIn("dc_phase_lock", fields)
        self.assertNotIn("dc_absolute_shift", fields)
        self.assertNotIn("dc_phase_offset_ns", fields)

    def test_mock_and_pysoem_axis_counts_remain_scalar(self):
        for backend, axis_count in (("mock", 1), ("pysoem", 6)):
            with self.subTest(backend=backend, axis_count=axis_count):
                configs = startup_configs(backend=backend)
                fields = dict(startup_summary_fields(*configs, axis_count))
                self.assertEqual(fields["backend"], backend)
                self.assertEqual(fields["axes"], axis_count)

    def test_dc_without_phase_lock_omits_shift_and_tuning(self):
        fields = self.fields(
            dc_enabled=True,
            phase_lock=False,
            absolute_shift=True,
        )

        self.assertTrue(fields["dc_enabled"])
        self.assertFalse(fields["dc_phase_lock"])
        self.assertNotIn("dc_absolute_shift", fields)
        self.assertNotIn("dc_phase_kp", fields)

    def test_phase_lock_includes_effective_shift_and_tuning(self):
        fields = self.fields(
            dc_enabled=True,
            phase_lock=True,
            absolute_shift=True,
        )

        self.assertTrue(fields["dc_absolute_shift"])
        self.assertEqual(fields["dc_phase_offset_ns"], 800000)
        self.assertEqual(fields["dc_phase_kp"], 0.02)
        self.assertEqual(fields["dc_phase_ki"], 0.00001)
        self.assertEqual(fields["dc_phase_max_correction"], 0.001)

    def test_non_csp_modes_omit_csp_fields(self):
        for motion_mode in ("pp", "pv", "jog"):
            with self.subTest(motion_mode=motion_mode):
                fields = self.fields(motion_mode=motion_mode)
                self.assertNotIn("csp_profile", fields)
                self.assertNotIn("csp_interpolation_mode", fields)

    def test_csp_mode_includes_active_csp_fields(self):
        fields = self.fields(motion_mode="csp")

        self.assertEqual(fields["csp_profile"], "trapezoid")
        self.assertEqual(fields["csp_jerk"], 100000.0)
        self.assertEqual(fields["csp_interpolation_mode"], "csp_v")
        self.assertTrue(fields["csp_velocity_offset"])


if __name__ == "__main__":
    unittest.main()
