import json
import os
from pathlib import Path
import json
import socket
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GUI_PERIOD_MS = 50
RECONNECT_PERIOD = 1.0
HISTORY_SIZE = 500
REPEAT_TOLERANCE = 10.0
STATUSWORD_BITS = [
    (0, "Ready"),
    (1, "Switched"),
    (2, "Op En"),
    (3, "Fault"),
    (4, "Volt En"),
    (5, "Quick Stop"),
    (6, "SOD"),
    (7, "Warning"),
    (8, "Moving"),
    (9, "Remote"),
    (10, "Reached"),
    (11, "Limit"),
    (12, "OMS 12"),
    (13, "OMS 13"),
    (14, "Manuf 14"),
    (15, "Refered"),
]


def load_env_file(path):
    values = {}
    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def default_axis_names(axis_count):
    base_names = ["X", "Y", "Z", "U", "V", "W"]
    return [
        base_names[index] if index < len(base_names) else f"A{index + 1}"
        for index in range(axis_count)
    ]


def read_runtime_config():
    env_file = load_env_file(PROJECT_ROOT / ".env")
    host = os.environ.get("PYSOEM_SERVER_HOST", "127.0.0.1")
    port = int(
        os.environ.get(
            "PYSOEM_AXIS_SERVER_PORT",
            env_file.get("PYSOEM_AXIS_SERVER_PORT", "15000"),
        )
    )
    axis_count = int(
        os.environ.get(
            "PYSOEM_AXIS_COUNT",
            env_file.get("PYSOEM_AXIS_COUNT", "1"),
        )
    )
    axis_names_text = os.environ.get("PYSOEM_AXIS_NAMES", "")
    if axis_names_text:
        axis_names = [
            name.strip()
            for name in axis_names_text.split(",")
            if name.strip()
        ]
    else:
        axis_names = default_axis_names(axis_count)

    if len(axis_names) < axis_count:
        axis_names.extend(default_axis_names(axis_count)[len(axis_names):])

    return host, port, axis_names[:axis_count]


