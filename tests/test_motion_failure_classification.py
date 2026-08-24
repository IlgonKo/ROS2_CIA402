import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from motion_server.api.validator import (
    INT32_MAX,
    UINT32_MAX,
    require_int32,
    require_uint32,
)
from motion_server.failure import (
    DeviceAccessException,
    InvalidArgumentException,
    InvalidStateException,
    LimitViolationException,
    ResourceNotFoundException,
    UnsupportedOperationException,
)
from motion_server.handlers.command.motion import command_position_axes
from motion_server.handlers.command.jog import start_jog, stop_jog
from motion_server.handlers.command.axis_state import disable, stop_axes
from motion_server.handlers.command.trajectory import move, stop
from motion_server.handlers.command.axis_state import set_controlword
from motion_server.handlers.command.homing import start_homing
from motion_server.handlers.parameter_access.ethercat import save_parameters


def trajectory_runtime():
    runtime = Mock()
    runtime.slaves = [SimpleNamespace()]
    runtime.sync_trajectory_to_actual_positions = Mock()
    return runtime


def call_move(message, *, faults=(), disabled=(), state_value=None):
    runtime = trajectory_runtime()
    state = {} if state_value is None else state_value
    move(
        message,
        runtime,
        state,
        axis_count=lambda runtime: len(runtime.slaves),
        faulted_axes=lambda runtime: list(faults),
        disabled_operation_axes=lambda runtime, axes: list(disabled),
        hold_faulted_axes=Mock(),
        ensure_csp_mode=Mock(),
    )
    return state


class NumericRangeFailureTest(unittest.TestCase):
    def test_non_numeric_value_is_invalid_argument(self):
        with self.assertRaises(InvalidArgumentException):
            require_int32("not-a-number", "target_position")

    def test_int32_overflow_is_invalid_argument(self):
        with self.assertRaises(InvalidArgumentException):
            require_int32(INT32_MAX + 1, "target_position")

    def test_uint32_overflow_is_invalid_argument(self):
        with self.assertRaises(InvalidArgumentException):
            require_uint32(UINT32_MAX + 1, "profile_velocity")


class TrajectoryFailureClassificationTest(unittest.TestCase):
    def test_rejected_request_preserves_active_trajectory_state(self):
        active_trajectory = {
            "active": True,
            "state": "running",
            "axes": [0],
            "points": [{"positions": [0]}],
        }
        state = {"trajectory": active_trajectory}
        with self.assertRaises(InvalidArgumentException):
            call_move(
                {"axes": [0], "points": [None]},
                state_value=state,
            )
        self.assertIs(state["trajectory"], active_trajectory)

    def test_invalid_point_shape_is_invalid_argument(self):
        with self.assertRaises(InvalidArgumentException):
            call_move({"axes": [0], "points": [None]})

    def test_missing_points_is_invalid_argument(self):
        with self.assertRaises(InvalidArgumentException):
            call_move({"axes": [0], "points": []})

    def test_unknown_axis_is_resource_not_found(self):
        with self.assertRaises(ResourceNotFoundException):
            call_move({"axes": [1], "points": [{"positions": [0]}]})

    def test_faulted_axis_is_invalid_state(self):
        with self.assertRaises(InvalidStateException):
            call_move(
                {"axes": [0], "points": [{"positions": [0]}]},
                faults=[0],
            )

    def test_disabled_axis_is_invalid_state(self):
        with self.assertRaises(InvalidStateException):
            call_move(
                {"axes": [0], "points": [{"positions": [0]}]},
                disabled=[0],
            )

    @patch(
        "motion_server.handlers.command.trajectory.validate_trajectory_limits",
        return_value="configured velocity limit exceeded",
    )
    def test_trajectory_limit_failure_is_limit_violation(self, validate):
        with self.assertRaises(LimitViolationException):
            call_move(
                {
                    "axes": [0],
                    "points": [
                        {"positions": [0], "time_from_start": 0.0},
                        {"positions": [1], "time_from_start": 1.0},
                    ],
                }
            )

    def test_rejected_stop_preserves_active_trajectory_state(self):
        active_trajectory = {"active": True, "state": "running", "axes": [0]}
        state = {"trajectory": active_trajectory}
        with self.assertRaises(UnsupportedOperationException):
            stop(
                {
                    "cmd": "system/axes/trajectory_stop",
                    "axes": [0],
                    "mode": "immediate",
                },
                trajectory_runtime(),
                state,
                None,
            )
        self.assertIs(state["trajectory"], active_trajectory)


