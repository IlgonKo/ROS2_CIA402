import unittest
from types import SimpleNamespace

from motion_server.app.startup import write_csp_interpolation_modes
from motion_server.app.cycle_diagnostics import velocity_anomaly_dc_snapshot
from motion_server.control.motion_controller import MotionController


class DeviceInstanceMotionConfigTest(unittest.TestCase):
    def test_disabled_dc_does_not_consume_phase_details(self):
        runtime = SimpleNamespace(cycle_time=0.01)
        cycle_stats = SimpleNamespace(latest={})
        dc_config = SimpleNamespace(
            enabled=False,
            phase_offset_ns=object(),
        )

        self.assertEqual(
            velocity_anomaly_dc_snapshot(runtime, cycle_stats, dc_config),
            "dc_enabled=False",
        )

    def test_csp_velocity_offset_is_applied_per_axis(self):
        controller = MotionController(
            2,
            0.01,
            motion_limits=[
                {
                    "max_velocity": 100.0,
                    "acceleration": 1000.0,
                    "deceleration": 1000.0,
                    "jerk": 10000.0,
                }
                for _ in range(2)
            ],
            csp_velocity_offset_enabled=(False, True),
        )
        controller.sync_trajectory_to_actual_positions([0.0, 0.0])
        controller.set_target_positions([100.0, 100.0])

        commands = None
        previous = [0, 0]
        for _ in range(20):
            commands = controller.update_commands([8, 8], previous)
            previous = [command["target_position"] for command in commands]

        self.assertEqual(commands[0]["velocity_offset"], 0)
        self.assertNotEqual(commands[1]["velocity_offset"], 0)

    def test_csp_interpolation_mode_is_written_per_axis(self):
        writes = []

        class Profile:
            def write_csp_interpolation_mode(self, runtime, axis_index, value):
                writes.append((axis_index, value))
                return value

        profiles = (Profile(), Profile())
        runtime = SimpleNamespace(
            slaves=[
                SimpleNamespace(device_profile=profile)
                for profile in profiles
            ],
        )

        write_csp_interpolation_modes(runtime, (1, 4))

        self.assertEqual(writes, [(0, 1), (1, 4)])

    def test_rejects_velocity_offset_count_mismatch(self):
        with self.assertRaisesRegex(ValueError, "one value per axis"):
            MotionController(
                2,
                0.01,
                csp_velocity_offset_enabled=(True,),
            )


if __name__ == "__main__":
    unittest.main()
