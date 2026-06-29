from pathlib import Path
import json
import sys
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from control_msgs.action import FollowJointTrajectory
from std_msgs.msg import Empty
from std_msgs.msg import Float64MultiArray
from std_msgs.msg import Int32MultiArray
from std_msgs.msg import String
from trajectory_msgs.msg import JointTrajectory
from trajectory_msgs.msg import JointTrajectoryPoint

from ros.axis_runtime_config import get_axis_names

AXES = get_axis_names()
GUI_PERIOD_MS = 50
HISTORY_SIZE = 500
REPEAT_TOLERANCE = 10.0


class TraceCanvas:
    def __init__(self, parent, axis_names, title, color_offset=0):
        self.axis_names = axis_names
        self.title = title
        self.history = [[] for _ in axis_names]
        self.colors = [
            "#ff5a5f",
            "#2ecc71",
            "#3498db",
            "#f1c40f",
            "#9b59b6",
            "#1abc9c",
        ]
        self.color_offset = color_offset
        self.canvas = tk.Canvas(parent, height=190, bg="#202020", highlightthickness=1)
        self.canvas.pack(fill="both", expand=True, padx=5, pady=5)

    def add_sample(self, values):
        for index, value in enumerate(values[:len(self.history)]):
            series = self.history[index]
            series.append(float(value))
            if len(series) > HISTORY_SIZE:
                del series[0]

    def draw(self):
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        self.canvas.delete("all")
        self.canvas.create_text(
            10,
            10,
            text=self.title,
            fill="#f2f2f2",
            anchor="nw",
        )

        if not any(self.history):
            self.canvas.create_text(
                width / 2,
                height / 2,
                text="Waiting for feedback",
                fill="#bdbdbd",
            )
            return

        all_values = [
            value
            for series in self.history
            for value in series
        ]
        minimum = min(all_values)
        maximum = max(all_values)
        if abs(maximum - minimum) < 1e-9:
            maximum = minimum + 1.0

        margin = 28
        plot_width = max(1, width - margin * 2)
        plot_height = max(1, height - margin * 2)
        zero_y = height - margin - ((0.0 - minimum) / (maximum - minimum)) * plot_height

        for grid_index in range(5):
            y = margin + grid_index * plot_height / 4
            self.canvas.create_line(margin, y, width - margin, y, fill="#3d3d3d")
        if margin <= zero_y <= height - margin:
            self.canvas.create_line(margin, zero_y, width - margin, zero_y, fill="#666666")

        for index, series in enumerate(self.history):
            if len(series) < 2:
                continue
            color = self.colors[(index + self.color_offset) % len(self.colors)]
            denominator = max(1, HISTORY_SIZE - 1)
            points = []
            start = HISTORY_SIZE - len(series)
            for sample_index, value in enumerate(series):
                x = margin + (start + sample_index) * plot_width / denominator
                y = height - margin - ((value - minimum) / (maximum - minimum)) * plot_height
                points.extend([x, y])
            self.canvas.create_line(points, fill=color, width=2)
            self.canvas.create_text(
                margin + 8 + index * 90,
                height - 14,
                text=self.axis_names[index],
                fill=color,
                anchor="w",
            )


