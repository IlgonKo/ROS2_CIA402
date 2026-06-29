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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
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
            "command_positions": [0.0 for _ in range(axis_count)],
            "position_counts_per_unit": 1.0,
            "statuswords": [0 for _ in range(axis_count)],
            "motion_limits": [0.0 for _ in range(axis_count * 4)],
            "software_position_limits": [0.0 for _ in range(axis_count * 2)],
            "motion_mode": "pp",
            "capabilities": {},
            "diagnostics": [],
            "command_authority": {
                "owner": None,
                "owned_by_this_client": False,
                "available": True,
            },
        }
        self.last_notice = ""
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
            elif message.get("type") in {"command_authority", "command_rejected"}:
                self._store_notice(message)

    def _store_feedback(self, message):
        with self.lock:
            self.feedback = message

    def _store_notice(self, message):
        with self.lock:
            self.last_notice = str(message.get("message", ""))

    def get_snapshot(self):
        with self.lock:
            notice = self.last_notice
            self.last_notice = ""
            return self.connected, self.last_error, dict(self.feedback), notice

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

    def send_software_position_limits(self, limits):
        self.send_json(
            {
                "type": "software_position_limits",
                "limits": [
                    [float(value) for value in axis_limits]
                    for axis_limits in limits
                ],
            }
        )

    def send_motion_mode(self, mode, axis_index=None):
        message = {
            "type": "motion_mode",
            "mode": str(mode).lower(),
        }
        if axis_index is not None:
            message["axis"] = int(axis_index)

        self.send_json(message)

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

    def request_command_authority(self):
        self.send_json({"type": "command_authority_request"})

    def release_command_authority(self):
        self.send_json({"type": "command_authority_release"})


