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
from rclpy.node import Node
from std_msgs.msg import Empty
from std_msgs.msg import Float64MultiArray
from std_msgs.msg import Int32MultiArray
from std_msgs.msg import String

from ros.axis_runtime_config import get_axis_names
from ros.axis_runtime_config import get_master_backend

AXES = get_axis_names()
GUI_PERIOD_MS = 50
HISTORY_SIZE = 500


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
        self.motion_limits = [
            [0.0, 0.0, 0.0, 0.0]
            for _ in AXES
        ]

        self.motion_limit_pub = self.create_publisher(
            Float64MultiArray,
            "/motion_limits",
            10,
        )

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

        self.command_position_pub = self.create_publisher(
            Float64MultiArray,
            "/command_target_positions",
            10,
        )
        self.alarm_ack_pub = self.create_publisher(
            Empty,
            "/alarm_ack",
            10,
        )
        self.repeat_motion_pub = self.create_publisher(
            String,
            "/repeat_motion_command",
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

    def publish_command_positions(self, targets):
        msg = Float64MultiArray()
        msg.data = [float(value) for value in targets]
        self.command_position_pub.publish(msg)

    def publish_motion_limits(self, limits):
        msg = Float64MultiArray()
        msg.data = [
            float(value)
            for axis_limits in limits
            for value in axis_limits
        ]
        self.motion_limit_pub.publish(msg)

    def publish_alarm_ack(self):
        self.alarm_ack_pub.publish(Empty())

    def publish_repeat_motion(self, action, points=None, period=2.0):
        msg = String()
        payload = {
            "action": action,
        }

        if points is not None:
            payload["points"] = points
            payload["period"] = float(period)

        msg.data = json.dumps(payload)
        self.repeat_motion_pub.publish(msg)

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


class AxisControlPanelGui:
    def __init__(self, node):
        self.node = node
        self.root = tk.Tk()
        self.root.title("Axis Control Panel")
        self.root.geometry(f"1240x{760 + len(AXES) * 70}")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.command_position_vars = []
        self.target_vars = []
        self.actual_position_vars = []
        self.actual_velocity_vars = []
        self.statusword_vars = []
        self.error_code_vars = []
        self.error_register_vars = []
        self.repeat_point_a_vars = []
        self.repeat_point_b_vars = []
        self.repeat_period_var = tk.StringVar(value="2.0")
        self.limit_vars = []
        self.dirty_vars = set()
        self.position_trace = None
        self.velocity_trace = None

        self._build_ui()
        self.root.after(GUI_PERIOD_MS, self.update_gui)

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        config_label = ttk.Label(
            frame,
            text=f"Backend: {get_master_backend()} | Axes: {', '.join(AXES)}",
            anchor="w",
        )
        config_label.grid(
            row=0,
            column=0,
            columnspan=9,
            padx=5,
            pady=(0, 10),
            sticky="ew",
        )

        headers = [
            "Axis",
            "Max Velocity",
            "Accel",
            "Decel",
            "Kp",
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

            axis_limit_vars = []
            for column in range(1, 5):
                var = tk.StringVar(value="0.0")
                entry = ttk.Entry(frame, textvariable=var, justify="right")
                entry.grid(
                    row=row,
                    column=column,
                    padx=5,
                    pady=5,
                    sticky="ew",
                )
                entry.bind(
                    "<KeyRelease>",
                    lambda _event, watched_var=var: self.mark_dirty(watched_var),
                )
                axis_limit_vars.append(var)

            command_position_var = tk.StringVar(value="0.0")
            command_position_entry = ttk.Entry(
                frame,
                textvariable=command_position_var,
                justify="right",
            )
            command_position_entry.grid(
                row=row,
                column=5,
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
                column=6,
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
            ).grid(row=row, column=7, padx=5, pady=5, sticky="ew")

            ttk.Label(
                frame,
                textvariable=actual_velocity_var,
                anchor="e",
            ).grid(row=row, column=8, padx=5, pady=5, sticky="ew")

            statusword_var = tk.StringVar(value="0x0000")
            ttk.Label(
                frame,
                textvariable=statusword_var,
                anchor="e",
            ).grid(row=row, column=9, padx=5, pady=5, sticky="ew")

            error_code_var = tk.StringVar(value="0x0000")
            ttk.Label(
                frame,
                textvariable=error_code_var,
                anchor="e",
            ).grid(row=row, column=10, padx=5, pady=5, sticky="ew")

            error_register_var = tk.StringVar(value="0x00")
            ttk.Label(
                frame,
                textvariable=error_register_var,
                anchor="e",
            ).grid(row=row, column=11, padx=5, pady=5, sticky="ew")

            self.limit_vars.append(axis_limit_vars)
            self.command_position_vars.append(command_position_var)
            self.target_vars.append(target_var)
            self.actual_position_vars.append(actual_position_var)
            self.actual_velocity_vars.append(actual_velocity_var)
            self.statusword_vars.append(statusword_var)
            self.error_code_vars.append(error_code_var)
            self.error_register_vars.append(error_register_var)

            point_a_var = tk.StringVar(value="0.0")
            point_b_var = tk.StringVar(value="0.0")
            self.repeat_point_a_vars.append(point_a_var)
            self.repeat_point_b_vars.append(point_b_var)

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
            text="Apply Limits",
            command=self.apply_limits,
        ).grid(row=0, column=0, padx=5)

        ttk.Button(
            button_frame,
            text="Send Command",
            command=self.send_command,
        ).grid(row=0, column=1, padx=5)

        ttk.Button(
            button_frame,
            text="Apply Limits + Send",
            command=self.apply_limits_and_send,
        ).grid(row=0, column=2, padx=5)

        ttk.Button(
            button_frame,
            text="Alarm Ack",
            command=self.alarm_ack,
        ).grid(row=0, column=3, padx=5)

        repeat_frame = ttk.LabelFrame(frame, text="Repeat Motion")
        repeat_frame.grid(
            row=len(AXES) + 3,
            column=0,
            columnspan=len(headers),
            padx=5,
            pady=(12, 5),
            sticky="ew",
        )

        ttk.Label(repeat_frame, text="Axis").grid(
            row=0,
            column=0,
            padx=5,
            pady=5,
        )
        ttk.Label(repeat_frame, text="Point A").grid(
            row=0,
            column=1,
            padx=5,
            pady=5,
        )
        ttk.Label(repeat_frame, text="Point B").grid(
            row=0,
            column=2,
            padx=5,
            pady=5,
        )

        for row, axis_name in enumerate(AXES, start=1):
            ttk.Label(repeat_frame, text=axis_name).grid(
                row=row,
                column=0,
                padx=5,
                pady=5,
            )
            ttk.Entry(
                repeat_frame,
                textvariable=self.repeat_point_a_vars[row - 1],
                justify="right",
                width=14,
            ).grid(row=row, column=1, padx=5, pady=5)
            ttk.Entry(
                repeat_frame,
                textvariable=self.repeat_point_b_vars[row - 1],
                justify="right",
                width=14,
            ).grid(row=row, column=2, padx=5, pady=5)

        ttk.Label(repeat_frame, text="Period (s)").grid(
            row=1,
            column=3,
            padx=5,
            pady=5,
        )
        ttk.Entry(
            repeat_frame,
            textvariable=self.repeat_period_var,
            justify="right",
            width=10,
        ).grid(row=1, column=4, padx=5, pady=5)
        ttk.Button(
            repeat_frame,
            text="Start Repeat",
            command=self.start_repeat,
        ).grid(row=1, column=5, padx=5, pady=5)
        ttk.Button(
            repeat_frame,
            text="Stop Repeat",
            command=self.stop_repeat,
        ).grid(row=1, column=6, padx=5, pady=5)

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

    def mark_dirty(self, var):
        self.dirty_vars.add(id(var))

    def apply_limits(self):
        limits = self.read_limit_values()
        if limits is None:
            return

        self.node.publish_motion_limits(limits)

        for axis_limit_vars in self.limit_vars:
            for var in axis_limit_vars:
                self.dirty_vars.discard(id(var))

    def send_command(self):
        targets = self.read_command_position_values()
        if targets is None:
            return

        self.node.publish_command_positions(targets)

    def apply_limits_and_send(self):
        limits = self.read_limit_values()
        targets = self.read_command_position_values()

        if limits is None or targets is None:
            return

        self.node.publish_motion_limits(limits)
        self.node.publish_command_positions(targets)

        for axis_limit_vars in self.limit_vars:
            for var in axis_limit_vars:
                self.dirty_vars.discard(id(var))

    def alarm_ack(self):
        self.node.publish_alarm_ack()

    def start_repeat(self):
        repeat_config = self.read_repeat_values()
        if repeat_config is None:
            return

        point_a, point_b, period = repeat_config
        self.node.publish_repeat_motion(
            "start",
            points=[point_a, point_b],
            period=period,
        )

    def stop_repeat(self):
        self.node.publish_repeat_motion("stop")

    def read_repeat_values(self):
        try:
            point_a = [
                float(var.get())
                for var in self.repeat_point_a_vars
            ]
            point_b = [
                float(var.get())
                for var in self.repeat_point_b_vars
            ]
            period = float(self.repeat_period_var.get())
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Repeat points and period must be numeric values.",
            )
            return None

        if period <= 0:
            messagebox.showerror(
                "Invalid Input",
                "Repeat period must be greater than 0.",
            )
            return None

        return point_a, point_b, period

    def read_limit_values(self):
        try:
            return [
                [float(var.get()) for var in axis_limit_vars]
                for axis_limit_vars in self.limit_vars
            ]
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Max Velocity, Accel, Decel, Kp must be numeric values.",
            )
            return None

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

        for index in range(len(AXES)):
            self.target_vars[index].set(
                f"{self.node.target_positions[index]:.3f}"
            )

            for limit_index in range(4):
                var = self.limit_vars[index][limit_index]
                if id(var) not in self.dirty_vars:
                    var.set(
                        f"{self.node.motion_limits[index][limit_index]:.3f}"
                    )

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