class AxisControlPanelNode(Node):
    def __init__(self):
        super().__init__("ros_control_panel")

        self.target_positions = [0.0 for _ in AXES]
        self.actual_positions = [0.0 for _ in AXES]
        self.actual_velocities = [0.0 for _ in AXES]
        self.statuswords = [0 for _ in AXES]
        self.error_codes = [0 for _ in AXES]
        self.error_registers = [0 for _ in AXES]
        self.command_authority_text = "Authority: unknown"
        self.action_status_text = "Action server: unknown"
        self.action_result_text = "Result: none"
        self.action_feedback_text = "Feedback: none"
        self.current_goal_handle = None
        self.motion_limits = [
            [0.0, 0.0, 0.0, 0.0]
            for _ in AXES
        ]

        self.create_subscription(
            Float64MultiArray,
            "/target_position_feedback",
            self.target_position_callback,
            10,
        )

        self.create_subscription(
            Float64MultiArray,
            "/actual_positions",
            self.actual_position_callback,
            10,
        )

        self.create_subscription(
            Float64MultiArray,
            "/actual_velocities",
            self.actual_velocity_callback,
            10,
        )

        self.create_subscription(
            Float64MultiArray,
            "/motion_limits_feedback",
            self.motion_limit_callback,
            10,
        )

        self.joint_trajectory_pub = self.create_publisher(
            JointTrajectory,
            "/joint_trajectory",
            10,
        )
        self.trajectory_action_client = ActionClient(
            self,
            FollowJointTrajectory,
            "/cia402_joint_trajectory_controller/follow_joint_trajectory",
        )
        self.command_authority_request_pub = self.create_publisher(
            Empty,
            "/command_authority/request",
            10,
        )
        self.command_authority_release_pub = self.create_publisher(
            Empty,
            "/command_authority/release",
            10,
        )

        self.create_subscription(
            Int32MultiArray,
            "/statuswords",
            self.statusword_callback,
            10,
        )
        self.create_subscription(
            Int32MultiArray,
            "/drive_diagnostics",
            self.diagnostics_callback,
            10,
        )
        self.create_subscription(
            String,
            "/command_authority/status",
            self.command_authority_callback,
            10,
        )
        self.create_subscription(
            String,
            "/command_rejected",
            self.command_rejected_callback,
            10,
        )

    def publish_joint_trajectory(self, targets):
        msg = JointTrajectory()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.joint_names = list(AXES)

        point = JointTrajectoryPoint()
        point.positions = [float(value) for value in targets]
        msg.points.append(point)

        self.joint_trajectory_pub.publish(msg)

    def send_follow_joint_trajectory(self, targets, done_callback=None):
        if not self.trajectory_action_client.wait_for_server(timeout_sec=0.1):
            self.action_status_text = "Action server: unavailable"
            self.action_result_text = "Result: no action server"
            self.get_logger().warn("FollowJointTrajectory action server is not available")
            return False

        goal = FollowJointTrajectory.Goal()
        goal.trajectory = JointTrajectory()
        goal.trajectory.header.stamp = self.get_clock().now().to_msg()
        goal.trajectory.joint_names = list(AXES)

        point = JointTrajectoryPoint()
        point.positions = [float(value) for value in targets]
        goal.trajectory.points.append(point)

        self.action_status_text = "Action goal: sending"
        self.action_result_text = "Result: pending"
        future = self.trajectory_action_client.send_goal_async(
            goal,
            feedback_callback=self.follow_joint_feedback_callback,
        )
        future.add_done_callback(
            lambda goal_future: self.follow_joint_goal_response_callback(
                goal_future,
                done_callback,
            )
        )
        return True

    def follow_joint_goal_response_callback(self, future, done_callback):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.current_goal_handle = None
            self.action_status_text = "Action goal: rejected"
            self.action_result_text = "Result: rejected"
            if done_callback is not None:
                done_callback(False)
            return

        self.current_goal_handle = goal_handle
        self.action_status_text = "Action goal: accepted"
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda future_result: self.follow_joint_result_callback(
                future_result,
                done_callback,
            )
        )

    def follow_joint_result_callback(self, future, done_callback):
        response = future.result()
        result = response.result
        self.current_goal_handle = None
        self.action_status_text = f"Action status: {response.status}"
        self.action_result_text = (
            f"Result: code={result.error_code} {result.error_string}"
        )
        if done_callback is not None:
            done_callback(result.error_code == FollowJointTrajectory.Result.SUCCESSFUL)

    def follow_joint_feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        desired = list(feedback.desired.positions)
        actual = list(feedback.actual.positions)
        error = list(feedback.error.positions)
        self.action_feedback_text = (
            f"Feedback desired={desired} actual={actual} error={error}"
        )

    def cancel_follow_joint_trajectory(self):
        if self.current_goal_handle is None:
            self.action_status_text = "Action cancel: no active goal"
            return

        self.action_status_text = "Action cancel: requested"
        cancel_future = self.current_goal_handle.cancel_goal_async()
        cancel_future.add_done_callback(self.cancel_follow_joint_callback)

    def cancel_follow_joint_callback(self, future):
        response = future.result()
        self.action_status_text = (
            f"Action cancel: {len(response.goals_canceling)} goal(s)"
        )

    def follow_joint_action_ready(self):
        try:
            return self.trajectory_action_client.server_is_ready()
        except Exception:
            return False

    def request_command_authority(self):
        self.command_authority_request_pub.publish(Empty())
        self.command_authority_text = "Authority request sent to ROS Bridge"

    def release_command_authority(self):
        self.command_authority_release_pub.publish(Empty())
        self.command_authority_text = "Authority release sent to ROS Bridge"

    def target_position_callback(self, msg):
        if len(msg.data) >= len(AXES):
            self.target_positions = [
                float(msg.data[index])
                for index in range(len(AXES))
            ]

    def actual_position_callback(self, msg):
        if len(msg.data) >= len(AXES):
            self.actual_positions = [
                float(msg.data[index])
                for index in range(len(AXES))
            ]

    def actual_velocity_callback(self, msg):
        if len(msg.data) >= len(AXES):
            self.actual_velocities = [
                float(msg.data[index])
                for index in range(len(AXES))
            ]

    def statusword_callback(self, msg):
        if len(msg.data) >= len(AXES):
            self.statuswords = [
                int(msg.data[index])
                for index in range(len(AXES))
            ]

    def diagnostics_callback(self, msg):
        expected_values = len(AXES) * 3
        if len(msg.data) < expected_values:
            return

        self.error_codes = [
            int(msg.data[index * 3])
            for index in range(len(AXES))
        ]
        self.error_registers = [
            int(msg.data[index * 3 + 1])
            for index in range(len(AXES))
        ]

    def motion_limit_callback(self, msg):
        expected_values = len(AXES) * 4

        if len(msg.data) < expected_values:
            return

        self.motion_limits = [
            [
                float(msg.data[index * 4]),
                float(msg.data[index * 4 + 1]),
                float(msg.data[index * 4 + 2]),
                float(msg.data[index * 4 + 3]),
            ]
            for index in range(len(AXES))
        ]

    def command_authority_callback(self, msg):
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            self.command_authority_text = msg.data
            return

        if payload.get("owned_by_this_client", False):
            self.command_authority_text = "Authority: ROS Bridge owns Axis Server"
        elif payload.get("available", False):
            self.command_authority_text = "Authority: available"
        elif payload.get("owner", None) is not None:
            self.command_authority_text = f"Authority: client {payload['owner']}"
        elif "message" in payload:
            self.command_authority_text = payload["message"]
        else:
            self.command_authority_text = "Authority: unknown"

    def command_rejected_callback(self, msg):
        try:
            payload = json.loads(msg.data)
            text = payload.get("message", msg.data)
        except json.JSONDecodeError:
            text = msg.data
        self.get_logger().warn(text)