class AxisServerClient:
    def __init__(self, host, port, axis_count):
        self.host = host
        self.port = port
        self.axis_count = axis_count
        self.sock = None
        self.sock_file = None
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.connected = False
        self.last_error = ""
        self.feedback = {
            "target_positions": [0.0 for _ in range(axis_count)],
            "actual_positions": [0.0 for _ in range(axis_count)],
            "actual_velocities": [0.0 for _ in range(axis_count)],
            "statuswords": [0 for _ in range(axis_count)],
            "motion_limits": [0.0 for _ in range(axis_count * 4)],
            "motion_mode": "pp",
            "diagnostics": [],
        }
        self.thread = threading.Thread(target=self._connection_loop, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.close()

    def close(self):
        with self.lock:
            if self.sock_file is not None:
                self.sock_file.close()
                self.sock_file = None
            if self.sock is not None:
                self.sock.close()
                self.sock = None
            self.connected = False

    def _connection_loop(self):
        while not self.stop_event.is_set():
            try:
                self._connect()
                self._read_loop()
            except OSError as exc:
                self.last_error = str(exc)
            except Exception as exc:
                self.last_error = str(exc)
            finally:
                self.close()

            time.sleep(RECONNECT_PERIOD)

    def _connect(self):
        sock = socket.create_connection((self.host, self.port), timeout=5.0)
        sock.settimeout(None)
        sock_file = sock.makefile("r", encoding="utf-8", newline="\n")
        with self.lock:
            self.sock = sock
            self.sock_file = sock_file
            self.connected = True
            self.last_error = ""

    def _read_loop(self):
        while not self.stop_event.is_set():
            line = self.sock_file.readline()
            if not line:
                raise OSError("server closed connection")

            message = json.loads(line)
            if message.get("type") == "feedback":
                self._store_feedback(message)

    def _store_feedback(self, message):
        with self.lock:
            self.feedback = message

    def get_snapshot(self):
        with self.lock:
            return self.connected, self.last_error, dict(self.feedback)

    def send_json(self, message):
        payload = (json.dumps(message) + "\n").encode("utf-8")
        with self.lock:
            if self.sock is None:
                raise ConnectionError("Axis server is not connected")
            self.sock.sendall(payload)

    def send_target_positions(self, positions):
        self.send_json(
            {
                "type": "target_positions",
                "positions": [float(value) for value in positions],
            }
        )

    def send_motion_limits(self, limits):
        self.send_json(
            {
                "type": "motion_limits",
                "limits": [
                    [float(value) for value in axis_limits]
                    for axis_limits in limits
                ],
            }
        )

    def send_motion_mode(self, mode):
        self.send_json(
            {
                "type": "motion_mode",
                "mode": str(mode).lower(),
            }
        )

    def send_controlword(self, controlword, axis_index=None):
        message = {
            "type": "controlword",
            "controlword": int(controlword),
        }
        if axis_index is not None:
            message["axis"] = int(axis_index)

        self.send_json(message)

    def send_jog_position(self, axis_index, distance):
        self.send_json(
            {
                "type": "jog_position",
                "axis": int(axis_index),
                "distance": float(distance),
            }
        )

    def send_alarm_ack(self):
        self.send_json({"type": "alarm_ack"})


class TraceCanvas:
    def __init__(self, parent, axis_names, title, color_offset=0):
        self.axis_names = axis_names
        self.title = title
        self.history = [
            []
            for _ in axis_names
        ]
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
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 50)
        height = max(self.canvas.winfo_height(), 50)
        margin = 28

        all_values = [
            value
            for series in self.history
            for value in series
        ]
        if not all_values:
            self._draw_empty(width, height)
            return

        min_value = min(all_values)
        max_value = max(all_values)
        if abs(max_value - min_value) < 1e-9:
            min_value -= 1.0
            max_value += 1.0

        self.canvas.create_text(
            8,
            8,
            text=self.title,
            fill="#f0f0f0",
            anchor="nw",
            font=("TkDefaultFont", 10, "bold"),
        )
        self.canvas.create_text(
            width - 8,
            8,
            text=f"{min_value:.1f} .. {max_value:.1f}",
            fill="#cfcfcf",
            anchor="ne",
        )

        for step in range(5):
            y = margin + step * (height - margin * 2) / 4
            self.canvas.create_line(
                margin,
                y,
                width - margin,
                y,
                fill="#343434",
            )

        for index, series in enumerate(self.history):
            if len(series) < 2:
                continue

            color = self.colors[(index + self.color_offset) % len(self.colors)]
            points = []
            for sample_index, value in enumerate(series):
                x = margin + sample_index * (width - margin * 2) / (HISTORY_SIZE - 1)
                normalized = (value - min_value) / (max_value - min_value)
                y = height - margin - normalized * (height - margin * 2)
                points.extend([x, y])

            self.canvas.create_line(*points, fill=color, width=2)
            self.canvas.create_text(
                margin + 8 + index * 90,
                height - 14,
                text=self.axis_names[index],
                fill=color,
                anchor="w",
            )

    def _draw_empty(self, width, height):
        self.canvas.create_text(
            width / 2,
            height / 2,
            text="Waiting for feedback",
            fill="#bdbdbd",
        )