class TraceCanvas:
    def __init__(self, parent, series_names, title, color_offset=0):
        self.series_names = series_names
        self.title = title
        self.history = [
            []
            for _ in series_names
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

    def set_series_names(self, series_names):
        if self.series_names == series_names:
            return

        self.series_names = series_names
        self.history = [
            []
            for _ in series_names
        ]

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
                margin + 8 + index * 120,
                height - 14,
                text=self.series_names[index],
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
        self.root.geometry("1180x820")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.limit_vars = [tk.StringVar(value="0.0") for _ in range(4)]
        self.software_limit_vars = [
            tk.StringVar(value="0.0"),
            tk.StringVar(value="0.0"),
        ]
        self.command_var = tk.StringVar(value="0.0")
        self.target_var = tk.StringVar(value="0.0")
        self.actual_position_var = tk.StringVar(value="0.0")
        self.actual_velocity_var = tk.StringVar(value="0.0")
        self.command_velocity_var = tk.StringVar(value="0.0")
        self.statusword_var = tk.StringVar(value="0x0000")
        self.error_code_var = tk.StringVar(value="0x0000")
        self.error_register_var = tk.StringVar(value="0x00")
        self.kp_entries = []
        self.repeat_point_a_var = tk.StringVar(value="0.0")
        self.repeat_point_b_var = tk.StringVar(value="0.0")
        self.repeat_period_var = tk.StringVar(value="2.0")
        self.selected_axis_var = tk.StringVar(value="0")
        self.selected_axis_label_var = tk.StringVar(value=self.axis_names[0])
        self.jog_step_var = tk.StringVar(value="100.0")
        self.connection_var = tk.StringVar(value="Disconnected")
        self.command_authority_var = tk.StringVar(value="Authority: available")
        self.command_authority_button_var = tk.StringVar(value="Request Authority")
        self.scale_var = tk.StringVar(value="CSP scale: 1.0 count/unit")
        self.motion_mode_var = tk.StringVar(value="pp")
        self.server_motion_mode = "pp"
        self.server_capabilities = {}
        self.dirty_vars = set()
        self.statusword_lamps = []
        self.latest_target_positions = [0.0 for _ in range(self.axis_count)]
        self.latest_actual_positions = [0.0 for _ in range(self.axis_count)]
        self.latest_motion_limits = [
            [0.0, 0.0, 0.0, 0.0]
            for _ in range(self.axis_count)
        ]
        self.latest_software_position_limits = [
            [0.0, 0.0]
            for _ in range(self.axis_count)
        ]
        self.latest_motion_modes = ["pp" for _ in range(self.axis_count)]
        self.position_counts_per_unit = 1000.0

        self.repeat_enabled = False
        self.repeat_axis_index = 0
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
        ttk.Button(
            header,
            textvariable=self.command_authority_button_var,
            command=self.toggle_command_authority,
        ).pack(side="left", padx=(14, 4))
        ttk.Label(header, textvariable=self.command_authority_var).pack(
            side="left",
            padx=4,
        )
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

        detail = ttk.LabelFrame(outer, text="Selected Axis Command / Feedback")
        detail.pack(fill="x")

        fields = [
            ("Selected Axis", self.selected_axis_label_var, "label"),
            ("Max Velocity mm/s", self.limit_vars[0], "entry"),
            ("Accel mm/s^2", self.limit_vars[1], "entry"),
            ("Decel mm/s^2", self.limit_vars[2], "entry"),
            ("Kp", self.limit_vars[3], "entry_kp"),
            ("Negative SW Limit mm", self.software_limit_vars[0], "entry_sw"),
            ("Positive SW Limit mm", self.software_limit_vars[1], "entry_sw"),
            ("Command Position mm", self.command_var, "entry"),
            ("Target Position mm", self.target_var, "label"),
            ("Actual Position mm", self.actual_position_var, "label"),
            ("Actual Velocity mm/s", self.actual_velocity_var, "label"),
            ("Command Velocity mm/s", self.command_velocity_var, "label"),
            ("Statusword", self.statusword_var, "label"),
            ("Error", self.error_code_var, "label"),
            ("Err Reg", self.error_register_var, "label"),
        ]
        for index, (label, var, kind) in enumerate(fields):
            row = index // 4
            column = (index % 4) * 2
            ttk.Label(detail, text=label).grid(
                row=row,
                column=column,
                padx=5,
                pady=5,
                sticky="e",
            )
            if kind.startswith("entry"):
                entry = ttk.Entry(detail, textvariable=var, justify="right", width=14)
                entry.bind(
                    "<KeyRelease>",
                    lambda _event, watched_var=var: self.mark_dirty(watched_var),
                )
                entry.grid(row=row, column=column + 1, padx=5, pady=5, sticky="ew")
                if kind == "entry_kp":
                    self.kp_entries.append(entry)
            else:
                ttk.Label(detail, textvariable=var, anchor="e", width=16).grid(
                    row=row,
                    column=column + 1,
                    padx=5,
                    pady=5,
                    sticky="ew",
                )
            detail.columnconfigure(column + 1, weight=1)
        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(12, 8))
        ttk.Button(buttons, text="Apply Limits", command=self.apply_limits).pack(
            side="left",
            padx=4,
        )
        ttk.Button(
            buttons,
            text="Apply SW Limits",
            command=self.apply_software_limits,
        ).pack(
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
        ttk.Label(jog, text="Step mm").pack(side="left", padx=(12, 4), pady=6)
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
        ttk.Label(repeat, text="Selected Axis").grid(row=0, column=0, padx=5, pady=4)
        ttk.Label(repeat, textvariable=self.selected_axis_label_var).grid(
            row=0,
            column=1,
            padx=5,
            pady=4,
            sticky="w",
        )
        ttk.Label(repeat, text="Point A mm").grid(row=0, column=2, padx=5, pady=4)
        ttk.Entry(
            repeat,
            textvariable=self.repeat_point_a_var,
            justify="right",
            width=14,
        ).grid(row=0, column=3, padx=5, pady=4)
        ttk.Label(repeat, text="Point B mm").grid(row=0, column=4, padx=5, pady=4)
        ttk.Entry(
            repeat,
            textvariable=self.repeat_point_b_var,
            justify="right",
            width=14,
        ).grid(row=0, column=5, padx=5, pady=4)
        ttk.Label(repeat, text="Period (s)").grid(row=0, column=6, padx=5, pady=4)
        ttk.Entry(
            repeat,
            textvariable=self.repeat_period_var,
            justify="right",
            width=10,
        ).grid(row=0, column=7, padx=5, pady=4)
        ttk.Button(repeat, text="Start Repeat", command=self.start_repeat).grid(
            row=0,
            column=8,
            padx=5,
            pady=4,
        )
        ttk.Button(repeat, text="Stop Repeat", command=self.stop_repeat).grid(
            row=0,
            column=9,
            padx=5,
            pady=4,
        )

        traces = ttk.Frame(outer)
        traces.pack(fill="both", expand=True)
        self.position_trace = TraceCanvas(
            traces,
            ["Actual Position mm", "Target Position mm"],
            "Position",
        )
        self.velocity_trace = TraceCanvas(
            traces,
            ["Actual Velocity mm/s"],
            "Velocity",
            2,
        )

    def mark_dirty(self, var):
        self.dirty_vars.add(id(var))

    def apply_limits(self):
        axis_limits = self.read_selected_limit_values()
        if axis_limits is None:
            return
        axis_index = self.selected_axis()
        limits = [list(values) for values in self.latest_motion_limits]
        limits[axis_index] = axis_limits
        self.try_send(lambda: self.client.send_motion_limits(limits))
        for var in self.limit_vars:
            self.dirty_vars.discard(id(var))

    def apply_software_limits(self):
        software_limits_mm = self.read_selected_software_limit_values()
        if software_limits_mm is None:
            return

        negative_limit = self.position_unit_to_count(software_limits_mm[0])
        positive_limit = self.position_unit_to_count(software_limits_mm[1])
        axis_index = self.selected_axis()
        limits = [list(values) for values in self.latest_software_position_limits]
        limits[axis_index] = [negative_limit, positive_limit]
        self.try_send(lambda: self.client.send_software_position_limits(limits))
        for var in self.software_limit_vars:
            self.dirty_vars.discard(id(var))

    def send_command(self):
        target_position_mm = self.read_selected_command_value()
        if target_position_mm is None:
            return
        axis_index = self.selected_axis()
        targets = list(self.latest_target_positions)
        targets[axis_index] = self.position_unit_to_count(target_position_mm)
        self.try_send(lambda: self.client.send_target_positions(targets))

    def apply_limits_and_send(self):
        axis_limits = self.read_selected_limit_values()
        target_position_mm = self.read_selected_command_value()
        if axis_limits is None or target_position_mm is None:
            return
        axis_index = self.selected_axis()
        limits = [list(values) for values in self.latest_motion_limits]
        targets = list(self.latest_target_positions)
        limits[axis_index] = axis_limits
        targets[axis_index] = self.position_unit_to_count(target_position_mm)
        self.try_send(lambda: self.client.send_motion_limits(limits))
        self.try_send(lambda: self.client.send_target_positions(targets))

    def alarm_ack(self):
        self.try_send(self.client.send_alarm_ack)

    def toggle_command_authority(self):
        _, _, feedback, _ = self.client.get_snapshot()
        authority = feedback.get("command_authority", {})
        if authority.get("owned_by_this_client", False):
            self.try_send(self.client.release_command_authority)
        else:
            self.try_send(self.client.request_command_authority)

    def update_selected_axis_label(self):
        self.stop_repeat()
        self.position_trace.history = [
            []
            for _ in self.position_trace.series_names
        ]
        self.velocity_trace.history = [
            []
            for _ in self.velocity_trace.series_names
        ]
        axis_index = self.selected_axis()
        self.selected_axis_label_var.set(self.axis_names[axis_index])
        self.dirty_vars.clear()

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
            lambda: self.client.send_jog_position(
                axis_index,
                self.position_unit_to_count(direction * step),
            )
        )

    def apply_motion_mode(self):
        mode = self.motion_mode_var.get()
        if mode == "csv":
            self.motion_mode_var.set(self.latest_motion_modes[self.selected_axis()])
            return

        axis_index = self.selected_axis()
        self.try_send(lambda: self.client.send_motion_mode(mode, axis_index))

    def start_repeat(self):
        repeat_config = self.read_repeat_values()
        if repeat_config is None:
            return
        point_a, point_b, period = repeat_config
        self.repeat_enabled = True
        self.repeat_axis_index = self.selected_axis()
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

    def read_selected_limit_values(self):
        try:
            return [float(var.get()) for var in self.limit_vars]
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Max Velocity, Accel, Decel, Kp must be numeric values.",
            )
            return None

    def read_selected_software_limit_values(self):
        try:
            limits = [float(var.get()) for var in self.software_limit_vars]
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Negative/Positive SW Limit must be numeric values.",
            )
            return None

        if limits[0] > limits[1]:
            messagebox.showerror(
                "Invalid Input",
                "Negative SW Limit must be less than or equal to Positive SW Limit.",
            )
            return None

        return limits

    def read_selected_command_value(self):
        try:
            return float(self.command_var.get())
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Command Position must be numeric.",
            )
            return None

    def read_repeat_values(self):
        try:
            point_a = float(self.repeat_point_a_var.get())
            point_b = float(self.repeat_point_b_var.get())
            period = float(self.repeat_period_var.get())
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Repeat points and period must be numeric.",
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
        connected, error, feedback, notice = self.client.get_snapshot()
        self.connection_var.set(
            f"Connected {self.client.host}:{self.client.port}"
            if connected
            else f"Disconnected {error}"
        )
        if notice:
            messagebox.showinfo("Axis Server", notice)

        target_positions = self._values(feedback, "target_positions", 0.0)
        actual_positions = self._values(feedback, "actual_positions", 0.0)
        actual_velocities = self._values(feedback, "actual_velocities", 0.0)
        command_positions = self._values(feedback, "command_positions", 0.0)
        command_velocities = self._values(feedback, "command_velocities", 0.0)
        statuswords = self._values(feedback, "statuswords", 0)
        diagnostics = feedback.get("diagnostics", [])
        motion_mode = str(feedback.get("motion_mode", self.server_motion_mode)).lower()
        motion_modes = [
            str(value).lower()
            for value in feedback.get("motion_modes", [])
        ]
        while len(motion_modes) < self.axis_count:
            motion_modes.append(motion_mode)
        position_counts_per_unit = float(
            feedback.get(
                "position_counts_per_unit",
                feedback.get("csp_counts_per_unit", 1.0),
            )
        )
        motion_limits = self._motion_limits(feedback)
        software_position_limits = self._software_position_limits(feedback)
        self.latest_target_positions = target_positions
        self.latest_actual_positions = actual_positions
        self.latest_motion_limits = motion_limits
        self.latest_software_position_limits = software_position_limits
        self.latest_motion_modes = motion_modes[:self.axis_count]
        self.server_capabilities = dict(feedback.get("capabilities", {}))
        self.update_command_authority(feedback.get("command_authority", {}))
        self.position_counts_per_unit = max(position_counts_per_unit, 1e-9)
        self.scale_var.set(
            f"Position scale: {self.position_counts_per_unit:g} count/mm"
        )
        selected_axis = self.selected_axis()
        self.update_statusword_lamps(int(statuswords[selected_axis]))

        selected_motion_mode = self.latest_motion_modes[selected_axis]
        if selected_motion_mode in {"pp", "csp", "csv"}:
            self.server_motion_mode = selected_motion_mode
            if self.motion_mode_var.get() != selected_motion_mode:
                self.motion_mode_var.set(selected_motion_mode)
            self.update_mode_dependent_controls()

        self.target_var.set(
            f"{self.position_count_to_unit(target_positions[selected_axis]):.3f}"
        )
        self.actual_position_var.set(
            f"{self.position_count_to_unit(actual_positions[selected_axis]):.3f}"
        )
        self.actual_velocity_var.set(f"{actual_velocities[selected_axis]:.3f}")
        self.command_velocity_var.set(
            f"{self.velocity_count_to_unit(command_velocities[selected_axis]):.3f}"
            if selected_motion_mode == "csp"
            else "n/a"
        )
        self.statusword_var.set(
            self.statusword_state_text(int(statuswords[selected_axis]))
        )

        diag = diagnostics[selected_axis] if selected_axis < len(diagnostics) else {}
        self.error_code_var.set(self._format_diag(diag, "error_code", 4))
        self.error_register_var.set(self._format_diag(diag, "error_register", 2))

        for limit_index in range(4):
            var = self.limit_vars[limit_index]
            if id(var) not in self.dirty_vars:
                var.set(f"{motion_limits[selected_axis][limit_index]:.3f}")

        for limit_index in range(2):
            var = self.software_limit_vars[limit_index]
            if id(var) not in self.dirty_vars:
                var.set(
                    f"{self.position_count_to_unit(software_position_limits[selected_axis][limit_index]):.3f}"
                )

        if selected_motion_mode == "csp":
            self.position_trace.set_series_names(
                ["Actual Position mm", "Target Position mm", "CSP Command Position mm"]
            )
            self.velocity_trace.set_series_names(
                ["Actual Velocity mm/s", "Command Velocity mm/s"]
            )
            self.position_trace.add_sample(
                [
                    self.position_count_to_unit(actual_positions[selected_axis]),
                    self.position_count_to_unit(target_positions[selected_axis]),
                    self.position_count_to_unit(command_positions[selected_axis]),
                ]
            )
            self.velocity_trace.add_sample(
                [
                    actual_velocities[selected_axis],
                    self.velocity_count_to_unit(command_velocities[selected_axis]),
                ]
            )
        else:
            self.position_trace.set_series_names(
                ["Actual Position mm", "Target Position mm"]
            )
            self.velocity_trace.set_series_names(["Actual Velocity mm/s"])
            self.position_trace.add_sample(
                [
                    self.position_count_to_unit(actual_positions[selected_axis]),
                    self.position_count_to_unit(target_positions[selected_axis]),
                ]
            )
            self.velocity_trace.add_sample([actual_velocities[selected_axis]])
        self.position_trace.draw()
        self.velocity_trace.draw()

        self.update_repeat(actual_positions)
        self.root.after(GUI_PERIOD_MS, self.update_gui)

    def update_command_authority(self, authority):
        owner = authority.get("owner", None)
        owned_by_this_client = bool(authority.get("owned_by_this_client", False))
        if owned_by_this_client:
            self.command_authority_var.set("Authority: owned by this panel")
            self.command_authority_button_var.set("Release Authority")
        elif owner is None:
            self.command_authority_var.set("Authority: available")
            self.command_authority_button_var.set("Request Authority")
        else:
            self.command_authority_var.set(f"Authority: held by client {owner}")
            self.command_authority_button_var.set("Request Authority")

    def update_mode_dependent_controls(self):
        kp_state = (
            "normal"
            if (
                self.server_motion_mode == "csp"
                and self.server_capabilities.get("position_loop_gain", False)
            )
            else "disabled"
        )
        for entry in self.kp_entries:
            entry.configure(state=kp_state)

    def update_repeat(self, actual_positions):
        if not self.repeat_enabled or self.repeat_points is None:
            return

        now = time.monotonic()
        axis_index = self.repeat_axis_index
        target = self._target_vector_for_axis(
            axis_index,
            self.repeat_points[self.repeat_index],
        )
        if self.last_sent_repeat_target is None:
            self.try_send(lambda: self.client.send_target_positions(target))
            self.last_sent_repeat_target = target[axis_index]
            return

        if self.repeat_waiting_to_send or now < self.repeat_wait_until:
            return

        reached = (
            abs(actual_positions[axis_index] - self.last_sent_repeat_target)
            <= REPEAT_TOLERANCE
        )
        if not reached:
            return

        self.repeat_wait_until = now + self.repeat_period
        self.repeat_index = 1 - self.repeat_index
        next_target = self.repeat_points[self.repeat_index]
        self.repeat_waiting_to_send = True
        self.root.after(
            int(self.repeat_period * 1000),
            lambda: self._send_repeat_target(axis_index, next_target),
        )

    def _send_repeat_target(self, axis_index, target_position):
        if not self.repeat_enabled:
            return
        target = self._target_vector_for_axis(axis_index, target_position)
        self.try_send(lambda: self.client.send_target_positions(target))
        self.last_sent_repeat_target = target[axis_index]
        self.repeat_waiting_to_send = False

    def _target_vector_for_axis(self, axis_index, target_position):
        targets = list(self.latest_target_positions)
        targets[axis_index] = self.position_unit_to_count(float(target_position))
        return targets

    def position_count_to_unit(self, position_count):
        return float(position_count) / self.position_counts_per_unit

    def position_unit_to_count(self, position_unit):
        return float(position_unit) * self.position_counts_per_unit

    def velocity_count_to_unit(self, velocity_count):
        return float(velocity_count) / self.position_counts_per_unit

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

    def _software_position_limits(self, feedback):
        flat = list(feedback.get("software_position_limits", []))
        required = self.axis_count * 2
        while len(flat) < required:
            flat.append(0.0)
        return [
            [
                float(flat[index * 2]),
                float(flat[index * 2 + 1]),
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
