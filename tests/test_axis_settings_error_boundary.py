import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import motion_server.api  # Complete the API package before axis_units imports it.
from motion_server.failure import InvalidArgumentException
from motion_server.handlers.command.axis_settings import (
    set_motion_limits,
    set_profile,
    set_software_position_limits,
)


def runtime():
    rxpdo = Mock()
    rxpdo.has_field.return_value = False
    return SimpleNamespace(
        slaves=[
            SimpleNamespace(
                rxpdo=rxpdo,
                motion_server_motion_limits=[100.0, -100.0, 10.0, 10.0],
            )
        ],
        set_axis_motion_limits=Mock(),
    )


def state():
    axis_devices = Mock()
    axis_devices.motion_api_to_drive.side_effect = (
        lambda axis_index, value, kind: float(value)
    )
    axis_devices.motion_drive_to_api.side_effect = (
        lambda axis_index, value, kind: float(value)
    )
    axis_devices.position_api_to_drive.side_effect = (
        lambda axis_index, value: float(value)
    )
    axis_devices.position_drive_to_api.side_effect = (
        lambda axis_index, value: float(value)
    )
    return {
        "axis_devices": axis_devices,
        "axis_metadata": [{}],
        "motion_limits": [[100.0, -100.0, 10.0, 10.0]],
        "motion_modes": ["pp"],
        "profile_settings": [[50.0, 5.0, 5.0, 0.0]],
        "software_position_limits": [[-1000, 1000]],
    }


class AxisSettingsErrorBoundaryTest(unittest.TestCase):
    def test_invalid_motion_limit_input_is_invalid_argument(self):
        with self.assertRaises(InvalidArgumentException):
            set_motion_limits(
                {
                    "cmd": "system/axis/motion_limits",
                    "axis": 0,
                    "max_acceleration": "invalid",
                },
                runtime(),
                state(),
                None,
            )

    @patch(
        "motion_server.handlers.command.axis_settings.update_axis_motion_limits",
        side_effect=ValueError("runtime failure"),
    )
    def test_motion_limit_runtime_value_error_is_not_reclassified(self, update):
        with self.assertRaisesRegex(ValueError, "runtime failure"):
            set_motion_limits(
                {"cmd": "system/axis/motion_limits", "axis": 0},
                runtime(),
                state(),
                None,
            )

    @patch("motion_server.handlers.command.axis_settings.DEVICE_PROFILE")
    def test_motion_limit_write_failure_preserves_server_state(self, profile):
        profile.write_motion_limits.side_effect = ValueError("device failure")
        active_runtime = runtime()
        active_state = state()
        previous_limits = list(active_state["motion_limits"][0])
        with self.assertRaisesRegex(ValueError, "device failure"):
            set_motion_limits(
                {
                    "cmd": "system/axis/motion_limits",
                    "axis": 0,
                    "max_acceleration": 20.0,
                },
                active_runtime,
                active_state,
                None,
            )
        self.assertEqual(active_state["motion_limits"][0], previous_limits)
        self.assertEqual(
            active_runtime.slaves[0].motion_server_motion_limits,
            previous_limits,
        )
        active_runtime.set_axis_motion_limits.assert_not_called()

    @patch(
        "motion_server.handlers.command.axis_settings.update_axis_profile_settings",
        side_effect=ValueError("device failure"),
    )
    def test_profile_device_value_error_is_not_reclassified(self, update):
        with self.assertRaisesRegex(ValueError, "device failure"):
            set_profile(
                {"cmd": "system/axis/profile", "axis": 0},
                runtime(),
                state(),
                None,
            )

    @patch("motion_server.handlers.command.axis_settings.DEVICE_PROFILE")
    def test_profile_write_failure_preserves_server_state(self, profile):
        profile.write_profile_settings.side_effect = ValueError("device failure")
        active_runtime = runtime()
        active_state = state()
        previous_settings = list(active_state["profile_settings"][0])
        with self.assertRaisesRegex(ValueError, "device failure"):
            set_profile(
                {
                    "cmd": "system/axis/profile",
                    "axis": 0,
                    "profile_acceleration": 20.0,
                },
                active_runtime,
                active_state,
                None,
            )
        self.assertEqual(active_state["profile_settings"][0], previous_settings)

    @patch("motion_server.handlers.command.axis_settings.DEVICE_PROFILE")
    def test_software_limit_device_value_error_is_not_reclassified(self, profile):
        profile.write_software_position_limits.side_effect = ValueError(
            "device failure"
        )
        with self.assertRaisesRegex(ValueError, "device failure"):
            set_software_position_limits(
                {
                    "cmd": "system/axis/software_position_limits",
                    "axis": 0,
                },
                runtime(),
                state(),
                None,
            )


if __name__ == "__main__":
    unittest.main()