class AxisServerControlPanel:
    def __init__(self, client, axis_names):
        self.client = client
        self.axis_names = axis_names
        self.axis_count = len(axis_names)
        self.root = tk.Tk()
        self.root.title("Axis Server Control Panel")
        self.root.geometry(f"1280x{620 + self.axis_count * 62}")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.limit_vars = []
        self.command_vars = []
        self.target_vars = []
        self.actual_position_vars = []
        self.actual_velocity_vars = []
        self.command_velocity_vars = []
        self.statusword_vars = []
        self.error_code_vars = []
        self.error_register_vars = []
        self.kp_entries = []
        self.repeat_point_a_vars = []
        self.repeat_point_b_vars = []
        self.repeat_period_var = tk.StringVar(value="2.0")
        self.selected_axis_var = tk.StringVar(value="0")
        self.selected_axis_label_var = tk.StringVar(value=self.axis_names[0])
        self.jog_step_var = tk.StringVar(value="100.0")
        self.connection_var = tk.StringVar(value="Disconnected")
        self.scale_var = tk.StringVar(value="CSP scale: 1.0 count/unit")
        self.motion_mode_var = tk.StringVar(value="pp")
        self.server_motion_mode = "pp"
        self.dirty_vars = set()
        self.statusword_lamps = []

        self.repeat_enabled = False
        self.repeat_points = None
        self.repeat_index = 0
        self.repeat_wait_until = 0.0
        self.last_sent_repeat_target = None
        self.repeat_waiting_to_send = False

        self._build_ui()
        self.update_mode_dependent_controls()
        self.update_selected_axis_label()
        self.selected_axis_var.trace_add(
            "write",
            lambda *_args: self.update_selected_axis_label(),
        )
        self.root.after(GUI_PERIOD_MS, self.update_gui)

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="Axis").pack(side="left", padx=(0, 4))
        for index, axis_name in enumerate(self.axis_names):
            ttk.Radiobutton(
                header,
                text=axis_name,
                value=str(index),
                variable=self.selected_axis_var,
            ).pack(side="left", padx=2)
        ttk.Label(
            header,
            text="Axis Server Control Panel",
            font=("TkDefaultFont", 12, "bold"),
        ).pack(side="left", padx=(14, 0))
        ttk.Label(header, textvariable=self.connection_var).pack(side="right")
        ttk.Label(header, textvariable=self.scale_var).pack(side="right", padx=12)

        status_frame = ttk.LabelFrame(outer, text="Selected Axis Statusword")
        status_frame.pack(fill="x", pady=(0, 10))
        for index, (bit, label) in enumerate(STATUSWORD_BITS):
            lamp = tk.Label(
                status_frame,
                text=f"b{bit} {label}",
                width=11,
                bg="#3a3a3a",
                fg="#d0d0d0",
                relief="sunken",
                bd=1,
            )
            lamp.grid(
                row=index // 8,
                column=index % 8,
                padx=3,
                pady=3,
                sticky="ew",
            )
            status_frame.columnconfigure(index % 8, weight=1)
            self.statusword_lamps.append(lamp)

        mode_frame = ttk.LabelFrame(outer, text="Motion Mode")
        mode_frame.pack(fill="x", pady=(0, 10))
        ttk.Radiobutton(
            mode_frame,
            text="PP",
            value="pp",
            variable=self.motion_mode_var,
            command=self.apply_motion_mode,
        ).pack(side="left", padx=8, pady=5)
        ttk.Radiobutton(
            mode_frame,
            text="CSP",
            value="csp",
            variable=self.motion_mode_var,
            command=self.apply_motion_mode,
        ).pack(side="left", padx=8, pady=5)
        ttk.Radiobutton(
            mode_frame,
            text="CSV",
            value="csv",
            variable=self.motion_mode_var,
            state="disabled",
        ).pack(side="left", padx=8, pady=5)
        ttk.Label(
            mode_frame,
            text="CSV is available through the TCP protocol only.",
        ).pack(side="left", padx=12, pady=5)

        table = ttk.Frame(outer)
        table.pack(fill="x")

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
            "Command Velocity",
            "Statusword",
            "Error",
            "Err Reg",
        ]
        for column, header_text in enumerate(headers):
            ttk.Label(table, text=header_text, anchor="center").grid(
                row=0,
                column=column,
                padx=4,
                pady=4,
                sticky="ew",
            )
            table.columnconfigure(column, weight=1)

        for row, axis_name in enumerate(self.axis_names, start=1):
            ttk.Label(table, text=axis_name, anchor="center").grid(
                row=row,
                column=0,
                padx=4,
                pady=4,
                sticky="ew",
            )

            axis_limit_vars = []
            for column in range(1, 5):
                var = tk.StringVar(value="0.0")
                entry = ttk.Entry(table, textvariable=var, justify="right", width=10)
                entry.grid(row=row, column=column, padx=4, pady=4, sticky="ew")
                entry.bind(
                    "<KeyRelease>",
                    lambda _event, watched_var=var: self.mark_dirty(watched_var),
                )
                axis_limit_vars.append(var)
                if column == 4:
                    self.kp_entries.append(entry)

            command_var = tk.StringVar(value="0.0")
            ttk.Entry(table, textvariable=command_var, justify="right", width=12).grid(
                row=row,
                column=5,
                padx=4,
                pady=4,
                sticky="ew",
            )

            target_var = tk.StringVar(value="0.0")
            actual_position_var = tk.StringVar(value="0.0")
            actual_velocity_var = tk.StringVar(value="0.0")
            statusword_var = tk.StringVar(value="0x0000")
            error_code_var = tk.StringVar(value="0x0000")
            error_register_var = tk.StringVar(value="0x00")

            command_velocity_var = tk.StringVar(value="0.0")

            for column, var in [
                (6, target_var),
                (7, actual_position_var),
                (8, actual_velocity_var),
                (9, command_velocity_var),
                (10, statusword_var),
                (11, error_code_var),
                (12, error_register_var),
            ]:
                ttk.Label(table, textvariable=var, anchor="e").grid(
                    row=row,
                    column=column,
                    padx=4,
                    pady=4,
                    sticky="ew",
                )

            self.limit_vars.append(axis_limit_vars)
            self.command_vars.append(command_var)
            self.target_vars.append(target_var)
            self.actual_position_vars.append(actual_position_var)
            self.actual_velocity_vars.append(actual_velocity_var)
            self.command_velocity_vars.append(command_velocity_var)
            self.statusword_vars.append(statusword_var)
            self.error_code_vars.append(error_code_var)
            self.error_register_vars.append(error_register_var)
            self.repeat_point_a_vars.append(tk.StringVar(value="0.0"))
            self.repeat_point_b_vars.append(tk.StringVar(value="0.0"))
        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(12, 8))
        ttk.Button(buttons, text="Apply Limits", command=self.apply_limits).pack(
            side="left",
            padx=4,
        )
        ttk.Button(buttons, text="Send Command", command=self.send_command).pack(
            side="left",
            padx=4,
        )
        ttk.Label(buttons, text="Manual CW").pack(side="left", padx=(12, 4))
        for label, value in [
            ("Shutdown", 0x0006),
            ("Switch On", 0x0007),
            ("Enable Op", 0x000F),
            ("Disable Voltage", 0x0000),
        ]:
            ttk.Button(
                buttons,
                text=label,
                command=lambda cw=value: self.send_manual_controlword(cw),
            ).pack(side="left", padx=2)
        ttk.Button(
            buttons,
            text="Apply Limits + Send",
            command=self.apply_limits_and_send,
        ).pack(side="left", padx=(12, 4))
        ttk.Button(buttons, text="Alarm Ack", command=self.alarm_ack).pack(
            side="left",
            padx=4,
        )

        jog = ttk.LabelFrame(outer, text="Jog")
        jog.pack(fill="x", pady=(4, 10))
        ttk.Label(jog, text="Selected Axis").pack(side="left", padx=(8, 4), pady=6)
        ttk.Label(jog, textvariable=self.selected_axis_label_var, width=8).pack(
            side="left",
            padx=4,
            pady=6,
        )
        ttk.Label(jog, text="Step").pack(side="left", padx=(12, 4), pady=6)
        ttk.Entry(
            jog,
            textvariable=self.jog_step_var,
            justify="right",
            width=12,
        ).pack(side="left", padx=4, pady=6)
        ttk.Button(
            jog,
            text="Jog -",
            command=lambda: self.send_jog(-1.0),
        ).pack(side="left", padx=4, pady=6)
        ttk.Button(
            jog,
            text="Jog +",
            command=lambda: self.send_jog(1.0),
        ).pack(side="left", padx=4, pady=6)

        repeat = ttk.LabelFrame(outer, text="Repeat Motion")
        repeat.pack(fill="x", pady=(4, 10))
        ttk.Label(repeat, text="Axis").grid(row=0, column=0, padx=5, pady=4)
        ttk.Label(repeat, text="Point A").grid(row=0, column=1, padx=5, pady=4)
        ttk.Label(repeat, text="Point B").grid(row=0, column=2, padx=5, pady=4)
        for row, axis_name in enumerate(self.axis_names, start=1):
            ttk.Label(repeat, text=axis_name).grid(row=row, column=0, padx=5, pady=4)
            ttk.Entry(
                repeat,
                textvariable=self.repeat_point_a_vars[row - 1],
                justify="right",
                width=14,
            ).grid(row=row, column=1, padx=5, pady=4)
            ttk.Entry(
                repeat,
                textvariable=self.repeat_point_b_vars[row - 1],
                justify="right",
                width=14,
            ).grid(row=row, column=2, padx=5, pady=4)

        ttk.Label(repeat, text="Period (s)").grid(row=1, column=3, padx=5, pady=4)
        ttk.Entry(
            repeat,
            textvariable=self.repeat_period_var,
            justify="right",
            width=10,
        ).grid(row=1, column=4, padx=5, pady=4)
        ttk.Button(repeat, text="Start Repeat", command=self.start_repeat).grid(
            row=1,
            column=5,
            padx=5,
            pady=4,
        )
        ttk.Button(repeat, text="Stop Repeat", command=self.stop_repeat).grid(
            row=1,
            column=6,
            padx=5,
            pady=4,
        )

        traces = ttk.Frame(outer)
        traces.pack(fill="both", expand=True)
        self.position_trace = TraceCanvas(traces, self.axis_names, "Actual Position")
        self.velocity_trace = TraceCanvas(traces, self.axis_names, "Actual Velocity", 3)

    def mark_dirty(self, var):
        self.dirty_vars.add(id(var))

    def apply_limits(self):
        limits = self.read_limit_values()
        if limits is None:
            return
        self.try_send(lambda: self.client.send_motion_limits(limits))
        for axis_limit_vars in self.limit_vars:
            for var in axis_limit_vars:
                self.dirty_vars.discard(id(var))

    def send_command(self):
        targets = self.read_command_values()
        if targets is None:
            return
        self.try_send(lambda: self.client.send_target_positions(targets))

    def apply_limits_and_send(self):
        limits = self.read_limit_values()
        targets = self.read_command_values()
        if limits is None or targets is None:
            return
        self.try_send(lambda: self.client.send_motion_limits(limits))
        self.try_send(lambda: self.client.send_target_positions(targets))

    def alarm_ack(self):
        self.try_send(self.client.send_alarm_ack)

    def update_selected_axis_label(self):
        axis_index = self.selected_axis()
        self.selected_axis_label_var.set(self.axis_names[axis_index])

    def update_statusword_lamps(self, statusword):
        for lamp, (bit, _label) in zip(self.statusword_lamps, STATUSWORD_BITS):
            is_on = bool(statusword & (1 << bit))
            if not is_on:
                lamp.configure(bg="#3a3a3a", fg="#d0d0d0")
            elif bit == 3:
                lamp.configure(bg="#c0392b", fg="#ffffff")
            elif bit == 7:
                lamp.configure(bg="#d68910", fg="#ffffff")
            else:
                lamp.configure(bg="#1e8449", fg="#ffffff")

    def statusword_state_text(self, statusword):
        masked = statusword & 0x006F
        if statusword & 0x0008:
            return "Fault"
        if masked == 0x0027:
            return "Op Enabled"
        if masked == 0x0023:
            return "Switched On"
        if masked == 0x0021:
            return "Ready"
        if masked == 0x0040:
            return "Switch Disabled"
        if masked == 0x0000:
            return "Not Ready"
        return "State Changed"

    def selected_axis(self):
        return int(self.selected_axis_var.get())

    def send_manual_controlword(self, controlword):
        axis_index = self.selected_axis()
        self.try_send(lambda: self.client.send_controlword(controlword, axis_index))

    def send_jog(self, direction):
        axis_index = self.selected_axis()
        try:
            step = float(self.jog_step_var.get())
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Jog step must be numeric.",
            )
            return
        if step <= 0:
            messagebox.showerror(
                "Invalid Input",
                "Jog step must be greater than 0.",
            )
            return

        self.try_send(
            lambda: self.client.send_jog_position(axis_index, direction * step)
        )

    def apply_motion_mode(self):
        mode = self.motion_mode_var.get()
        if mode == "csv":
            self.motion_mode_var.set(self.server_motion_mode)
            return

        self.try_send(lambda: self.client.send_motion_mode(mode))

    def start_repeat(self):
        repeat_config = self.read_repeat_values()
        if repeat_config is None:
            return
        point_a, point_b, period = repeat_config
        self.repeat_enabled = True
        self.repeat_points = [point_a, point_b]
        self.repeat_period = period
        self.repeat_index = 0
        self.repeat_wait_until = 0.0
        self.last_sent_repeat_target = None
        self.repeat_waiting_to_send = False

    def stop_repeat(self):
        self.repeat_enabled = False
        self.last_sent_repeat_target = None
        self.repeat_waiting_to_send = False

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

    def read_command_values(self):
        try:
            return [
                float(var.get())
                for var in self.command_vars
            ]
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Command Position must be numeric values.",
            )
            return None

    def read_repeat_values(self):
        try:
            point_a = [float(var.get()) for var in self.repeat_point_a_vars]
            point_b = [float(var.get()) for var in self.repeat_point_b_vars]
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

    def try_send(self, send_func):
        try:
            send_func()
        except Exception as exc:
            messagebox.showerror("Send Failed", str(exc))

    def update_gui(self):
        connected, error, feedback = self.client.get_snapshot()
        self.connection_var.set(
            f"Connected {self.client.host}:{self.client.port}"
            if connected
            else f"Disconnected {error}"
        )

        target_positions = self._values(feedback, "target_positions", 0.0)
        actual_positions = self._values(feedback, "actual_positions", 0.0)
        actual_velocities = self._values(feedback, "actual_velocities", 0.0)
        command_velocities = self._values(feedback, "command_velocities", 0.0)
        statuswords = self._values(feedback, "statuswords", 0)
        diagnostics = feedback.get("diagnostics", [])
        motion_mode = str(feedback.get("motion_mode", self.server_motion_mode)).lower()
        csp_counts_per_unit = float(feedback.get("csp_counts_per_unit", 1.0))
        motion_limits = self._motion_limits(feedback)
        self.scale_var.set(f"CSP scale: {csp_counts_per_unit:g} count/unit")
        selected_axis = self.selected_axis()
        self.update_statusword_lamps(int(statuswords[selected_axis]))

        if motion_mode in {"pp", "csp", "csv"}:
            self.server_motion_mode = motion_mode
            if self.motion_mode_var.get() != motion_mode:
                self.motion_mode_var.set(motion_mode)
            self.update_mode_dependent_controls()

        for index in range(self.axis_count):
            self.target_vars[index].set(f"{target_positions[index]:.3f}")
            self.actual_position_vars[index].set(f"{actual_positions[index]:.3f}")
            self.actual_velocity_vars[index].set(f"{actual_velocities[index]:.3f}")
            self.command_velocity_vars[index].set(f"{command_velocities[index]:.3f}")
            self.statusword_vars[index].set(
                self.statusword_state_text(int(statuswords[index]))
            )

            diag = diagnostics[index] if index < len(diagnostics) else {}
            self.error_code_vars[index].set(self._format_diag(diag, "error_code", 4))
            self.error_register_vars[index].set(
                self._format_diag(diag, "error_register", 2)
            )

            for limit_index in range(4):
                var = self.limit_vars[index][limit_index]
                if id(var) not in self.dirty_vars:
                    var.set(f"{motion_limits[index][limit_index]:.3f}")

        self.position_trace.add_sample(actual_positions)
        self.velocity_trace.add_sample(actual_velocities)
        self.position_trace.draw()
        self.velocity_trace.draw()

        self.update_repeat(actual_positions)
        self.root.after(GUI_PERIOD_MS, self.update_gui)

    def update_mode_dependent_controls(self):
        kp_state = "normal" if self.server_motion_mode == "csp" else "disabled"
        for entry in self.kp_entries:
            entry.configure(state=kp_state)

    def update_repeat(self, actual_positions):
        if not self.repeat_enabled or self.repeat_points is None:
            return

        now = time.monotonic()
        target = self.repeat_points[self.repeat_index]
        if self.last_sent_repeat_target is None:
            self.try_send(lambda: self.client.send_target_positions(target))
            self.last_sent_repeat_target = list(target)
            return

        if self.repeat_waiting_to_send or now < self.repeat_wait_until:
            return

        reached = all(
            abs(actual_positions[index] - self.last_sent_repeat_target[index])
            <= REPEAT_TOLERANCE
            for index in range(self.axis_count)
        )
        if not reached:
            return

        self.repeat_wait_until = now + self.repeat_period
        self.repeat_index = 1 - self.repeat_index
        next_target = self.repeat_points[self.repeat_index]
        self.repeat_waiting_to_send = True
        self.root.after(
            int(self.repeat_period * 1000),
            lambda: self._send_repeat_target(next_target),
        )

    def _send_repeat_target(self, target):
        if not self.repeat_enabled:
            return
        self.try_send(lambda: self.client.send_target_positions(target))
        self.last_sent_repeat_target = list(target)
        self.repeat_waiting_to_send = False

    def _values(self, feedback, key, default):
        values = list(feedback.get(key, []))
        while len(values) < self.axis_count:
            values.append(default)
        return values[:self.axis_count]

    def _motion_limits(self, feedback):
        flat = list(feedback.get("motion_limits", []))
        required = self.axis_count * 4
        while len(flat) < required:
            flat.append(0.0)
        return [
            [
                float(flat[index * 4]),
                float(flat[index * 4 + 1]),
                float(flat[index * 4 + 2]),
                float(flat[index * 4 + 3]),
            ]
            for index in range(self.axis_count)
        ]

    def _format_diag(self, diagnostics, key, width):
        value = diagnostics.get(key, None)
        if isinstance(value, int):
            return f"0x{value:0{width}X}"
        if value is None:
            return "n/a"
        return "read fail"

    def close(self):
        self.client.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    host, port, axis_names = read_runtime_config()
    client = AxisServerClient(host, port, len(axis_names))
    client.start()
    gui = AxisServerControlPanel(client, axis_names)
    gui.run()


if __name__ == "__main__":
    main()