class RemainingCommandFailureContractTest(unittest.TestCase):
    def test_position_command_in_non_position_mode_is_invalid_state(self):
        runtime = Mock()
        runtime.slaves = [
            SimpleNamespace(txpdo=SimpleNamespace(statusword=0x0027)),
        ]
        state = {
            "motion_modes": ["pv"],
            "target_positions": [10.0],
        }
        with self.assertRaises(InvalidStateException):
            command_position_axes(
                runtime,
                state,
                [0],
                [20.0],
                "system/axis/move_abs",
            )
        self.assertEqual(state["target_positions"], [10.0])

    @patch("motion_server.handlers.command.motion.command_profile_positions")
    def test_mixed_position_modes_return_partial_failure(self, command_positions):
        runtime = Mock()
        runtime.slaves = [
            SimpleNamespace(txpdo=SimpleNamespace(statusword=0x0027)),
            SimpleNamespace(txpdo=SimpleNamespace(statusword=0x0027)),
        ]
        state = {
            "motion_modes": ["pp", "pv"],
            "target_positions": [10.0, 20.0],
        }
        result = command_position_axes(
            runtime,
            state,
            [0, 1],
            [30.0, 40.0],
            "system/axes/move_abs",
        )
        self.assertEqual(result.succeeded, [0])
        self.assertEqual([item.target for item in result.failed], [1])
        self.assertEqual(state["target_positions"], [30.0, 20.0])

    @patch(
        "motion_server.handlers.command.axis_state.set_axis_controlword",
        side_effect=DeviceAccessException("axis_controlword_write"),
    )
    def test_failed_stop_preserves_active_trajectory(self, set_controlword):
        active_trajectory = {"active": True, "axes": [0], "state": "running"}
        runtime = Mock()
        runtime.slaves = [
            SimpleNamespace(
                txpdo=SimpleNamespace(statusword=0x0027, actual_position=0),
                rxpdo=SimpleNamespace(controlword=0x000F),
            ),
        ]
        state = {
            "trajectory": active_trajectory,
            "homing": {"active": False},
            "motion_modes": ["pp"],
            "target_positions": [0.0],
        }
        with self.assertRaises(DeviceAccessException):
            stop_axes(
                {"cmd": "system/axis/stop", "axis": 0},
                runtime,
                state,
                {"id": "client-1"},
            )
        self.assertIs(state["trajectory"], active_trajectory)

    @patch(
        "motion_server.handlers.command.axis_state.set_axis_controlword",
        side_effect=DeviceAccessException("axis_controlword_write"),
    )
    def test_failed_disable_preserves_active_trajectory(self, set_controlword):
        active_trajectory = {"active": True, "axes": [0], "state": "running"}
        runtime = Mock()
        runtime.slaves = [
            SimpleNamespace(txpdo=SimpleNamespace(actual_position=0)),
        ]
        state = {
            "trajectory": active_trajectory,
            "homing": {"active": False},
            "target_positions": [0.0],
        }
        with self.assertRaises(DeviceAccessException):
            disable(
                {"cmd": "system/axis/disable", "axis": 0},
                runtime,
                state,
                {"id": "client-1"},
            )
        self.assertIs(state["trajectory"], active_trajectory)

    @patch(
        "motion_server.handlers.command.jog.configure_motion_mode",
        side_effect=OSError("mode write failed"),
    )
    def test_failed_jog_start_does_not_record_previous_mode(self, configure):
        runtime = Mock()
        runtime.slaves = [
            SimpleNamespace(txpdo=SimpleNamespace(statusword=0x0027)),
        ]
        state = {
            "motion_modes": ["pp"],
            "jog_previous_modes": [None],
            "target_positions": [0.0],
        }
        with self.assertRaises(DeviceAccessException):
            start_jog(
                {
                    "cmd": "system/axis/jog_start",
                    "axis": 0,
                    "direction": "positive",
                },
                runtime,
                state,
                None,
            )
        self.assertIsNone(state["jog_previous_modes"][0])

    @patch(
        "motion_server.handlers.command.jog.configure_motion_mode",
        side_effect=OSError("mode restore failed"),
    )
    @patch("motion_server.handlers.command.jog.exchange")
    def test_failed_jog_stop_preserves_previous_mode(self, exchange, configure):
        runtime = Mock()
        runtime.slaves = [
            SimpleNamespace(
                txpdo=SimpleNamespace(statusword=0x0027),
                rxpdo=SimpleNamespace(controlword=0x000F),
            ),
        ]
        state = {
            "motion_modes": ["jog"],
            "jog_previous_modes": ["csp"],
            "target_positions": [0.0],
        }
        with self.assertRaises(DeviceAccessException):
            stop_jog(
                {"cmd": "system/axis/jog_stop", "axis": 0},
                runtime,
                state,
                None,
            )
        self.assertEqual(state["jog_previous_modes"][0], "csp")

    def test_manual_controlword_invalid_value_is_invalid_argument(self):
        runtime = SimpleNamespace(slaves=[SimpleNamespace()])
        with self.assertRaises(InvalidArgumentException):
            set_controlword(
                {
                    "cmd": "system/axis/manualCW",
                    "axis": 0,
                    "controlword": "invalid",
                },
                runtime,
                {"target_positions": [0]},
            )

    def test_manual_controlword_unknown_axis_is_resource_not_found(self):
        runtime = SimpleNamespace(slaves=[SimpleNamespace()])
        with self.assertRaises(ResourceNotFoundException):
            set_controlword(
                {
                    "cmd": "system/axis/manualCW",
                    "axis": 2,
                    "controlword": "0x000F",
                },
                runtime,
                {"target_positions": [0]},
            )

    def test_parameter_save_unknown_axis_is_resource_not_found(self):
        runtime = SimpleNamespace(slaves=[SimpleNamespace()])
        with self.assertRaises(ResourceNotFoundException):
            save_parameters(
                {
                    "cmd": "system/axis/param_save",
                    "axis": 2,
                },
                runtime,
                None,
            )

    def test_rejected_homing_preserves_active_homing_state(self):
        active_homing = {
            "active": True,
            "state": "running",
            "axes": [0],
        }
        state = {"homing": active_homing}
        runtime = SimpleNamespace(
            slaves=[SimpleNamespace(txpdo=SimpleNamespace(statusword=0))],
        )
        with self.assertRaises(InvalidStateException):
            start_homing(
                {"cmd": "system/axis/home", "axis": 0},
                runtime,
                state,
                None,
            )
        self.assertIs(state["homing"], active_homing)


if __name__ == "__main__":
    unittest.main()