class AxisControlPanelGui:
    def __init__(self, node):
        self.node = node
        self.root = tk.Tk()
        self.root.title("ROS Control Panel")
        self.root.geometry(f"1240x{760 + len(AXES) * 70}")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.command_position_vars = []
        self.target_vars = []
        self.actual_position_vars = []
        self.actual_velocity_vars = []
        self.statusword_vars = []
        self.error_code_vars = []
        self.error_register_vars = []
        self.repeat_point_count_var = tk.StringVar(value="2")
        self.repeat_point_vars = []
        self.repeat_period_var = tk.StringVar(value="2.0")
        self.repeat_points_frame = None
        self.limit_vars = []
        self.command_authority_var = tk.StringVar(value="Authority: unknown")
        self.command_transport_var = tk.StringVar(value="Action Controller")
        self.action_status_var = tk.StringVar(value="Action server: unknown")
        self.action_result_var = tk.StringVar(value="Result: none")
        self.action_feedback_var = tk.StringVar(value="Feedback: none")
        self.position_trace = None
        self.velocity_trace = None
        self.repeat_enabled = False
        self.repeat_points = None
        self.repeat_period = 2.0
        self.repeat_index = 0
        self.repeat_target = None
        self.repeat_wait_until = 0.0

        self._build_ui()
        self.root.after(GUI_PERIOD_MS, self.update_gui)

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        config_label = ttk.Label(
            frame,
            text=f"ROS Control Panel | Joints: {', '.join(AXES)}",
            anchor="w",
        )
        config_label.grid(
            row=0,
            column=0,
            columnspan=6,
            padx=5,
            pady=(0, 10),
            sticky="ew",
        )
        ttk.Button(
            frame,
            text="Request Bridge Authority",
            command=self.request_command_authority,
        ).grid(row=0, column=6, padx=5, pady=(0, 10), sticky="ew")
        ttk.Button(
            frame,
            text="Release Bridge Authority",
            command=self.release_command_authority,
        ).grid(row=0, column=7, padx=5, pady=(0, 10), sticky="ew")
        ttk.Label(
            frame,
            textvariable=self.command_authority_var,
            anchor="w",
        ).grid(row=0, column=8, columnspan=4, padx=5, pady=(0, 10), sticky="ew")

        notebook = ttk.Notebook(frame)
        notebook.grid(row=1, column=0, columnspan=12, sticky="nsew")

        command_tab = ttk.Frame(notebook, padding=8)
        limits_tab = ttk.Frame(notebook, padding=8)
        notebook.add(command_tab, text="Command")
        notebook.add(limits_tab, text="Limits")

        self._build_command_tab(command_tab)
        self._build_limits_tab(limits_tab)

    def _build_command_tab(self, frame):
        transport_frame = ttk.Frame(frame)
        transport_frame.grid(
            row=0,
            column=0,
            columnspan=8,
            padx=5,
            pady=(0, 8),
            sticky="ew",
        )
        ttk.Label(transport_frame, text="Command Mode").grid(
            row=0,
            column=0,
            padx=5,
            pady=5,
        )
        ttk.Radiobutton(
            transport_frame,
            text="Action Controller",
            variable=self.command_transport_var,
            value="Action Controller",
        ).grid(row=0, column=1, padx=5, pady=5)
        ttk.Radiobutton(
            transport_frame,
            text="Topic Debug",
            variable=self.command_transport_var,
            value="Topic Debug",
        ).grid(row=0, column=2, padx=5, pady=5)
        ttk.Button(
            transport_frame,
            text="Cancel Goal",
            command=self.cancel_command,
        ).grid(row=0, column=3, padx=5, pady=5)
        ttk.Label(
            transport_frame,
            textvariable=self.action_status_var,
            anchor="w",
        ).grid(row=0, column=4, padx=5, pady=5, sticky="ew")
        ttk.Label(
            transport_frame,
            textvariable=self.action_result_var,
            anchor="w",
        ).grid(row=1, column=1, columnspan=3, padx=5, pady=2, sticky="ew")
        ttk.Label(
            transport_frame,
            textvariable=self.action_feedback_var,
            anchor="w",
        ).grid(row=1, column=4, columnspan=4, padx=5, pady=2, sticky="ew")
        transport_frame.columnconfigure(4, weight=1)

        headers = [
            "Joint",
            "Command Position",
            "Target Position",
            "Actual Position",
            "Actual Velocity",
            "Statusword",
            "Error",
            "Err Reg",
        ]

        for column, header in enumerate(headers):
            label = ttk.Label(frame, text=header, anchor="center")
            label.grid(row=1, column=column, padx=5, pady=5, sticky="ew")
            frame.columnconfigure(column, weight=1)

        for row, axis_name in enumerate(AXES, start=2):
            ttk.Label(frame, text=axis_name, anchor="center").grid(
                row=row,
                column=0,
                padx=5,
                pady=5,
                sticky="ew",
            )

            command_position_var = tk.StringVar(value="0.0")
            command_position_entry = ttk.Entry(
                frame,
                textvariable=command_position_var,
                justify="right",
            )
            command_position_entry.grid(
                row=row,
                column=1,
                padx=5,
                pady=5,
                sticky="ew",
            )

            target_var = tk.StringVar(value="0.0")
            ttk.Label(
                frame,
                textvariable=target_var,
                anchor="e",
            ).grid(
                row=row,
                column=2,
                padx=5,
                pady=5,
                sticky="ew",
            )

            actual_position_var = tk.StringVar(value="0.0")
            actual_velocity_var = tk.StringVar(value="0.0")

            ttk.Label(
                frame,
                textvariable=actual_position_var,
                anchor="e",
            ).grid(row=row, column=3, padx=5, pady=5, sticky="ew")

            ttk.Label(
                frame,
                textvariable=actual_velocity_var,
                anchor="e",
            ).grid(row=row, column=4, padx=5, pady=5, sticky="ew")

            statusword_var = tk.StringVar(value="0x0000")
            ttk.Label(
                frame,
                textvariable=statusword_var,
                anchor="e",
            ).grid(row=row, column=5, padx=5, pady=5, sticky="ew")

            error_code_var = tk.StringVar(value="0x0000")
            ttk.Label(
                frame,
                textvariable=error_code_var,
                anchor="e",
            ).grid(row=row, column=6, padx=5, pady=5, sticky="ew")

            error_register_var = tk.StringVar(value="0x00")
            ttk.Label(
                frame,
                textvariable=error_register_var,
                anchor="e",
            ).grid(row=row, column=7, padx=5, pady=5, sticky="ew")

            self.command_position_vars.append(command_position_var)
            self.target_vars.append(target_var)
            self.actual_position_vars.append(actual_position_var)
            self.actual_velocity_vars.append(actual_velocity_var)
            self.statusword_vars.append(statusword_var)
            self.error_code_vars.append(error_code_var)
            self.error_register_vars.append(error_register_var)

        button_frame = ttk.Frame(frame)
        button_frame.grid(
            row=len(AXES) + 2,
            column=0,
            columnspan=len(headers),
            padx=5,
            pady=(14, 5),
            sticky="e",
        )

        ttk.Button(
            button_frame,
            text="Send Command",
            command=self.send_command,
        ).grid(row=0, column=0, padx=5)

        repeat_frame = ttk.LabelFrame(frame, text="Repeat Motion")
        repeat_frame.grid(
            row=len(AXES) + 3,
            column=0,
            columnspan=len(headers),
            padx=5,
            pady=(12, 5),
            sticky="ew",
        )

        ttk.Label(repeat_frame, text="Point Count").grid(
            row=0,
            column=0,
            padx=5,
            pady=5,
        )
        ttk.Spinbox(
            repeat_frame,
            from_=2,
            to=8,
            textvariable=self.repeat_point_count_var,
            width=6,
            justify="right",
        ).grid(
            row=0,
            column=1,
            padx=5,
            pady=5,
        )
        ttk.Button(
            repeat_frame,
            text="Apply Points",
            command=self.apply_repeat_point_count,
        ).grid(
            row=0,
            column=2,
            padx=5,
            pady=5,
        )
        ttk.Label(repeat_frame, text="Period (s)").grid(
            row=0,
            column=3,
            padx=5,
            pady=5,
        )
        ttk.Entry(
            repeat_frame,
            textvariable=self.repeat_period_var,
            justify="right",
            width=10,
        ).grid(row=0, column=4, padx=5, pady=5)
        ttk.Button(
            repeat_frame,
            text="Start Repeat",
            command=self.start_repeat,
        ).grid(row=0, column=5, padx=5, pady=5)
        ttk.Button(
            repeat_frame,
            text="Stop Repeat",
            command=self.stop_repeat,
        ).grid(row=0, column=6, padx=5, pady=5)

        self.repeat_points_frame = ttk.Frame(repeat_frame)
        self.repeat_points_frame.grid(
            row=1,
            column=0,
            columnspan=7,
            padx=5,
            pady=(6, 5),
            sticky="ew",
        )
        self.build_repeat_point_entries(2)

        traces_frame = ttk.Frame(frame)
        traces_frame.grid(
            row=len(AXES) + 4,
            column=0,
            columnspan=len(headers),
            padx=5,
            pady=(12, 5),
            sticky="nsew",
        )
        frame.rowconfigure(len(AXES) + 4, weight=1)
        self.position_trace = TraceCanvas(traces_frame, AXES, "Actual Position")
        self.velocity_trace = TraceCanvas(traces_frame, AXES, "Actual Velocity", 3)

    def _build_limits_tab(self, frame):
        headers = ["Joint", "Max Velocity", "Accel", "Decel", "Kp"]
        ttk.Label(
            frame,
            text="Read-only feedback from Axis Server. Configure limits in Axis Panel.",
            anchor="w",
        ).grid(
            row=0,
            column=0,
            columnspan=len(headers),
            padx=5,
            pady=(0, 8),
            sticky="ew",
        )

        for column, header in enumerate(headers):
            label = ttk.Label(frame, text=header, anchor="center")
            label.grid(row=1, column=column, padx=5, pady=5, sticky="ew")
            frame.columnconfigure(column, weight=1)

        for row, axis_name in enumerate(AXES, start=2):
            ttk.Label(frame, text=axis_name, anchor="center").grid(
                row=row,
                column=0,
                padx=5,
                pady=5,
                sticky="ew",
            )

            axis_limit_vars = []
            for column in range(1, 5):
                var = tk.StringVar(value="0.0")
                ttk.Label(
                    frame,
                    textvariable=var,
                    anchor="e",
                ).grid(
                    row=row,
                    column=column,
                    padx=5,
                    pady=5,
                    sticky="ew",
                )
                axis_limit_vars.append(var)

            self.limit_vars.append(axis_limit_vars)

    def build_repeat_point_entries(self, point_count):
        existing_values = [
            [
                var.get()
                for var in point_vars
            ]
            for point_vars in self.repeat_point_vars
        ]

        for child in self.repeat_points_frame.winfo_children():
            child.destroy()

        self.repeat_point_vars = []

        ttk.Label(self.repeat_points_frame, text="Joint").grid(
            row=0,
            column=0,
            padx=5,
            pady=5,
        )
        for point_index in range(point_count):
            ttk.Label(
                self.repeat_points_frame,
                text=f"Point {self.repeat_point_name(point_index)}",
            ).grid(row=0, column=point_index + 1, padx=5, pady=5)

        for axis_index, axis_name in enumerate(AXES):
            ttk.Label(self.repeat_points_frame, text=axis_name).grid(
                row=axis_index + 1,
                column=0,
                padx=5,
                pady=5,
            )

        for point_index in range(point_count):
            point_vars = []
            for axis_index in range(len(AXES)):
                value = "0.0"
                if (
                    point_index < len(existing_values)
                    and axis_index < len(existing_values[point_index])
                ):
                    value = existing_values[point_index][axis_index]
                var = tk.StringVar(value=value)
                ttk.Entry(
                    self.repeat_points_frame,
                    textvariable=var,
                    justify="right",
                    width=14,
                ).grid(
                    row=axis_index + 1,
                    column=point_index + 1,
                    padx=5,
                    pady=5,
                )
                point_vars.append(var)
            self.repeat_point_vars.append(point_vars)

    @staticmethod
    def repeat_point_name(index):
        if 0 <= index < 26:
            return chr(ord("A") + index)
        return str(index + 1)

    def apply_repeat_point_count(self):
        try:
            point_count = int(self.repeat_point_count_var.get())
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Point Count must be an integer value.",
            )
            return

        point_count = max(2, min(8, point_count))
        self.repeat_point_count_var.set(str(point_count))
        self.stop_repeat()
        self.build_repeat_point_entries(point_count)

    def send_command(self):
        targets = self.read_command_position_values()
        if targets is None:
            return

        self.send_targets(targets)

    def send_targets(self, targets, done_callback=None):
        if self.command_transport_var.get() == "Action Controller":
            self.node.send_follow_joint_trajectory(targets, done_callback)
        else:
            self.node.publish_joint_trajectory(targets)
            if done_callback is not None:
                done_callback(True)

    def cancel_command(self):
        if self.command_transport_var.get() == "Action Controller":
            self.node.cancel_follow_joint_trajectory()

    def request_command_authority(self):
        self.node.request_command_authority()

    def release_command_authority(self):
        self.node.release_command_authority()

    def start_repeat(self):
        repeat_config = self.read_repeat_values()
        if repeat_config is None:
            return

        points, period = repeat_config
        self.repeat_enabled = True
        self.repeat_points = points
        self.repeat_period = period
        self.repeat_index = 0
        self.repeat_wait_until = 0.0
        self.send_repeat_target()

    def stop_repeat(self):
        self.repeat_enabled = False
        self.repeat_points = None
        self.repeat_target = None
        self.repeat_wait_until = 0.0

    def send_repeat_target(self):
        if not self.repeat_enabled or self.repeat_points is None:
            return

        self.repeat_target = list(self.repeat_points[self.repeat_index])
        self.send_targets(self.repeat_target)
        self.repeat_wait_until = 0.0

    def update_repeat_motion(self):
        if not self.repeat_enabled or self.repeat_target is None:
            return

        now = self.node.get_clock().now().nanoseconds / 1_000_000_000.0
        if self.repeat_wait_until > 0.0:
            if now >= self.repeat_wait_until:
                self.repeat_index = (self.repeat_index + 1) % len(self.repeat_points)
                self.send_repeat_target()
            return

        reached = all(
            abs(actual - target) <= REPEAT_TOLERANCE
            for actual, target in zip(self.node.actual_positions, self.repeat_target)
        )
        if reached:
            self.repeat_wait_until = now + self.repeat_period

    def read_repeat_values(self):
        try:
            points = [
                [
                    float(var.get())
                    for var in point_vars
                ]
                for point_vars in self.repeat_point_vars
            ]
            period = float(self.repeat_period_var.get())
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Repeat point values and period must be numeric values.",
            )
            return None

        if len(points) < 2:
            messagebox.showerror(
                "Invalid Input",
                "Repeat motion needs at least 2 points.",
            )
            return None

        if any(len(point) != len(AXES) for point in points):
            messagebox.showerror(
                "Invalid Input",
                "Each repeat point must define all joint positions.",
            )
            return None

        if period <= 0:
            messagebox.showerror(
                "Invalid Input",
                "Repeat period must be greater than 0.",
            )
            return None

        return points, period

    def read_command_position_values(self):
        try:
            return [
                float(var.get())
                for var in self.command_position_vars
            ]
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Command Position must be numeric values.",
            )
            return None

    def update_gui(self):
        rclpy.spin_once(self.node, timeout_sec=0.0)
        self.command_authority_var.set(self.node.command_authority_text)
        action_ready = self.node.follow_joint_action_ready()
        if self.command_transport_var.get() == "Action Controller":
            server_text = "Action server: ready" if action_ready else "Action server: unavailable"
            if self.node.action_status_text.startswith("Action server:"):
                self.action_status_var.set(server_text)
            else:
                self.action_status_var.set(f"{server_text} | {self.node.action_status_text}")
        else:
            self.action_status_var.set("Topic Debug mode")
        self.action_result_var.set(self.node.action_result_text)
        self.action_feedback_var.set(self.node.action_feedback_text)

        for index in range(len(AXES)):
            self.target_vars[index].set(
                f"{self.node.target_positions[index]:.3f}"
            )

            for limit_index in range(4):
                var = self.limit_vars[index][limit_index]
                var.set(f"{self.node.motion_limits[index][limit_index]:.3f}")

            self.actual_position_vars[index].set(
                f"{self.node.actual_positions[index]:.3f}"
            )
            self.actual_velocity_vars[index].set(
                f"{self.node.actual_velocities[index]:.3f}"
            )
            self.statusword_vars[index].set(
                f"0x{self.node.statuswords[index]:04X}"
            )
            self.error_code_vars[index].set(
                f"0x{self.node.error_codes[index]:04X}"
                if self.node.error_codes[index] >= 0
                else "read fail"
            )
            self.error_register_vars[index].set(
                f"0x{self.node.error_registers[index]:02X}"
                if self.node.error_registers[index] >= 0
                else "read fail"
            )

        self.position_trace.add_sample(self.node.actual_positions)
        self.velocity_trace.add_sample(self.node.actual_velocities)
        self.position_trace.draw()
        self.velocity_trace.draw()
        self.update_repeat_motion()

        self.root.after(GUI_PERIOD_MS, self.update_gui)

    def close(self):
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main(args=None):
    rclpy.init(args=args)
    node = AxisControlPanelNode()
    gui = AxisControlPanelGui(node)

    try:
        gui.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
