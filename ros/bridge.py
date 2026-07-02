from pathlib import Path
import json
import os
import socket
import sys
import threading
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import rclpy
from rclpy.action import ActionServer
from rclpy.action import CancelResponse
from rclpy.action import GoalResponse
from rclpy.node import Node
from control_msgs.action import FollowJointTrajectory
from rcl_interfaces.msg import SetParametersResult
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray
from std_msgs.msg import Int32MultiArray
from std_msgs.msg import Empty
from std_msgs.msg import String
from trajectory_msgs.msg import JointTrajectory
from trajectory_msgs.msg import JointTrajectoryPoint

from ros.axis_runtime_config import get_axis_count
from ros.axis_runtime_config import get_axis_names


DEFAULT_HOST = "192.168.0.12"
DEFAULT_PORT = 15000
RECONNECT_PERIOD = 1.0
REPEAT_TOLERANCE = 10.0
DEFAULT_ACTION_GOAL_TOLERANCE = 0.01
DEFAULT_ACTION_RESULT_TIMEOUT = 0.0


class Cia402CommandBridgeNode(Node):
    def __init__(self):
        super().__init__("ros_command_bridge")

        self.axis_count = get_axis_count()
        self.axis_names = get_axis_names()
        self.host = os.environ.get(
            "CIA402_AXIS_SERVER_HOST",
            os.environ.get("CIA402_PYSOEM_HOST", DEFAULT_HOST),
        )
        self.port = int(
            os.environ.get(
                "PYSOEM_AXIS_SERVER_PORT",
                DEFAULT_PORT,
            )
        )
        self.auto_request_authority = (
            os.environ.get("CIA402_AUTO_REQUEST_AUTHORITY", "1").strip() != "0"
        )
        self.action_goal_tolerance = float(
            os.environ.get(
                "CIA402_ACTION_GOAL_TOLERANCE",
                str(DEFAULT_ACTION_GOAL_TOLERANCE),
            )
        )
        self.action_result_timeout = float(
            os.environ.get(
                "CIA402_ACTION_RESULT_TIMEOUT",
                str(DEFAULT_ACTION_RESULT_TIMEOUT),
            )
        )
        self.sock = None
        self.sock_file = None
        self.sock_lock = threading.Lock()
        self.feedback_lock = threading.Lock()
        self.latest_actual_positions = [0.0 for _ in range(self.axis_count)]
        self.latest_actual_velocities = [0.0 for _ in range(self.axis_count)]
        self.position_counts_per_unit = float(
            os.environ.get(
                "CIA402_POSITION_COUNTS_PER_UNIT",
                os.environ.get("PYSOEM_CSP_COUNTS_PER_UNIT", "1.0"),
            )
        )
        self.stop_event = threading.Event()
        self.motion_limits = [
            [0.0, 0.0, 0.0, 0.0]
            for _ in range(self.axis_count)
        ]
        self.declare_motion_limit_parameters()
        self.add_on_set_parameters_callback(self.parameter_callback)

        self.target_sub = self.create_subscription(
            Float64MultiArray,
            "/target_positions",
            self.target_position_callback,
            10,
        )
        self.joint_trajectory_sub = self.create_subscription(
            JointTrajectory,
            "/joint_trajectory",
            self.joint_trajectory_callback,
            10,
        )

        self.motion_limit_sub = self.create_subscription(
            Float64MultiArray,
            "/motion_limits",
            self.motion_limit_callback,
            10,
        )
        self.alarm_ack_sub = self.create_subscription(
            Empty,
            "/alarm_ack",
            self.alarm_ack_callback,
            10,
        )
        self.repeat_motion_sub = self.create_subscription(
            String,
            "/repeat_motion_command",
            self.repeat_motion_callback,
            10,
        )
        self.motion_mode_sub = self.create_subscription(
            String,
            "/motion_mode",
            self.motion_mode_callback,
            10,
        )
        self.controlword_sub = self.create_subscription(
            Int32MultiArray,
            "/controlword",
            self.controlword_callback,
            10,
        )
        self.jog_position_sub = self.create_subscription(
            Float64MultiArray,
            "/jog_position",
            self.jog_position_callback,
            10,
        )
        self.command_authority_request_sub = self.create_subscription(
            Empty,
            "/command_authority/request",
            self.command_authority_request_callback,
            10,
        )
        self.command_authority_release_sub = self.create_subscription(
            Empty,
            "/command_authority/release",
            self.command_authority_release_callback,
            10,
        )

        self.target_position_pub = self.create_publisher(
            Float64MultiArray,
            "/target_position_feedback",
            10,
        )
        self.actual_position_pub = self.create_publisher(
            Float64MultiArray,
            "/actual_positions",
            10,
        )
        self.actual_velocity_pub = self.create_publisher(
            Float64MultiArray,
            "/actual_velocities",
            10,
        )
        self.joint_state_pub = self.create_publisher(
            JointState,
            "/joint_states",
            10,
        )
        self.statusword_pub = self.create_publisher(
            Int32MultiArray,
            "/statuswords",
            10,
        )
        self.diagnostics_pub = self.create_publisher(
            Int32MultiArray,
            "/drive_diagnostics",
            10,
        )
        self.motion_limit_pub = self.create_publisher(
            Float64MultiArray,
            "/motion_limits_feedback",
            10,
        )
        self.motion_mode_pub = self.create_publisher(
            String,
            "/motion_modes_feedback",
            10,
        )
        self.command_authority_pub = self.create_publisher(
            String,
            "/command_authority/status",
            10,
        )
        self.command_rejected_pub = self.create_publisher(
            String,
            "/command_rejected",
            10,
        )
        self.follow_joint_trajectory_server = ActionServer(
            self,
            FollowJointTrajectory,
            "cia402_joint_trajectory_controller/follow_joint_trajectory",
            execute_callback=self.execute_follow_joint_trajectory,
            goal_callback=self.follow_joint_trajectory_goal_callback,
            cancel_callback=self.follow_joint_trajectory_cancel_callback,
        )

        self.reader_thread = threading.Thread(
            target=self.connection_loop,
            daemon=True,
        )
        self.repeat_enabled = False
        self.repeat_points = None
        self.repeat_period = 2.0
        self.repeat_index = 0
        self.repeat_wait_until = 0.0
        self.repeat_waiting_to_send = False
        self.last_sent_repeat_target = None
        self.reader_thread.start()

        self.get_logger().info(
            f"CIA402 bridge started. axes={self.axis_count} "
            f"target={self.host}:{self.port} "
            f"position_counts_per_unit={self.position_counts_per_unit:g}"
        )

    def declare_motion_limit_parameters(self):
        for axis_index in range(self.axis_count):
            prefix = f"axis_{axis_index}"
            self.declare_parameter(f"{prefix}.max_velocity", 0.0)
            self.declare_parameter(f"{prefix}.acceleration", 0.0)
            self.declare_parameter(f"{prefix}.deceleration", 0.0)
            self.declare_parameter(f"{prefix}.jerk", 0.0)

    def parameter_callback(self, parameters):
        limits = [list(values) for values in self.motion_limits]
        changed = False

        for parameter in parameters:
            parts = parameter.name.split(".")
            if len(parts) != 2 or not parts[0].startswith("axis_"):
                continue

            try:
                axis_index = int(parts[0].split("_", 1)[1])
            except ValueError:
                continue

            field_map = {
                "max_velocity": 0,
                "acceleration": 1,
                "deceleration": 2,
                "jerk": 3,
            }
            if axis_index < 0 or axis_index >= self.axis_count:
                return SetParametersResult(
                    successful=False,
                    reason=f"Invalid axis index: {axis_index}",
                )
            if parts[1] not in field_map:
                continue

            limits[axis_index][field_map[parts[1]]] = float(parameter.value)
            changed = True

        if changed:
            self.motion_limits = limits
            self.get_logger().warn(
                "Ignoring ROS motion limit parameter update. "
                "Configure limits from Axis Panel."
            )

        return SetParametersResult(successful=True)

    def target_position_callback(self, msg):
        if len(msg.data) < self.axis_count:
            self.get_logger().warn(
                f"Invalid /target_positions. Expected {self.axis_count} values."
            )
            return

        self.send_trajectory_command(
            [
                {
                    "positions": [
                        float(msg.data[index])
                        for index in range(self.axis_count)
                    ],
                }
            ]
        )
        self.get_logger().info(
            "Forwarded target positions to Axis Server: "
            f"{list(msg.data[:self.axis_count])}"
        )

    def joint_trajectory_callback(self, msg):
        if not msg.points:
            self.get_logger().warn("Invalid /joint_trajectory. No points.")
            return

        command_points = self.map_joint_trajectory_points(msg)
        if command_points is None:
            return

        self.send_trajectory_command(command_points)
        self.get_logger().info(
            "Forwarded JointTrajectory to Axis Server: "
            f"points={len(command_points)}"
        )

    def map_joint_trajectory_points(self, trajectory):
        command_points = []
        for point in trajectory.points:
            positions = self.map_joint_positions(trajectory.joint_names, point.positions)
            if positions is None:
                return None

            command_point = {
                "positions": positions,
                "time_from_start": self.duration_to_seconds(point.time_from_start),
            }
            velocities = self.map_joint_optional_values(
                trajectory.joint_names,
                point.velocities,
                "velocities",
            )
            if velocities is not None:
                command_point["velocities"] = velocities
            accelerations = self.map_joint_optional_values(
                trajectory.joint_names,
                point.accelerations,
                "accelerations",
            )
            if accelerations is not None:
                command_point["accelerations"] = accelerations
            command_points.append(command_point)
        return command_points

    def map_joint_positions(self, joint_names, positions):
        if not joint_names:
            if len(positions) < self.axis_count:
                self.get_logger().warn(
                    "Invalid /joint_trajectory. Expected "
                    f"{self.axis_count} positions when joint_names is empty."
                )
                return None

            return [
                float(positions[index])
                for index in range(self.axis_count)
            ]

        if len(positions) < len(joint_names):
            self.get_logger().warn(
                "Invalid /joint_trajectory. positions length is smaller than "
                "joint_names length."
            )
            return None

        position_by_name = {
            name: float(positions[index])
            for index, name in enumerate(joint_names)
        }
        expected_names = list(self.axis_names[:self.axis_count])

        missing_names = [
            name
            for name in expected_names
            if name not in position_by_name
        ]
        if missing_names:
            self.get_logger().warn(
                "Invalid /joint_trajectory. Missing joints: "
                f"{missing_names}. Expected joints: {expected_names}"
            )
            return None

        unknown_names = [
            name
            for name in joint_names
            if name not in expected_names
        ]
        if unknown_names:
            self.get_logger().warn(
                "Ignoring unknown joints in /joint_trajectory: "
                f"{unknown_names}"
            )

        return [
            position_by_name[name]
            for name in expected_names
        ]

    def map_joint_optional_values(self, joint_names, values, field_name):
        if not values:
            return None
        if not joint_names:
            if len(values) < self.axis_count:
                self.get_logger().warn(
                    f"Ignoring {field_name}; expected {self.axis_count} values."
                )
                return None
            return [
                float(values[index])
                for index in range(self.axis_count)
            ]
        if len(values) < len(joint_names):
            self.get_logger().warn(
                f"Ignoring {field_name}; length is smaller than joint_names."
            )
            return None
        value_by_name = {
            name: float(values[index])
            for index, name in enumerate(joint_names)
        }
        expected_names = list(self.axis_names[:self.axis_count])
        if any(name not in value_by_name for name in expected_names):
            self.get_logger().warn(
                f"Ignoring {field_name}; missing expected joints."
            )
            return None
        return [
            value_by_name[name]
            for name in expected_names
        ]

    def follow_joint_trajectory_goal_callback(self, goal_request):
        trajectory = goal_request.trajectory
        if not trajectory.points:
            self.get_logger().warn("Rejected FollowJointTrajectory goal: no points.")
            return GoalResponse.REJECT

        for point in trajectory.points:
            if self.map_joint_positions(trajectory.joint_names, point.positions) is None:
                self.get_logger().warn(
                    "Rejected FollowJointTrajectory goal: invalid joint mapping."
                )
                return GoalResponse.REJECT

        self.get_logger().info(
            "Accepted FollowJointTrajectory goal with "
            f"{len(trajectory.points)} points."
        )
        return GoalResponse.ACCEPT

    def follow_joint_trajectory_cancel_callback(self, _goal_handle):
        self.get_logger().info("Cancel requested for FollowJointTrajectory goal.")
        return CancelResponse.ACCEPT

    def execute_follow_joint_trajectory(self, goal_handle):
        trajectory = goal_handle.request.trajectory
        result = FollowJointTrajectory.Result()
        command_points = self.map_joint_trajectory_points(trajectory)
        if command_points is None:
            result.error_code = FollowJointTrajectory.Result.INVALID_JOINTS
            result.error_string = "Invalid joint mapping."
            goal_handle.abort()
            return result

        if not self.send_trajectory_command(command_points):
            result.error_code = FollowJointTrajectory.Result.INVALID_GOAL
            result.error_string = "Axis Server is not connected."
            goal_handle.abort()
            return result

        final_target = command_points[-1]["positions"]
        if not self.wait_for_action_target(goal_handle, final_target, time.monotonic()):
            result.error_code = FollowJointTrajectory.Result.GOAL_TOLERANCE_VIOLATED
            result.error_string = "Final target was not reached before timeout."
            goal_handle.abort()
            return result

        goal_handle.succeed()
        result.error_code = FollowJointTrajectory.Result.SUCCESSFUL
        result.error_string = "Trajectory accepted by Axis Server."
        return result

    def send_trajectory_command(self, points):
        self.request_axis_server_authority()
        return self.send_json(
            {
                "type": "trajectory_command",
                "axes": list(range(self.axis_count)),
                "points": self.trajectory_points_to_axis_units(points),
            }
        )

    def send_trajectory_stop(self):
        self.request_axis_server_authority()
        return self.send_json({"type": "trajectory_stop", "mode": "controlled"})

    def request_axis_server_authority(self):
        self.auto_request_authority = True
        return self.send_json({"type": "command_authority_request"})

    def release_axis_server_authority(self):
        self.auto_request_authority = False
        return self.send_json({"type": "command_authority_release"})

    def trajectory_points_to_axis_units(self, points):
        converted_points = []
        for point in points:
            converted = dict(point)
            converted["positions"] = [
                self.ros_position_to_axis_position(value)
                for value in point.get("positions", [])
            ]
            if "velocities" in point:
                converted["velocities"] = [
                    self.ros_velocity_to_axis_velocity(value)
                    for value in point["velocities"]
                ]
            if "accelerations" in point:
                converted["accelerations"] = [
                    self.ros_velocity_to_axis_velocity(value)
                    for value in point["accelerations"]
                ]
            converted_points.append(converted)
        return converted_points

    def ros_position_to_axis_position(self, position):
        return float(position) * self.position_counts_per_unit

    def axis_position_to_ros_position(self, position):
        return float(position) / max(self.position_counts_per_unit, 1e-9)

    def ros_velocity_to_axis_velocity(self, velocity):
        return float(velocity) * self.position_counts_per_unit

    def publish_follow_joint_feedback(self, goal_handle, desired_positions):
        with self.feedback_lock:
            actual_positions = list(self.latest_actual_positions)
            actual_velocities = list(self.latest_actual_velocities)

        feedback = FollowJointTrajectory.Feedback()
        feedback.joint_names = list(self.axis_names[:self.axis_count])
        feedback.desired = JointTrajectoryPoint()
        feedback.desired.positions = [
            float(value)
            for value in desired_positions[:self.axis_count]
        ]
        feedback.actual = JointTrajectoryPoint()
        feedback.actual.positions = [
            float(value)
            for value in actual_positions[:self.axis_count]
        ]
        feedback.actual.velocities = [
            float(value)
            for value in actual_velocities[:self.axis_count]
        ]
        feedback.error = JointTrajectoryPoint()
        feedback.error.positions = [
            feedback.desired.positions[index] - feedback.actual.positions[index]
            for index in range(min(len(feedback.desired.positions), len(feedback.actual.positions)))
        ]
        goal_handle.publish_feedback(feedback)

    def wait_for_action_target(self, goal_handle, target_positions, start_time):
        timeout = self.duration_to_seconds(
            goal_handle.request.goal_time_tolerance
        )
        if timeout <= 0.0:
            timeout = self.action_result_timeout
        deadline = None
        if timeout > 0.0:
            deadline = start_time + timeout

        while deadline is None or time.monotonic() <= deadline:
            if goal_handle.is_cancel_requested:
                self.send_trajectory_stop()
                goal_handle.canceled()
                return False

            with self.feedback_lock:
                actual_positions = list(self.latest_actual_positions)

            if self.positions_within_tolerance(
                actual_positions,
                target_positions,
                goal_handle.request.goal_tolerance,
            ):
                self.publish_follow_joint_feedback(goal_handle, target_positions)
                return True

            self.publish_follow_joint_feedback(goal_handle, target_positions)
            time.sleep(0.05)

        return False

    def positions_within_tolerance(self, actual_positions, target_positions, tolerances):
        if len(actual_positions) < self.axis_count:
            return False

        tolerance_by_name = {
            tolerance.name: tolerance.position
            for tolerance in tolerances
            if tolerance.position > 0.0
        }

        for index, axis_name in enumerate(self.axis_names[:self.axis_count]):
            tolerance = tolerance_by_name.get(axis_name, self.action_goal_tolerance)
            if abs(float(actual_positions[index]) - float(target_positions[index])) > tolerance:
                return False

        return True

    def sleep_with_cancel(self, duration, goal_handle):
        end_time = time.monotonic() + duration
        while time.monotonic() < end_time:
            if goal_handle.is_cancel_requested:
                return
            time.sleep(min(0.05, end_time - time.monotonic()))

    @staticmethod
    def duration_to_seconds(duration):
        return float(duration.sec) + float(duration.nanosec) / 1_000_000_000.0

    def motion_limit_callback(self, msg):
        expected_values = self.axis_count * 4
        if len(msg.data) < expected_values:
            self.get_logger().warn(
                f"Invalid /motion_limits. Expected {expected_values} values."
            )
            return

        limits = []
        for index in range(self.axis_count):
            offset = index * 4
            limits.append(
                [
                    float(msg.data[offset]),
                    float(msg.data[offset + 1]),
                    float(msg.data[offset + 2]),
                    float(msg.data[offset + 3]),
                ]
            )

        self.motion_limits = limits
        self.get_logger().info(
            "Updated local ROS Bridge motion limits only. "
            "Configure Axis Server limits from Axis Panel."
        )

    def alarm_ack_callback(self, _msg):
        self.get_logger().warn(
            "Ignoring /alarm_ack in ROS Bridge. Use Axis Panel for alarm ack."
        )

    def repeat_motion_callback(self, msg):
        try:
            payload = json.loads(msg.data)
            action = str(payload.get("action", "")).lower()
        except json.JSONDecodeError:
            self.get_logger().warn(f"Invalid /repeat_motion_command JSON: {msg.data}")
            return

        if action == "stop":
            self.repeat_enabled = False
            self.repeat_points = None
            self.last_sent_repeat_target = None
            self.repeat_waiting_to_send = False
            self.get_logger().info("Stopped repeat motion")
            return

        if action != "start":
            self.get_logger().warn(f"Invalid repeat action: {action}")
            return

        points = payload.get("points", [])
        if len(points) < 2:
            self.get_logger().warn("Repeat motion requires two points")
            return

        point_a = [float(value) for value in points[0]]
        point_b = [float(value) for value in points[1]]
        if len(point_a) < self.axis_count or len(point_b) < self.axis_count:
            self.get_logger().warn(
                f"Repeat points require {self.axis_count} axis values"
            )
            return

        self.repeat_enabled = True
        self.repeat_points = [
            point_a[:self.axis_count],
            point_b[:self.axis_count],
        ]
        self.repeat_period = float(payload.get("period", 2.0))
        self.repeat_index = 0
        self.repeat_wait_until = 0.0
        self.repeat_waiting_to_send = False
        self.last_sent_repeat_target = None
        self.get_logger().info(
            f"Started repeat motion period={self.repeat_period}"
        )

    def motion_mode_callback(self, msg):
        self.get_logger().warn(
            "Ignoring /motion_mode in ROS Bridge. Trajectory commands force CSP."
        )

    def controlword_callback(self, msg):
        self.get_logger().warn(
            "Ignoring /controlword in ROS Bridge. Use Axis Panel for controlword."
        )

    def jog_position_callback(self, msg):
        self.get_logger().warn(
            "Ignoring /jog_position in ROS Bridge. Use Axis Panel for manual jog."
        )

    def command_authority_request_callback(self, _msg):
        self.request_axis_server_authority()
        self.get_logger().info(
            "Requested Axis Server command authority; auto request enabled"
        )

    def command_authority_release_callback(self, _msg):
        self.release_axis_server_authority()
        self.get_logger().info(
            "Released Axis Server command authority; auto request disabled"
        )

    def connection_loop(self):
        while not self.stop_event.is_set():
            try:
                self.connect()
                self.read_loop()
            except OSError as exc:
                self.get_logger().warn(f"Bridge disconnected: {exc}")
            except Exception as exc:
                self.get_logger().error(f"Bridge error: {exc}")
            finally:
                self.close_socket()

            time.sleep(RECONNECT_PERIOD)

    def connect(self):
        self.get_logger().info(f"Connecting to Axis Server {self.host}:{self.port}")
        sock = socket.create_connection((self.host, self.port), timeout=5.0)
        sock.settimeout(None)
        sock_file = sock.makefile("r", encoding="utf-8", newline="\n")

        with self.sock_lock:
            self.sock = sock
            self.sock_file = sock_file

        self.get_logger().info("Connected to Axis Server")
        if self.auto_request_authority:
            self.request_axis_server_authority()
        else:
            self.get_logger().info("Auto authority request is disabled")

    def read_loop(self):
        while not self.stop_event.is_set():
            line = self.sock_file.readline()
            if not line:
                raise OSError("server closed connection")

            message = json.loads(line)
            if message.get("type") == "feedback":
                self.publish_feedback(message)
            elif message.get("type") == "log":
                self.get_logger().info(message.get("text", ""))
            elif message.get("type") == "command_authority":
                self.publish_string(self.command_authority_pub, message)
                self.get_logger().info(message.get("message", ""))
            elif message.get("type") == "command_rejected":
                self.publish_string(self.command_rejected_pub, message)
                self.get_logger().warn(message.get("message", "Command rejected"))

    def publish_feedback(self, message):
        self.position_counts_per_unit = float(
            message.get(
                "position_counts_per_unit",
                message.get("csp_counts_per_unit", self.position_counts_per_unit),
            )
        )
        target_positions = [
            self.axis_position_to_ros_position(value)
            for value in list(message.get("target_positions", []))[:self.axis_count]
        ]
        actual_positions = [
            self.axis_position_to_ros_position(value)
            for value in list(message.get("actual_positions", []))[:self.axis_count]
        ]
        actual_velocities = message.get("actual_velocities", [])
        with self.feedback_lock:
            self.latest_actual_positions = [
                float(value)
                for value in actual_positions[:self.axis_count]
            ]
            self.latest_actual_velocities = [
                float(value)
                for value in list(actual_velocities)[:self.axis_count]
            ]

        self.publish_float_array(
            self.target_position_pub,
            target_positions,
        )
        self.publish_float_array(
            self.actual_position_pub,
            actual_positions,
        )
        self.publish_float_array(
            self.actual_velocity_pub,
            actual_velocities,
        )
        self.publish_joint_state(
            actual_positions,
            actual_velocities,
        )
        self.publish_statuswords(message.get("statuswords", []))
        self.publish_diagnostics(message.get("diagnostics", []))
        self.publish_float_array(
            self.motion_limit_pub,
            message.get("motion_limits", []),
        )
        self.update_motion_limits_from_feedback(message.get("motion_limits", []))
        self.publish_string(
            self.motion_mode_pub,
            {
                "motion_mode": message.get("motion_mode", ""),
                "motion_modes": message.get("motion_modes", []),
            },
        )
        self.publish_string(
            self.command_authority_pub,
            message.get("command_authority", {}),
        )
        self.update_repeat_motion(actual_positions)

    def update_repeat_motion(self, actual_positions):
        if not self.repeat_enabled or self.repeat_points is None:
            return
        if len(actual_positions) < self.axis_count:
            return

        now = time.monotonic()
        if self.last_sent_repeat_target is None:
            target = self.repeat_points[self.repeat_index]
            self.send_trajectory_command([{"positions": target}])
            self.last_sent_repeat_target = list(target)
            return

        if self.repeat_waiting_to_send or now < self.repeat_wait_until:
            return

        reached = all(
            abs(float(actual_positions[index]) - self.last_sent_repeat_target[index])
            <= REPEAT_TOLERANCE
            for index in range(self.axis_count)
        )
        if not reached:
            return

        self.repeat_wait_until = now + self.repeat_period
        self.repeat_index = 1 - self.repeat_index
        self.repeat_waiting_to_send = True
        threading.Timer(self.repeat_period, self.send_next_repeat_target).start()

    def send_next_repeat_target(self):
        if not self.repeat_enabled or self.repeat_points is None:
            return

        target = self.repeat_points[self.repeat_index]
        self.send_trajectory_command([{"positions": target}])
        self.last_sent_repeat_target = list(target)
        self.repeat_waiting_to_send = False

    def send_json(self, message):
        payload = (json.dumps(message) + "\n").encode("utf-8")

        with self.sock_lock:
            if self.sock is None:
                self.get_logger().warn("Axis Server is not connected yet")
                return False

            self.sock.sendall(payload)
            return True

    def close_socket(self):
        with self.sock_lock:
            if self.sock_file is not None:
                self.sock_file.close()
                self.sock_file = None

            if self.sock is not None:
                self.sock.close()
                self.sock = None

    def publish_float_array(self, publisher, values):
        msg = Float64MultiArray()
        msg.data = [float(value) for value in values]
        publisher.publish(msg)

    def publish_statuswords(self, values):
        msg = Int32MultiArray()
        msg.data = [int(value) for value in values]
        self.statusword_pub.publish(msg)

    def publish_joint_state(self, positions, velocities):
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = list(self.axis_names[:self.axis_count])
        msg.position = [
            float(value)
            for value in list(positions)[:self.axis_count]
        ]
        msg.velocity = [
            float(value)
            for value in list(velocities)[:self.axis_count]
        ]
        while len(msg.position) < self.axis_count:
            msg.position.append(0.0)
        while len(msg.velocity) < self.axis_count:
            msg.velocity.append(0.0)
        self.joint_state_pub.publish(msg)

    def update_motion_limits_from_feedback(self, flat_limits):
        values = list(flat_limits)
        if len(values) < self.axis_count * 4:
            return

        self.motion_limits = [
            [
                float(values[index * 4]),
                float(values[index * 4 + 1]),
                float(values[index * 4 + 2]),
                float(values[index * 4 + 3]),
            ]
            for index in range(self.axis_count)
        ]

    def publish_diagnostics(self, diagnostics):
        values = []
        for item in diagnostics:
            values.extend(
                [
                    int(item.get("error_code", 0))
                    if isinstance(item.get("error_code", 0), int)
                    else -1,
                    int(item.get("error_register", 0))
                    if isinstance(item.get("error_register", 0), int)
                    else -1,
                    int(item.get("mode_display", 0))
                    if isinstance(item.get("mode_display", 0), int)
                    else -1,
                ]
            )

        msg = Int32MultiArray()
        msg.data = values
        self.diagnostics_pub.publish(msg)

    def publish_string(self, publisher, payload):
        msg = String()
        msg.data = json.dumps(payload)
        publisher.publish(msg)

    def close(self):
        self.stop_event.set()
        self.close_socket()


def main(args=None):
    rclpy.init(args=args)
    node = Cia402CommandBridgeNode()

    try:
        rclpy.spin(node)
    finally:
        node.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
