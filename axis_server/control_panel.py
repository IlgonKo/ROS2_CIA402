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
PANEL_SDO_READ_DELAY = 1.0
PANEL_SDO_READ_PERIOD = 0.1
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
    (15, "Referenced"),
]


PV_USER_POSITION_UNITS = {
    0x1000: "rad",
    0x4100: "deg",
    0xB400: "rev",
}

LINEAR_USER_POSITION_UNITS = {
    0x0100: "mm",
}


def user_position_unit_name(user_position_unit):
    if user_position_unit is None:
        return "unknown"
    unit = int(user_position_unit)
    return (
        PV_USER_POSITION_UNITS.get(unit)
        or LINEAR_USER_POSITION_UNITS.get(unit)
        or f"0x{unit:04X}"
    )


def axis_motion_kind(user_position_unit):
    if user_position_unit is None:
        return "unknown"
    unit = int(user_position_unit)
    if unit in PV_USER_POSITION_UNITS:
        return "rotary"
    if unit in LINEAR_USER_POSITION_UNITS:
        return "linear"
    return "unknown"


def scale_from_exponent(exponent, default=1.0):
    if exponent is None:
        return default
    return 10.0 ** int(exponent)


def build_axis_metadata(axis_index, user_position_unit, exponents):
    if exponents is None:
        exponents = [None, None, None, None]
    position_unit = user_position_unit_name(user_position_unit)
    acceleration_scale = scale_from_exponent(exponents[2], 1.0)
    return {
        "axis": axis_index,
        "user_position_unit": user_position_unit,
        "user_position_unit_name": position_unit,
        "motion_kind": axis_motion_kind(user_position_unit),
        "pv_allowed": user_position_unit is not None
        and int(user_position_unit) in PV_USER_POSITION_UNITS,
        "converting_unit_exponents": exponents,
        "position_unit": position_unit,
        "velocity_unit": f"{position_unit}/s",
        "acceleration_unit": f"{position_unit}/s^2",
        "deceleration_unit": f"{position_unit}/s^2",
        "jerk_unit": f"{position_unit}/s^3",
        "position_scale": scale_from_exponent(exponents[0], 1.0),
        "velocity_scale": scale_from_exponent(exponents[1], 1.0),
        "acceleration_scale": acceleration_scale,
        "deceleration_scale": acceleration_scale,
        "jerk_scale": scale_from_exponent(exponents[3], 1.0),
    }


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
    host = os.environ.get(
        "AXIS_SERVER_HOST",
        env_file.get("AXIS_SERVER_HOST", "127.0.0.1"),
    )
    port = int(
        os.environ.get(
            "AXIS_SERVER_PORT",
            env_file.get("AXIS_SERVER_PORT", "15000"),
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
            "profile_settings": [0.0 for _ in range(axis_count * 4)],
            "software_position_limits": [0.0 for _ in range(axis_count * 2)],
            "motion_mode": "pp",
            "server_mode": "basic",
            "capabilities": {},
            "diagnostics": [],
            "command_authority": {
                "owner": None,
                "owned_by_this_client": False,
                "available": True,
            },
        }
        self.last_notice = ""
        self.last_diagnosis_result = ""
        self.sdo_read_results = []
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
            elif message.get("type") in {"axis/param_read", "axis/param_write"}:
                self._store_diagnosis_result(message)

    def _store_feedback(self, message):
        with self.lock:
            self.feedback = message
            for result in self.sdo_read_results:
                self._apply_param_read_result(result)

    def _store_notice(self, message):
        with self.lock:
            self.last_notice = str(message.get("message", ""))

    def _store_diagnosis_result(self, message):
        with self.lock:
            self.last_diagnosis_result = json.dumps(message, ensure_ascii=False)
            if message.get("type") == "axis/param_read" and message.get("ok"):
                self.sdo_read_results.append(dict(message))
                self._apply_param_read_result(message)

    def _apply_param_read_result(self, message):
        axis_index = int(message.get("axis", 0))
        if axis_index < 0 or axis_index >= self.axis_count:
            return

        index = int(message.get("index", 0))
        subindex = int(message.get("subindex", 0))
        value = message.get("value")
        if value is None:
            return

        if index == 0x6041 and subindex == 0:
            self._diagnostics_for_axis(axis_index)["statusword"] = int(value)
        elif index == 0x2145 and subindex == 0x0C:
            diagnostics = self._diagnostics_for_axis(axis_index)
            diagnostics["error_code"] = int(value)
            diagnostics["error_code_text"] = (
                "No error"
                if int(value) == 0
                else f"Error {int(value)}"
            )
        elif index == 0x6061 and subindex == 0:
            self._diagnostics_for_axis(axis_index)["mode_display"] = int(value)
        elif index == 0x607D and subindex in (1, 2):
            api_value = self._position_drive_to_api(axis_index, value)
            limits = self.feedback.setdefault(
                "software_position_limits",
                [0.0 for _ in range(self.axis_count * 2)],
            )
            limits[axis_index * 2 + subindex - 1] = api_value
        elif index == 0x6081 and subindex == 0:
            self._set_flat_feedback_value(
                "profile_settings",
                4,
                axis_index,
                0,
                self._motion_drive_to_api(axis_index, value, "velocity"),
            )
        elif index == 0x6083 and subindex == 0:
            self._set_flat_feedback_value(
                "profile_settings",
                4,
                axis_index,
                1,
                self._motion_drive_to_api(axis_index, value, "acceleration"),
            )
        elif index == 0x6084 and subindex == 0:
            self._set_flat_feedback_value(
                "profile_settings",
                4,
                axis_index,
                2,
                self._motion_drive_to_api(axis_index, value, "deceleration"),
            )
        elif index == 0x60A4 and subindex == 1:
            self._set_flat_feedback_value(
                "profile_settings",
                4,
                axis_index,
                3,
                self._motion_drive_to_api(axis_index, value, "jerk"),
            )
        elif index == 0x607F and subindex == 0:
            self._set_flat_feedback_value(
                "motion_limits",
                4,
                axis_index,
                0,
                self._motion_drive_to_api(axis_index, value, "velocity"),
            )
        elif index == 0x2183 and subindex == 0x0C:
            self._set_flat_feedback_value(
                "motion_limits",
                4,
                axis_index,
                1,
                self._motion_drive_to_api(axis_index, float(value) * 1000.0),
            )
        elif index == 0x60C5 and subindex == 0:
            self._set_flat_feedback_value(
                "motion_limits",
                4,
                axis_index,
                2,
                self._motion_drive_to_api(axis_index, value, "acceleration"),
            )
        elif index == 0x60C6 and subindex == 0:
            self._set_flat_feedback_value(
                "motion_limits",
                4,
                axis_index,
                3,
                self._motion_drive_to_api(axis_index, value, "deceleration"),
            )

    def _diagnostics_for_axis(self, axis_index):
        diagnostics = self.feedback.setdefault("diagnostics", [])
        while len(diagnostics) <= axis_index:
            diagnostics.append({})
        return diagnostics[axis_index]

    def _set_flat_feedback_value(self, key, fields_per_axis, axis_index, field, value):
        flat = self.feedback.setdefault(
            key,
            [0.0 for _ in range(self.axis_count * fields_per_axis)],
        )
        required = self.axis_count * fields_per_axis
        while len(flat) < required:
            flat.append(0.0)
        flat[axis_index * fields_per_axis + field] = float(value)

    def _axis_metadata(self, axis_index):
        metadata = self.feedback.setdefault(
            "axis_metadata",
            [{} for _ in range(self.axis_count)],
        )
        if axis_index < len(metadata) and isinstance(metadata[axis_index], dict):
            return metadata[axis_index]
        return {}

    def _position_drive_to_api(self, axis_index, value):
        metadata = self._axis_metadata(axis_index)
        if metadata.get("motion_kind") == "rotary":
            scale = 1_000_000.0
        else:
            scale = float(self.feedback.get("position_counts_per_unit", 1.0))
        return float(value) / max(scale, 1e-9)

    def _motion_drive_to_api(self, axis_index, value, kind="velocity"):
        metadata = self._axis_metadata(axis_index)
        key = {
            "velocity": "velocity_scale",
            "acceleration": "acceleration_scale",
            "deceleration": "deceleration_scale",
            "jerk": "jerk_scale",
        }.get(kind, "velocity_scale")
        try:
            scale = float(metadata.get(key, 1.0))
        except (TypeError, ValueError):
            scale = 1.0
        return float(value) * scale

    def get_snapshot(self):
        with self.lock:
            notice = self.last_notice
            self.last_notice = ""
            diagnosis_result = self.last_diagnosis_result
            self.last_diagnosis_result = ""
            return (
                self.connected,
                self.last_error,
                dict(self.feedback),
                notice,
                diagnosis_result,
            )

    def send_json(self, message):
        payload = (json.dumps(message) + "\n").encode("utf-8")
        with self.lock:
            if self.sock is None:
                raise ConnectionError("Axis server is not connected")
            self.sock.sendall(payload)

    def send_axis_move_absolute(self, axis_index, position, profile_velocity=None):
        message = {
            "cmd": "axis/move_abs",
            "axis": int(axis_index),
            "position": float(position),
        }
        if profile_velocity is not None:
            message["profile_velocity"] = float(profile_velocity)
        self.send_json(message)

    def send_axes_move_absolute(self, axes, positions, profile_velocities=None):
        message = {
            "cmd": "axis/move_abs",
            "axes": [int(axis_index) for axis_index in axes],
            "positions": [float(position) for position in positions],
        }
        if profile_velocities is not None:
            message["profile_velocities"] = [
                float(profile_velocity)
                for profile_velocity in profile_velocities
            ]
        self.send_json(message)

    def send_axis_move_velocity(self, axis_index, velocity):
        self.send_json(
            {
                "cmd": "axis/move_vel",
                "axis": int(axis_index),
                "velocity": float(velocity),
            }
        )

    def send_axes_move_velocity(self, axes, velocities):
        self.send_json(
            {
                "cmd": "axis/move_vel",
                "axes": [int(axis_index) for axis_index in axes],
                "velocities": [float(velocity) for velocity in velocities],
            }
        )

    def send_axis_enable(self, axis_index):
        self.send_json(
            {
                "cmd": "axis/enable",
                "axis": int(axis_index),
            }
        )

    def send_axis_disable(self, axis_index):
        self.send_json(
            {
                "cmd": "axis/disable",
                "axis": int(axis_index),
            }
        )

    def send_profile_settings(self, axis_index, profile_settings):
        message = {
            "cmd": "axis/profile",
            "axis": int(axis_index),
        }
        if len(profile_settings) == 2:
            message["profile_acceleration"] = float(profile_settings[0])
            message["profile_deceleration"] = float(profile_settings[1])
        else:
            message["profile_velocity"] = float(profile_settings[0])
            message["profile_acceleration"] = float(profile_settings[1])
            message["profile_deceleration"] = float(profile_settings[2])
            if len(profile_settings) > 3 and profile_settings[3] is not None:
                message["profile_jerk"] = float(profile_settings[3])
        self.send_json(message)

    def send_axis_motion_limits(self, axis_index, axis_limits):
        self.send_json(
            {
                "cmd": "axis/motion_limits",
                "axis": int(axis_index),
                "positive_velocity_limit": float(axis_limits[0]),
                "negative_velocity_limit": float(axis_limits[1]),
                "max_acceleration": float(axis_limits[2]),
                "max_deceleration": float(axis_limits[3]),
            }
        )

    def send_axis_software_position_limits(
        self,
        axis_index,
        negative_limit,
        positive_limit,
    ):
        self.send_json(
            {
                "cmd": "axis/software_position_limits",
                "axis": int(axis_index),
                "negative_limit": float(negative_limit),
                "positive_limit": float(positive_limit),
            }
        )

    def send_motion_mode(self, mode, axis_index):
        self.send_json(
            {
                "cmd": "axis/mode",
                "axis": int(axis_index),
                "mode": str(mode).lower(),
            }
        )

    def send_controlword(self, controlword, axis_index):
        self.send_json(
            {
                "cmd": "debug/controlword",
                "axis": int(axis_index),
                "controlword": int(controlword),
            }
        )

    def send_axis_move_relative(self, axis_index, distance, profile_velocity=None):
        message = {
            "cmd": "axis/move_rel",
            "axis": int(axis_index),
            "distance": float(distance),
        }
        if profile_velocity is not None:
            message["profile_velocity"] = float(profile_velocity)
        self.send_json(message)

    def send_jog_start(self, axis_index, direction, speed="slow"):
        self.send_json(
            {
                "cmd": "axis/jog_start",
                "axis": int(axis_index),
                "direction": str(direction),
                "speed": str(speed),
            }
        )

    def send_jog_stop(self, axis_index):
        self.send_json(
            {
                "cmd": "axis/jog_stop",
                "axis": int(axis_index),
            }
        )

    def send_axis_stop(self, axis_index):
        self.send_json(
            {
                "cmd": "axis/stop",
                "axis": int(axis_index),
            }
        )

    def send_axes_stop(self, axes):
        self.send_json(
            {
                "cmd": "axis/stop",
                "axes": [int(axis_index) for axis_index in axes],
            }
        )

    def send_homing_start(self, axis_index):
        self.send_json(
            {
                "cmd": "axis/home",
                "axis": int(axis_index),
            }
        )

    def send_axes_homing_start(self, axes):
        self.send_json(
            {
                "cmd": "axis/home",
                "axes": [int(axis_index) for axis_index in axes],
            }
        )

    def send_axis_reset(self, axis_index):
        self.send_json(
            {
                "cmd": "axis/reset",
                "axis": int(axis_index),
            }
        )

    def send_axes_reset(self, axes):
        self.send_json(
            {
                "cmd": "axis/reset",
                "axes": [int(axis_index) for axis_index in axes],
            }
        )

    def request_command_authority(self):
        self.send_json({"type": "command_authority_request"})

    def release_command_authority(self):
        self.send_json({"type": "command_authority_release"})

    def send_param_read(self, axis_index, index, subindex, data_type):
        self.send_json(
            {
                "cmd": "axis/param_read",
                "axis": int(axis_index),
                "index": str(index),
                "subindex": str(subindex),
                "data_type": str(data_type),
            }
        )

    def send_param_write(self, axis_index, index, subindex, data_type, value):
        self.send_json(
            {
                "cmd": "axis/param_write",
                "axis": int(axis_index),
                "index": str(index),
                "subindex": str(subindex),
                "data_type": str(data_type),
                "value": value,
            }
        )


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

        self._draw_legend(width, height, margin)

    def _draw_empty(self, width, height):
        self.canvas.create_text(
            width / 2,
            height / 2,
            text="Waiting for feedback",
            fill="#bdbdbd",
        )

    def _draw_legend(self, width, height, margin):
        x = margin + 8
        y = height - 14
        line_height = 15

        for index, text in enumerate(self.series_names):
            color = self.colors[(index + self.color_offset) % len(self.colors)]
            item = self.canvas.create_text(
                x,
                y,
                text=text,
                fill=color,
                anchor="w",
                font=("TkDefaultFont", 9),
            )
            bbox = self.canvas.bbox(item)
            if bbox is not None and bbox[2] > width - margin and x > margin + 8:
                self.canvas.move(item, margin + 8 - x, -line_height)
                x = margin + 8
                y -= line_height
                bbox = self.canvas.bbox(item)

            if bbox is not None and bbox[2] > width - margin:
                compact_text = self._compact_legend_text(text)
                self.canvas.itemconfigure(item, text=compact_text)
                bbox = self.canvas.bbox(item)

            if bbox is not None:
                x = bbox[2] + 18

    def _compact_legend_text(self, text):
        return (
            text.replace("Actual ", "Act ")
            .replace("Target ", "Tgt ")
            .replace("Command ", "Cmd ")
            .replace("Position", "Pos")
            .replace("Velocity", "Vel")
            .replace(" mm/s", "")
            .replace(" mm", "")
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

        self.profile_vars = [tk.StringVar(value="0.0") for _ in range(4)]
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
        self.error_code_var = tk.StringVar(value="No error")
        self.repeat_point_a_var = tk.StringVar(value="0.0")
        self.repeat_point_b_var = tk.StringVar(value="0.0")
        self.repeat_period_var = tk.StringVar(value="2.0")
        self.repeat_profile_velocity_var = tk.StringVar(value="0.0")
        self.selected_axis_var = tk.StringVar(value="0")
        self.selected_axis_label_var = tk.StringVar(value=self.axis_names[0])
        self.multi_trace_axis_vars = [
            tk.BooleanVar(value=True)
            for _ in range(self.axis_count)
        ]
        self.multi_axis_vars = [
            tk.BooleanVar(value=True)
            for _ in range(self.axis_count)
        ]
        self.multi_motion_mode_vars = [
            tk.StringVar(value="pp")
            for _ in range(self.axis_count)
        ]
        self.multi_target_position_vars = [
            tk.StringVar(value="0.0")
            for _ in range(self.axis_count)
        ]
        self.multi_profile_velocity_vars = [
            tk.StringVar(value="0.0")
            for _ in range(self.axis_count)
        ]
        self.multi_actual_position_vars = [
            tk.StringVar(value="0.0")
            for _ in range(self.axis_count)
        ]
        self.multi_repeat_point_a_vars = [
            tk.StringVar(value="0.0")
            for _ in range(self.axis_count)
        ]
        self.multi_repeat_point_b_vars = [
            tk.StringVar(value="0.0")
            for _ in range(self.axis_count)
        ]
        self.multi_repeat_profile_velocity_vars = [
            tk.StringVar(value="0.0")
            for _ in range(self.axis_count)
        ]
        self.multi_repeat_period_var = tk.StringVar(value="2.0")
        self.jog_step_var = tk.StringVar(value="100.0")
        self.connection_var = tk.StringVar(value="Disconnected")
        self.command_authority_var = tk.StringVar(value="Authority: available")
        self.command_authority_button_var = tk.StringVar(value="Request Authority")
        self.axis_enable_button_var = tk.StringVar(value="Enable")
        self.scale_var = tk.StringVar(value="CSP scale: 1.0 count/unit")
        self.diagnosis_index_var = tk.StringVar(value="0x607F")
        self.diagnosis_subindex_var = tk.StringVar(value="0x00")
        self.diagnosis_type_var = tk.StringVar(value="uint32")
        self.diagnosis_value_var = tk.StringVar(value="0")
        self.diagnosis_result_var = tk.StringVar(value="No SDO request yet.")
        self.motion_mode_var = tk.StringVar(value="pp")
        self.server_motion_mode = "pp"
        self.server_mode = "basic"
        self.server_capabilities = {}
        self.selected_axis_operation_enabled = False
        self.dirty_vars = set()
        self.statusword_lamps = []
        self.latest_target_positions = [0.0 for _ in range(self.axis_count)]
        self.latest_actual_positions = [0.0 for _ in range(self.axis_count)]
        self.latest_motion_limits = [
            [0.0, 0.0, 0.0, 0.0]
            for _ in range(self.axis_count)
        ]
        self.latest_profile_settings = [
            [0.0, 0.0, 0.0, 0.0]
            for _ in range(self.axis_count)
        ]
        self.latest_software_position_limits = [
            [0.0, 0.0]
            for _ in range(self.axis_count)
        ]
        self.latest_motion_modes = ["pp" for _ in range(self.axis_count)]
        self.latest_user_position_units = [None for _ in range(self.axis_count)]
        self.latest_converting_unit_exponents = [
            None for _ in range(self.axis_count)
        ]
        self.latest_axis_metadata = [{} for _ in range(self.axis_count)]
        self.position_counts_per_unit = 1000.0
        self.mode_frame = None
        self.pv_mode_button = None
        self.csp_mode_button = None
        self.axis_selector_notebook = None
        self.single_control_notebook = None
        self.single_axis_area = None
        self.multi_axis_area = None
        self.multi_position_trace = None
        self.multi_velocity_trace = None
        self.manual_controlword_frame = None
        self.manual_controlword_buttons = []
        self.multi_mode_widgets = []
        self.multi_command_label_widgets = []
        self.multi_profile_label_widgets = []
        self.multi_profile_entry_widgets = []
        self.multi_repeat_a_label_widgets = []
        self.multi_repeat_b_label_widgets = []
        self.multi_repeat_profile_label_widgets = []
        self.multi_repeat_profile_entry_widgets = []
        self.motion_field_labels = {}
        self.motion_entry_widgets = {}
        self.profile_label_widgets = []
        self.profile_entry_widgets = []
        self.limit_label_widgets = []
        self.software_limit_label_widgets = []
        self.repeat_label_widgets = {}
        self.diagnosis_unit_var = tk.StringVar(value="Unit: unknown")

        self.repeat_enabled = False
        self.jog_active_axis = None
        self.repeat_axis_index = 0
        self.repeat_points = None
        self.repeat_profile_velocity = 0.0
        self.repeat_index = 0
        self.repeat_wait_until = 0.0
        self.last_sent_repeat_target = None
        self.repeat_waiting_to_send = False
        self.repeat_generation = 0
        self.multi_repeat_enabled = False
        self.multi_repeat_axes = []
        self.multi_repeat_modes = []
        self.multi_repeat_points = None
        self.multi_repeat_profile_velocities = []
        self.multi_repeat_index = 0
        self.multi_repeat_wait_until = 0.0
        self.multi_repeat_last_targets = None
        self.multi_repeat_waiting_to_send = False
        self.multi_repeat_generation = 0
        self.panel_sdo_read_queue = []
        self.panel_sdo_read_next_time = 0.0
        self.panel_sdo_read_connected = False

        self._build_ui()
        self.update_mode_dependent_controls()
        self.update_selected_axis_label()
        self.selected_axis_var.trace_add(
            "write",
            lambda *_args: self.update_selected_axis_label(),
        )
        for var in self.multi_trace_axis_vars:
            var.trace_add("write", lambda *_args: self.reset_multi_traces())
        self.root.after(GUI_PERIOD_MS, self.update_gui)

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(
            header,
            text="Axis Server Control Panel",
            font=("TkDefaultFont", 12, "bold"),
        ).pack(side="left")
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

        self.axis_selector_notebook = ttk.Notebook(outer)
        self.axis_selector_notebook.pack(fill="x", pady=(0, 10))
        for axis_name in self.axis_names:
            axis_tab = ttk.Frame(self.axis_selector_notebook)
            self.axis_selector_notebook.add(axis_tab, text=axis_name)
        multi_tab = ttk.Frame(self.axis_selector_notebook)
        self.axis_selector_notebook.add(multi_tab, text="Multi Axis")
        self.axis_selector_notebook.bind(
            "<<NotebookTabChanged>>",
            self.on_axis_selector_changed,
        )

        self.single_axis_area = ttk.Frame(outer)
        self.single_axis_area.pack(fill="both", expand=True)
        self.multi_axis_area = ttk.Frame(outer)

        status_frame = ttk.LabelFrame(self.single_axis_area, text="Selected Axis Statusword")
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

        self.mode_frame = ttk.LabelFrame(self.single_axis_area, text="Motion Mode")
        self.mode_frame.pack(fill="x", pady=(0, 10))
        ttk.Radiobutton(
            self.mode_frame,
            text="PP",
            value="pp",
            variable=self.motion_mode_var,
            command=self.apply_motion_mode,
        ).pack(side="left", padx=8, pady=5)
        self.pv_mode_button = ttk.Radiobutton(
            self.mode_frame,
            text="PV",
            value="pv",
            variable=self.motion_mode_var,
            command=self.apply_motion_mode,
        )
        self.pv_mode_button.pack(side="left", padx=8, pady=5)
        self.csp_mode_button = ttk.Radiobutton(
            self.mode_frame,
            text="CSP",
            value="csp",
            variable=self.motion_mode_var,
            command=self.apply_motion_mode,
        )
        self.csp_mode_button.pack(side="left", padx=8, pady=5)
        self.single_control_notebook = ttk.Notebook(self.single_axis_area)
        self.single_control_notebook.pack(fill="x", pady=(0, 10))

        motion_tab = ttk.Frame(self.single_control_notebook, padding=6)
        settings_tab = ttk.Frame(self.single_control_notebook, padding=6)
        limits_tab = ttk.Frame(self.single_control_notebook, padding=6)
        diagnosis_tab = ttk.Frame(self.single_control_notebook, padding=6)
        self.single_control_notebook.add(motion_tab, text="Motion")
        self.single_control_notebook.add(settings_tab, text="Settings")
        self.single_control_notebook.add(limits_tab, text="Limits")
        self.single_control_notebook.add(diagnosis_tab, text="Diagnosis")
        self.single_control_notebook.bind(
            "<<NotebookTabChanged>>",
            self.on_single_control_tab_changed,
        )

        detail = ttk.LabelFrame(motion_tab, text="Selected Axis Command / Feedback")
        detail.pack(fill="x")

        fields = [
            ("Selected Axis", self.selected_axis_label_var, "label"),
            ("Target Position mm", self.command_var, "entry"),
            ("Profile Velocity mm/s", self.profile_vars[0], "entry"),
            ("Active Target Position mm", self.target_var, "label"),
            ("Actual Position mm", self.actual_position_var, "label"),
            ("Actual Velocity mm/s", self.actual_velocity_var, "label"),
            ("Command Velocity mm/s", self.command_velocity_var, "label"),
            ("Statusword", self.statusword_var, "label"),
        ]
        for index, (label, var, kind) in enumerate(fields):
            row = index // 4
            column = (index % 4) * 2
            label_widget = ttk.Label(detail, text=label)
            self.motion_field_labels[label] = label_widget
            label_widget.grid(
                row=row,
                column=column,
                padx=5,
                pady=5,
                sticky="e",
            )
            if kind.startswith("entry"):
                entry = ttk.Entry(detail, textvariable=var, justify="right", width=14)
                self.motion_entry_widgets[label] = entry
                entry.bind(
                    "<KeyRelease>",
                    lambda _event, watched_var=var: self.mark_dirty(watched_var),
                )
                self.bind_entry_focus(entry, var)
                entry.grid(row=row, column=column + 1, padx=5, pady=5, sticky="ew")
            else:
                ttk.Label(detail, textvariable=var, anchor="e", width=16).grid(
                    row=row,
                    column=column + 1,
                    padx=5,
                    pady=5,
                    sticky="ew",
                )
            detail.columnconfigure(column + 1, weight=1)

        error_row = (len(fields) + 3) // 4
        ttk.Label(detail, text="Error").grid(
            row=error_row,
            column=0,
            padx=5,
            pady=5,
            sticky="e",
        )
        ttk.Label(
            detail,
            textvariable=self.error_code_var,
            anchor="w",
            wraplength=1050,
        ).grid(
            row=error_row,
            column=1,
            columnspan=7,
            padx=5,
            pady=5,
            sticky="ew",
        )
        detail.columnconfigure(1, weight=1)

        buttons = ttk.Frame(motion_tab)
        buttons.pack(fill="x", pady=(12, 8))
        ttk.Button(
            buttons,
            textvariable=self.axis_enable_button_var,
            command=self.toggle_axis_enable,
        ).pack(
            side="left",
            padx=4,
        )
        ttk.Button(buttons, text="Run", command=self.send_command).pack(
            side="left",
            padx=4,
        )
        ttk.Button(buttons, text="Stop", command=self.axis_stop).pack(
            side="left",
            padx=4,
        )
        ttk.Button(buttons, text="Homing", command=self.homing_start).pack(
            side="left",
            padx=4,
        )
        ttk.Button(buttons, text="Alarm Ack", command=self.axis_reset).pack(
            side="left",
            padx=4,
        )
        self.manual_controlword_frame = ttk.Frame(buttons)
        self.manual_controlword_frame.pack(side="left", padx=(12, 0))
        ttk.Label(self.manual_controlword_frame, text="Manual CW").pack(
            side="left",
            padx=(0, 4),
        )
        for label, value in [
            ("Shutdown", 0x0006),
            ("Switch On", 0x0007),
            ("Enable Op", 0x000F),
            ("Disable Voltage", 0x0000),
        ]:
            button = ttk.Button(
                self.manual_controlword_frame,
                text=label,
                command=lambda cw=value: self.send_manual_controlword(cw),
            )
            button.pack(side="left", padx=2)
            self.manual_controlword_buttons.append(button)

        jog = ttk.LabelFrame(motion_tab, text="Jog")
        jog.pack(fill="x", pady=(4, 10))
        ttk.Label(jog, text="Selected Axis").pack(side="left", padx=(8, 4), pady=6)
        ttk.Label(jog, textvariable=self.selected_axis_label_var, width=8).pack(
            side="left",
            padx=4,
            pady=6,
        )
        ttk.Label(jog, text="Speed").pack(side="left", padx=(12, 4), pady=6)
        ttk.Label(jog, text="slow").pack(side="left", padx=4, pady=6)
        jog_negative = ttk.Button(
            jog,
            text="Jog -",
        )
        jog_negative.pack(side="left", padx=4, pady=6)
        jog_negative.bind(
            "<ButtonPress-1>",
            lambda _event: self.jog_start("negative"),
        )
        jog_negative.bind("<ButtonRelease-1>", lambda _event: self.jog_stop())
        jog_negative.bind("<Leave>", lambda _event: self.jog_stop())

        jog_positive = ttk.Button(
            jog,
            text="Jog +",
        )
        jog_positive.pack(side="left", padx=4, pady=6)
        jog_positive.bind(
            "<ButtonPress-1>",
            lambda _event: self.jog_start("positive"),
        )
        jog_positive.bind("<ButtonRelease-1>", lambda _event: self.jog_stop())
        jog_positive.bind("<Leave>", lambda _event: self.jog_stop())

        repeat = ttk.LabelFrame(motion_tab, text="Repeat Motion")
        repeat.pack(fill="x", pady=(4, 10))
        ttk.Label(repeat, text="Selected Axis").grid(row=0, column=0, padx=5, pady=4)
        ttk.Label(repeat, textvariable=self.selected_axis_label_var).grid(
            row=0,
            column=1,
            padx=5,
            pady=4,
            sticky="w",
        )
        self.repeat_label_widgets["point_a"] = ttk.Label(repeat, text="Point A mm")
        self.repeat_label_widgets["point_a"].grid(row=0, column=2, padx=5, pady=4)
        entry = ttk.Entry(
            repeat,
            textvariable=self.repeat_point_a_var,
            justify="right",
            width=14,
        )
        self.bind_entry_focus(entry, self.repeat_point_a_var)
        entry.grid(row=0, column=3, padx=5, pady=4)
        self.repeat_label_widgets["point_b"] = ttk.Label(repeat, text="Point B mm")
        self.repeat_label_widgets["point_b"].grid(row=0, column=4, padx=5, pady=4)
        entry = ttk.Entry(
            repeat,
            textvariable=self.repeat_point_b_var,
            justify="right",
            width=14,
        )
        self.bind_entry_focus(entry, self.repeat_point_b_var)
        entry.grid(row=0, column=5, padx=5, pady=4)
        self.repeat_label_widgets["velocity"] = ttk.Label(repeat, text="Profile Velocity mm/s")
        self.repeat_label_widgets["velocity"].grid(
            row=0,
            column=6,
            padx=5,
            pady=4,
        )
        entry = ttk.Entry(
            repeat,
            textvariable=self.repeat_profile_velocity_var,
            justify="right",
            width=14,
        )
        self.bind_entry_focus(entry, self.repeat_profile_velocity_var)
        entry.grid(row=0, column=7, padx=5, pady=4)
        ttk.Label(repeat, text="Period (s)").grid(row=0, column=8, padx=5, pady=4)
        entry = ttk.Entry(
            repeat,
            textvariable=self.repeat_period_var,
            justify="right",
            width=10,
        )
        self.bind_entry_focus(entry, self.repeat_period_var)
        entry.grid(row=0, column=9, padx=5, pady=4)
        ttk.Button(repeat, text="Start Repeat", command=self.start_repeat).grid(
            row=0,
            column=10,
            padx=5,
            pady=4,
        )
        ttk.Button(repeat, text="Stop Repeat", command=self.stop_repeat).grid(
            row=0,
            column=11,
            padx=5,
            pady=4,
        )

        profile_frame = ttk.LabelFrame(settings_tab, text="Selected Axis PP Profile")
        profile_frame.pack(fill="x", pady=(0, 10))
        profile_fields = [
            ("Profile Velocity mm/s", self.profile_vars[0]),
            ("Profile Accel mm/s^2", self.profile_vars[1]),
            ("Profile Decel mm/s^2", self.profile_vars[2]),
            ("Profile Jerk mm/s^3", self.profile_vars[3]),
        ]
        for index, (label, var) in enumerate(profile_fields):
            label_widget = ttk.Label(profile_frame, text=label)
            self.profile_label_widgets.append(label_widget)
            label_widget.grid(
                row=0,
                column=index * 2,
                padx=5,
                pady=5,
                sticky="e",
            )
            entry = ttk.Entry(profile_frame, textvariable=var, justify="right", width=14)
            entry.bind(
                "<KeyRelease>",
                lambda _event, watched_var=var: self.mark_dirty(watched_var),
            )
            self.bind_entry_focus(entry, var)
            entry.grid(row=0, column=index * 2 + 1, padx=5, pady=5, sticky="ew")
            self.profile_entry_widgets.append(entry)
            profile_frame.columnconfigure(index * 2 + 1, weight=1)

        settings_buttons = ttk.Frame(settings_tab)
        settings_buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(
            settings_buttons,
            text="Apply PP Profile",
            command=self.apply_profile_settings,
        ).pack(side="left", padx=4)

        limit_frame = ttk.LabelFrame(limits_tab, text="Selected Axis Motion Limits")
        limit_frame.pack(fill="x", pady=(0, 10))
        limit_fields = [
            ("Max Profile Velocity (+) mm/s", self.limit_vars[0]),
            ("Max Profile Velocity (-) mm/s", self.limit_vars[1]),
            ("Max Accel mm/s^2", self.limit_vars[2]),
            ("Max Decel mm/s^2", self.limit_vars[3]),
        ]
        for index, (label, var) in enumerate(limit_fields):
            label_widget = ttk.Label(limit_frame, text=label)
            self.limit_label_widgets.append(label_widget)
            label_widget.grid(
                row=0,
                column=index * 2,
                padx=5,
                pady=5,
                sticky="e",
            )
            entry = ttk.Entry(limit_frame, textvariable=var, justify="right", width=14)
            entry.bind(
                "<KeyRelease>",
                lambda _event, watched_var=var: self.mark_dirty(watched_var),
            )
            self.bind_entry_focus(entry, var)
            entry.grid(row=0, column=index * 2 + 1, padx=5, pady=5, sticky="ew")
            limit_frame.columnconfigure(index * 2 + 1, weight=1)

        sw_limit_frame = ttk.LabelFrame(limits_tab, text="Selected Axis Software Position Limits")
        sw_limit_frame.pack(fill="x", pady=(0, 10))
        sw_limit_fields = [
            ("Negative SW Limit mm", self.software_limit_vars[0]),
            ("Positive SW Limit mm", self.software_limit_vars[1]),
        ]
        for index, (label, var) in enumerate(sw_limit_fields):
            label_widget = ttk.Label(sw_limit_frame, text=label)
            self.software_limit_label_widgets.append(label_widget)
            label_widget.grid(
                row=0,
                column=index * 2,
                padx=5,
                pady=5,
                sticky="e",
            )
            entry = ttk.Entry(sw_limit_frame, textvariable=var, justify="right", width=14)
            entry.bind(
                "<KeyRelease>",
                lambda _event, watched_var=var: self.mark_dirty(watched_var),
            )
            self.bind_entry_focus(entry, var)
            entry.grid(row=0, column=index * 2 + 1, padx=5, pady=5, sticky="ew")
            sw_limit_frame.columnconfigure(index * 2 + 1, weight=1)

        limit_buttons = ttk.Frame(limits_tab)
        limit_buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(
            limit_buttons,
            text="Apply Motion Limits",
            command=self.apply_motion_limits,
        ).pack(
            side="left",
            padx=4,
        )
        ttk.Button(
            limit_buttons,
            text="Apply SW Limits",
            command=self.apply_software_limits,
        ).pack(
            side="left",
            padx=4,
        )

        diagnosis_frame = ttk.LabelFrame(diagnosis_tab, text="Selected Axis SDO")
        diagnosis_frame.pack(fill="x", pady=(0, 10))
        diagnosis_fields = [
            ("Index", self.diagnosis_index_var, "entry"),
            ("Subindex", self.diagnosis_subindex_var, "entry"),
            ("Type", self.diagnosis_type_var, "combo"),
            ("Value", self.diagnosis_value_var, "entry"),
        ]
        for index, (label, var, kind) in enumerate(diagnosis_fields):
            ttk.Label(diagnosis_frame, text=label).grid(
                row=0,
                column=index * 2,
                padx=5,
                pady=5,
                sticky="e",
            )
            if kind == "combo":
                widget = ttk.Combobox(
                    diagnosis_frame,
                    textvariable=var,
                    values=[
                        "uint8",
                        "int8",
                        "uint16",
                        "int32",
                        "uint32",
                        "udint",
                        "float32",
                    ],
                    width=12,
                    state="readonly",
                )
            else:
                widget = ttk.Entry(
                    diagnosis_frame,
                    textvariable=var,
                    justify="right",
                    width=14,
                )
                self.bind_entry_focus(widget, var)
            widget.grid(
                row=0,
                column=index * 2 + 1,
                padx=5,
                pady=5,
                sticky="ew",
            )
            diagnosis_frame.columnconfigure(index * 2 + 1, weight=1)

        diagnosis_buttons = ttk.Frame(diagnosis_tab)
        diagnosis_buttons.pack(fill="x", pady=(4, 8))
        ttk.Button(
            diagnosis_buttons,
            text="Read",
            command=self.diagnosis_read,
        ).pack(side="left", padx=4)
        ttk.Button(
            diagnosis_buttons,
            text="Write",
            command=self.diagnosis_write,
        ).pack(side="left", padx=4)
        ttk.Label(
            diagnosis_buttons,
            textvariable=self.diagnosis_unit_var,
        ).pack(side="right", padx=4)

        diagnosis_result = ttk.LabelFrame(diagnosis_tab, text="Result")
        diagnosis_result.pack(fill="both", expand=True)
        ttk.Label(
            diagnosis_result,
            textvariable=self.diagnosis_result_var,
            anchor="nw",
            justify="left",
            wraplength=1080,
        ).pack(fill="both", expand=True, padx=6, pady=6)

        traces = ttk.Frame(self.single_axis_area)
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
        self._build_multi_axis_ui(self.multi_axis_area)

    def _build_multi_axis_ui(self, parent):
        command_frame = ttk.LabelFrame(parent, text="Multi Axis Position Command")
        command_frame.pack(fill="x", pady=(0, 10))

        headings = [
            "Use",
            "Axis",
            "Mode",
            "Command",
            "Value",
            "Profile Velocity",
            "Value",
            "Actual Position",
        ]
        for column, text in enumerate(headings):
            ttk.Label(command_frame, text=text).grid(
                row=0,
                column=column,
                padx=5,
                pady=5,
                sticky="ew",
            )
            command_frame.columnconfigure(column, weight=1 if column in (4, 6, 7) else 0)

        for axis_index, axis_name in enumerate(self.axis_names):
            row = axis_index + 1
            ttk.Checkbutton(
                command_frame,
                variable=self.multi_axis_vars[axis_index],
            ).grid(row=row, column=0, padx=5, pady=4)
            ttk.Label(command_frame, text=axis_name).grid(
                row=row,
                column=1,
                padx=5,
                pady=4,
                sticky="w",
            )
            mode_combo = ttk.Combobox(
                command_frame,
                textvariable=self.multi_motion_mode_vars[axis_index],
                values=self.motion_mode_options(axis_index),
                state="readonly",
                width=5,
            )
            mode_combo.bind(
                "<<ComboboxSelected>>",
                lambda _event, axis=axis_index: self.on_multi_motion_mode_changed(axis),
            )
            mode_combo.grid(row=row, column=2, padx=5, pady=4, sticky="ew")
            self.multi_mode_widgets.append(mode_combo)

            command_label = ttk.Label(command_frame, text="Target Position")
            command_label.grid(row=row, column=3, padx=5, pady=4, sticky="e")
            self.multi_command_label_widgets.append(command_label)
            target_entry = ttk.Entry(
                command_frame,
                textvariable=self.multi_target_position_vars[axis_index],
                justify="right",
                width=16,
            )
            target_entry.bind(
                "<KeyRelease>",
                lambda _event, watched_var=self.multi_target_position_vars[axis_index]: (
                    self.mark_dirty(watched_var)
                ),
            )
            self.bind_entry_focus(
                target_entry,
                self.multi_target_position_vars[axis_index],
            )
            target_entry.grid(row=row, column=4, padx=5, pady=4, sticky="ew")

            profile_label = ttk.Label(command_frame, text="Profile Velocity")
            profile_label.grid(row=row, column=5, padx=5, pady=4, sticky="e")
            self.multi_profile_label_widgets.append(profile_label)
            velocity_entry = ttk.Entry(
                command_frame,
                textvariable=self.multi_profile_velocity_vars[axis_index],
                justify="right",
                width=16,
            )
            velocity_entry.bind(
                "<KeyRelease>",
                lambda _event, watched_var=self.multi_profile_velocity_vars[axis_index]: (
                    self.mark_dirty(watched_var)
                ),
            )
            self.bind_entry_focus(
                velocity_entry,
                self.multi_profile_velocity_vars[axis_index],
            )
            velocity_entry.grid(row=row, column=6, padx=5, pady=4, sticky="ew")
            self.multi_profile_entry_widgets.append(velocity_entry)

            ttk.Label(
                command_frame,
                textvariable=self.multi_actual_position_vars[axis_index],
                anchor="e",
                width=16,
            ).grid(row=row, column=7, padx=5, pady=4, sticky="ew")

        buttons = ttk.Frame(parent)
        buttons.pack(fill="x", pady=(0, 10))
        ttk.Button(buttons, text="Run", command=self.multi_axis_run).pack(
            side="left",
            padx=4,
        )
        ttk.Button(buttons, text="Stop", command=self.multi_axis_stop).pack(
            side="left",
            padx=4,
        )
        ttk.Button(buttons, text="Homing", command=self.multi_axis_homing).pack(
            side="left",
            padx=4,
        )
        ttk.Button(buttons, text="Alarm Ack", command=self.multi_axis_reset).pack(
            side="left",
            padx=4,
        )

        repeat_frame = ttk.LabelFrame(parent, text="Multi Axis Repeat Motion")
        repeat_frame.pack(fill="x", pady=(0, 10))
        repeat_headings = [
            "Use",
            "Axis",
            "Mode",
            "A",
            "Value",
            "B",
            "Value",
            "Profile Velocity",
            "Value",
        ]
        for column, text in enumerate(repeat_headings):
            ttk.Label(repeat_frame, text=text).grid(
                row=0,
                column=column,
                padx=5,
                pady=5,
                sticky="ew",
            )
            repeat_frame.columnconfigure(column, weight=1 if column in (4, 6, 8) else 0)

        for axis_index, axis_name in enumerate(self.axis_names):
            row = axis_index + 1
            ttk.Checkbutton(
                repeat_frame,
                variable=self.multi_axis_vars[axis_index],
            ).grid(row=row, column=0, padx=5, pady=4)
            ttk.Label(repeat_frame, text=axis_name).grid(
                row=row,
                column=1,
                padx=5,
                pady=4,
                sticky="w",
            )
            repeat_mode_combo = ttk.Combobox(
                repeat_frame,
                textvariable=self.multi_motion_mode_vars[axis_index],
                values=self.motion_mode_options(axis_index),
                state="readonly",
                width=5,
            )
            repeat_mode_combo.bind(
                "<<ComboboxSelected>>",
                lambda _event, axis=axis_index: self.on_multi_motion_mode_changed(axis),
            )
            repeat_mode_combo.grid(row=row, column=2, padx=5, pady=4, sticky="ew")
            self.multi_mode_widgets.append(repeat_mode_combo)

            a_label = ttk.Label(repeat_frame, text="Point A")
            a_label.grid(row=row, column=3, padx=5, pady=4, sticky="e")
            self.multi_repeat_a_label_widgets.append(a_label)
            b_label = ttk.Label(repeat_frame, text="Point B")
            b_label.grid(row=row, column=5, padx=5, pady=4, sticky="e")
            self.multi_repeat_b_label_widgets.append(b_label)
            profile_label = ttk.Label(repeat_frame, text="Profile Velocity")
            profile_label.grid(row=row, column=7, padx=5, pady=4, sticky="e")
            self.multi_repeat_profile_label_widgets.append(profile_label)

            for column, var in [
                (4, self.multi_repeat_point_a_vars[axis_index]),
                (6, self.multi_repeat_point_b_vars[axis_index]),
                (8, self.multi_repeat_profile_velocity_vars[axis_index]),
            ]:
                entry = ttk.Entry(
                    repeat_frame,
                    textvariable=var,
                    justify="right",
                    width=16,
                )
                entry.bind(
                    "<KeyRelease>",
                    lambda _event, watched_var=var: self.mark_dirty(watched_var),
                )
                self.bind_entry_focus(entry, var)
                entry.grid(row=row, column=column, padx=5, pady=4, sticky="ew")
                if column == 8:
                    self.multi_repeat_profile_entry_widgets.append(entry)

        repeat_controls = ttk.Frame(parent)
        repeat_controls.pack(fill="x", pady=(0, 10))
        ttk.Label(repeat_controls, text="Period (s)").pack(
            side="left",
            padx=(4, 5),
        )
        entry = ttk.Entry(
            repeat_controls,
            textvariable=self.multi_repeat_period_var,
            justify="right",
            width=10,
        )
        self.bind_entry_focus(entry, self.multi_repeat_period_var)
        entry.pack(side="left", padx=4)
        ttk.Button(
            repeat_controls,
            text="Start Repeat",
            command=self.start_multi_repeat,
        ).pack(side="left", padx=(12, 4))
        ttk.Button(
            repeat_controls,
            text="Stop Repeat",
            command=self.stop_multi_repeat_motion,
        ).pack(side="left", padx=4)

        trace_controls = ttk.Frame(parent)
        trace_controls.pack(fill="x", pady=(0, 4))
        ttk.Label(trace_controls, text="Trace Axes").pack(
            side="left",
            padx=(4, 5),
        )
        for axis_index, axis_name in enumerate(self.axis_names):
            ttk.Checkbutton(
                trace_controls,
                text=axis_name,
                variable=self.multi_trace_axis_vars[axis_index],
            ).pack(side="left", padx=4)

        traces = ttk.Frame(parent)
        traces.pack(fill="both", expand=True)
        self.multi_position_trace = TraceCanvas(
            traces,
            ["Actual Position mm"],
            "Position",
        )
        self.multi_velocity_trace = TraceCanvas(
            traces,
            ["Actual Velocity mm/s"],
            "Velocity",
            2,
        )

    def on_axis_selector_changed(self, _event=None):
        if self.axis_selector_notebook is None:
            return

        self.stop_tab_motion()
        selected_tab = self.axis_selector_notebook.index("current")
        if selected_tab < self.axis_count:
            self.selected_axis_var.set(str(selected_tab))
            self.show_single_axis_area()
        else:
            self.show_multi_axis_area()

    def on_single_control_tab_changed(self, _event=None):
        if self.single_control_notebook is None:
            return
        if self.single_control_notebook.index("current") != 0:
            self.stop_repeat()
            self.stop_jog()
            self.stop_selected_pv_axis()

    def stop_tab_motion(self):
        self.stop_repeat()
        self.stop_multi_repeat()
        self.stop_jog()
        self.stop_selected_pv_axis()

    def stop_selected_pv_axis(self):
        axis_index = self.selected_axis()
        if axis_index < 0 or axis_index >= self.axis_count:
            return
        if axis_index >= len(self.latest_motion_modes):
            return
        if self.latest_motion_modes[axis_index] != "pv":
            return
        self.try_send(lambda: self.client.send_axis_stop(axis_index))

    def show_single_axis_area(self):
        if self.multi_axis_area is not None and self.multi_axis_area.winfo_ismapped():
            self.multi_axis_area.pack_forget()
        if self.single_axis_area is not None and not self.single_axis_area.winfo_ismapped():
            self.single_axis_area.pack(fill="both", expand=True)

    def show_multi_axis_area(self):
        if self.single_axis_area is not None and self.single_axis_area.winfo_ismapped():
            self.single_axis_area.pack_forget()
        if self.multi_axis_area is not None and not self.multi_axis_area.winfo_ismapped():
            self.multi_axis_area.pack(fill="both", expand=True)

    def mark_dirty(self, var):
        self.dirty_vars.add(id(var))

    def bind_entry_focus(self, entry, var):
        entry.bind("<Button-1>", lambda _event: entry.focus_set(), add="+")
        entry.bind("<FocusIn>", lambda _event: self.mark_dirty(var), add="+")
        entry.bind("<KeyPress>", lambda _event: self.mark_dirty(var), add="+")
        entry.bind("<KeyRelease>", lambda _event: self.mark_dirty(var), add="+")

    def apply_profile_settings(self):
        profile_settings = self.read_selected_profile_values()
        if profile_settings is None:
            return
        axis_index = self.selected_axis()
        if self.try_send(
            lambda: self.client.send_profile_settings(axis_index, profile_settings)
        ):
            reads = [
                (axis_index, "0x6083", "0x00", "uint32"),
                (axis_index, "0x6084", "0x00", "uint32"),
            ]
            if self.latest_motion_modes[axis_index] != "pv":
                reads.insert(0, (axis_index, "0x6081", "0x00", "uint32"))
                reads.append((axis_index, "0x60A4", "0x01", "uint32"))
            self.queue_panel_sdo_reads(reads)
        if self.latest_motion_modes[axis_index] == "pv":
            dirty_vars = self.profile_vars[1:3]
        else:
            dirty_vars = self.profile_vars[:len(profile_settings)]
        for var in dirty_vars:
            self.dirty_vars.discard(id(var))

    def apply_motion_limits(self):
        axis_limits = self.read_selected_limit_values()
        if axis_limits is None:
            return
        axis_index = self.selected_axis()
        if self.try_send(
            lambda: self.client.send_axis_motion_limits(axis_index, axis_limits)
        ):
            self.queue_panel_sdo_reads([
                (axis_index, "0x607F", "0x00", "uint32"),
                (axis_index, "0x2183", "0x0C", "float32"),
                (axis_index, "0x60C5", "0x00", "uint32"),
                (axis_index, "0x60C6", "0x00", "uint32"),
            ])
        for var in self.limit_vars:
            self.dirty_vars.discard(id(var))

    def apply_software_limits(self):
        software_limits_mm = self.read_selected_software_limit_values()
        if software_limits_mm is None:
            return

        axis_index = self.selected_axis()
        if self.try_send(
            lambda: self.client.send_axis_software_position_limits(
                axis_index,
                software_limits_mm[0],
                software_limits_mm[1],
            )
        ):
            self.queue_panel_sdo_reads([
                (axis_index, "0x607D", "0x01", "int32"),
                (axis_index, "0x607D", "0x02", "int32"),
            ])
        for var in self.software_limit_vars:
            self.dirty_vars.discard(id(var))

    def send_command(self):
        axis_index = self.selected_axis()
        command_value = self.read_selected_command_value()
        if command_value is None:
            return
        if self.latest_motion_modes[axis_index] == "pv":
            self.try_send(
                lambda: self.client.send_axis_move_velocity(axis_index, command_value)
            )
            return
        profile_velocity = self.read_selected_motion_profile_velocity()
        if profile_velocity is None:
            return
        self.try_send(
            lambda: self.client.send_axis_move_absolute(
                axis_index,
                command_value,
                profile_velocity,
            )
        )
        self.dirty_vars.discard(id(self.profile_vars[0]))

    def multi_axis_run(self):
        self.stop_multi_repeat()
        command = self.read_multi_axis_command()
        if command is None:
            return
        axes, modes, values, profile_velocities = command
        if self.try_send(lambda: self.send_multi_axis_command(
            axes,
            modes,
            values,
            profile_velocities,
        )):
            for axis_index in axes:
                self.dirty_vars.discard(id(self.multi_target_position_vars[axis_index]))
                self.dirty_vars.discard(id(self.multi_profile_velocity_vars[axis_index]))

    def send_multi_axis_command(self, axes, modes, values, profile_velocities=None):
        for axis_index, mode in zip(axes, modes):
            self.client.send_motion_mode(mode, axis_index)

        position_axes = []
        positions = []
        position_profile_velocities = []
        velocity_axes = []
        velocities = []
        for local_index, axis_index in enumerate(axes):
            mode = modes[local_index]
            if mode == "pv":
                velocity_axes.append(axis_index)
                velocities.append(values[local_index])
            else:
                position_axes.append(axis_index)
                positions.append(values[local_index])
                if profile_velocities is not None:
                    position_profile_velocities.append(profile_velocities[local_index])

        if position_axes:
            self.client.send_axes_move_absolute(
                position_axes,
                positions,
                position_profile_velocities if profile_velocities is not None else None,
            )
        if velocity_axes:
            self.client.send_axes_move_velocity(velocity_axes, velocities)

    def multi_axis_stop(self):
        self.stop_repeat()
        self.stop_multi_repeat()
        axes = self.selected_multi_axes()
        if axes is not None:
            self.try_send(lambda: self.client.send_axes_stop(axes))

    def multi_axis_homing(self):
        self.stop_repeat()
        self.stop_multi_repeat()
        axes = self.selected_multi_axes()
        if axes is not None:
            self.try_send(lambda: self.client.send_axes_homing_start(axes))

    def multi_axis_reset(self):
        self.stop_multi_repeat()
        axes = self.selected_multi_axes()
        if axes is not None:
            self.try_send(lambda: self.client.send_axes_reset(axes))

    def axis_reset(self):
        axis_index = self.selected_axis()
        self.try_send(lambda: self.client.send_axis_reset(axis_index))

    def diagnosis_read(self):
        request = self.read_diagnosis_request(include_value=False)
        if request is None:
            return
        axis_index, index, subindex, data_type, _value = request
        self.diagnosis_result_var.set("Waiting for SDO read response...")
        self.try_send(
            lambda: self.client.send_param_read(
                axis_index,
                index,
                subindex,
                data_type,
            )
        )

    def diagnosis_write(self):
        request = self.read_diagnosis_request(include_value=True)
        if request is None:
            return
        axis_index, index, subindex, data_type, value = request
        self.diagnosis_result_var.set("Waiting for SDO write response...")
        if self.try_send(
            lambda: self.client.send_param_write(
                axis_index,
                index,
                subindex,
                data_type,
                value,
            )
        ):
            self.queue_panel_sdo_reads([
                (axis_index, index, subindex, data_type),
            ])

    def axis_stop(self):
        self.stop_repeat()
        axis_index = self.selected_axis()
        self.try_send(lambda: self.client.send_axis_stop(axis_index))

    def homing_start(self):
        self.stop_repeat()
        axis_index = self.selected_axis()
        self.try_send(lambda: self.client.send_homing_start(axis_index))

    def toggle_command_authority(self):
        _, _, feedback, _, _ = self.client.get_snapshot()
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

    def reset_multi_traces(self):
        if self.multi_position_trace is not None:
            self.multi_position_trace.history = [
                []
                for _ in self.multi_position_trace.series_names
            ]
        if self.multi_velocity_trace is not None:
            self.multi_velocity_trace.history = [
                []
                for _ in self.multi_velocity_trace.series_names
            ]

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

    def update_axis_enable_button(self, statusword):
        self.selected_axis_operation_enabled = bool(int(statusword) & 0x0004)
        self.axis_enable_button_var.set(
            "Disable" if self.selected_axis_operation_enabled else "Enable"
        )

    def axis_user_position_unit(self, axis_index):
        metadata = self.axis_metadata(axis_index)
        value = metadata.get("user_position_unit")
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        return None

    def axis_metadata(self, axis_index):
        if axis_index < len(self.latest_axis_metadata):
            metadata = self.latest_axis_metadata[axis_index]
            if isinstance(metadata, dict):
                return metadata
        return {}

    def axis_unit_labels(self, axis_index):
        metadata = self.axis_metadata(axis_index)
        position_unit = metadata.get("position_unit", "mm")
        velocity_unit = metadata.get("velocity_unit", f"{position_unit}/s")
        acceleration_unit = metadata.get("acceleration_unit", f"{position_unit}/s^2")
        jerk_unit = metadata.get("jerk_unit", f"{position_unit}/s^3")
        return position_unit, velocity_unit, acceleration_unit, jerk_unit

    def axis_unit_scale(self, axis_index):
        metadata = self.axis_metadata(axis_index)
        if metadata.get("motion_kind") == "rotary":
            return 1_000_000.0
        return self.position_counts_per_unit

    def axis_motion_scale(self, axis_index, kind="velocity"):
        metadata = self.axis_metadata(axis_index)
        key = {
            "velocity": "velocity_scale",
            "acceleration": "acceleration_scale",
            "deceleration": "deceleration_scale",
            "jerk": "jerk_scale",
        }.get(kind, "velocity_scale")
        try:
            return float(metadata.get(key, 1.0))
        except (TypeError, ValueError):
            return 1.0

    def axis_pv_allowed(self, axis_index):
        return bool(self.axis_metadata(axis_index).get("pv_allowed", False))

    def motion_mode_options(self, axis_index):
        options = ["pp"]
        if self.axis_pv_allowed(axis_index):
            options.append("pv")
        if self.server_mode == "advanced":
            options.append("csp")
        return options

    def on_multi_motion_mode_changed(self, axis_index):
        mode = self.multi_motion_mode_vars[axis_index].get()
        if mode == "pv" and not self.axis_pv_allowed(axis_index):
            self.multi_motion_mode_vars[axis_index].set(self.latest_motion_modes[axis_index])
            messagebox.showinfo(
                "PV Not Available",
                "PV mode is available only for rad, degree, or revolution axes.",
            )
            return
        if mode == "csp" and self.server_mode != "advanced":
            self.multi_motion_mode_vars[axis_index].set(self.latest_motion_modes[axis_index])
            return
        self.update_multi_axis_mode_controls()
        self.try_send(lambda: self.client.send_motion_mode(mode, axis_index))

    def update_multi_axis_mode_controls(self):
        if (
            len(self.multi_command_label_widgets) < self.axis_count
            or len(self.multi_profile_label_widgets) < self.axis_count
            or len(self.multi_profile_entry_widgets) < self.axis_count
            or len(self.multi_repeat_a_label_widgets) < self.axis_count
            or len(self.multi_repeat_b_label_widgets) < self.axis_count
            or len(self.multi_repeat_profile_label_widgets) < self.axis_count
            or len(self.multi_repeat_profile_entry_widgets) < self.axis_count
        ):
            return

        for axis_index in range(self.axis_count):
            mode = self.multi_motion_mode_vars[axis_index].get()
            pos_unit, vel_unit, _accel_unit, _jerk_unit = self.axis_unit_labels(axis_index)
            options = self.motion_mode_options(axis_index)
            for widget_index in (axis_index, self.axis_count + axis_index):
                if widget_index < len(self.multi_mode_widgets):
                    self.multi_mode_widgets[widget_index].configure(values=options)
            command_label = self.multi_command_label_widgets[axis_index]
            profile_label = self.multi_profile_label_widgets[axis_index]
            profile_entry = self.multi_profile_entry_widgets[axis_index]
            repeat_a_label = self.multi_repeat_a_label_widgets[axis_index]
            repeat_b_label = self.multi_repeat_b_label_widgets[axis_index]
            repeat_profile_label = self.multi_repeat_profile_label_widgets[axis_index]
            repeat_profile_entry = self.multi_repeat_profile_entry_widgets[axis_index]

            if mode == "pv":
                command_label.configure(text=f"Target Velocity {vel_unit}")
                profile_label.configure(text="Profile Velocity")
                profile_label.configure(state="disabled")
                profile_entry.configure(state="disabled")
                repeat_a_label.configure(text=f"Velocity A {vel_unit}")
                repeat_b_label.configure(text=f"Velocity B {vel_unit}")
                repeat_profile_label.configure(state="disabled")
                repeat_profile_entry.configure(state="disabled")
            else:
                command_label.configure(text=f"Target Position {pos_unit}")
                profile_label.configure(text=f"Profile Velocity {vel_unit}")
                profile_label.configure(state="normal")
                profile_entry.configure(state="normal")
                repeat_a_label.configure(text=f"Point A {pos_unit}")
                repeat_b_label.configure(text=f"Point B {pos_unit}")
                repeat_profile_label.configure(text=f"Profile Velocity {vel_unit}")
                repeat_profile_label.configure(state="normal")
                repeat_profile_entry.configure(state="normal")

    def update_unit_labels(self, axis_index, motion_mode):
        pos_unit, vel_unit, accel_unit, jerk_unit = self.axis_unit_labels(axis_index)
        command_label = (
            f"Target Velocity {vel_unit}"
            if motion_mode == "pv"
            else f"Target Position {pos_unit}"
        )
        label_updates = {
            "Target Position mm": command_label,
            "Profile Velocity mm/s": f"Profile Velocity {vel_unit}",
            "Active Target Position mm": f"Active Target Position {pos_unit}",
            "Actual Position mm": f"Actual Position {pos_unit}",
            "Actual Velocity mm/s": f"Actual Velocity {vel_unit}",
            "Command Velocity mm/s": f"Command Velocity {vel_unit}",
        }
        for original, text in label_updates.items():
            widget = self.motion_field_labels.get(original)
            if widget is not None:
                widget.configure(text=text)

        profile_labels = [
            f"Profile Velocity {vel_unit}",
            f"Profile Accel {accel_unit}",
            f"Profile Decel {accel_unit}",
            f"Profile Jerk {jerk_unit}",
        ]
        for widget, text in zip(self.profile_label_widgets, profile_labels):
            widget.configure(text=text)
        self.update_profile_field_states(motion_mode)

        limit_labels = [
            f"Max Profile Velocity (+) {vel_unit}",
            f"Max Profile Velocity (-) {vel_unit}",
            f"Max Accel {accel_unit}",
            f"Max Decel {accel_unit}",
        ]
        for widget, text in zip(self.limit_label_widgets, limit_labels):
            widget.configure(text=text)

        sw_limit_labels = [
            f"Negative SW Limit {pos_unit}",
            f"Positive SW Limit {pos_unit}",
        ]
        for widget, text in zip(self.software_limit_label_widgets, sw_limit_labels):
            widget.configure(text=text)

        repeat_updates = {
            "point_a": f"Point A {pos_unit}",
            "point_b": f"Point B {pos_unit}",
            "velocity": f"Profile Velocity {vel_unit}",
        }
        for key, text in repeat_updates.items():
            widget = self.repeat_label_widgets.get(key)
            if widget is not None:
                widget.configure(text=text)

        user_unit = self.axis_user_position_unit(axis_index)
        unit_text = f"0x{user_unit:04X}" if user_unit is not None else "unknown"
        self.diagnosis_unit_var.set(f"Unit: {pos_unit} ({unit_text})")

    def update_profile_field_states(self, motion_mode):
        if len(self.profile_label_widgets) < 4 or len(self.profile_entry_widgets) < 4:
            return
        velocity_widgets = (
            self.profile_label_widgets[0],
            self.profile_entry_widgets[0],
        )
        motion_velocity_widgets = [
            widget
            for widget in (
                self.motion_field_labels.get("Profile Velocity mm/s"),
                self.motion_entry_widgets.get("Profile Velocity mm/s"),
            )
            if widget is not None
        ]
        jerk_widgets = (
            self.profile_label_widgets[3],
            self.profile_entry_widgets[3],
        )
        if motion_mode == "pv":
            for widget in velocity_widgets:
                widget.configure(state="disabled")
            for widget in motion_velocity_widgets:
                widget.configure(state="disabled")
            for widget in jerk_widgets:
                widget.grid_remove()
            self.dirty_vars.discard(id(self.profile_vars[0]))
            self.dirty_vars.discard(id(self.profile_vars[3]))
        else:
            for widget in velocity_widgets:
                widget.configure(state="normal")
            for widget in motion_velocity_widgets:
                widget.configure(state="normal")
            for widget in jerk_widgets:
                widget.grid()

    def selected_axis(self):
        return int(self.selected_axis_var.get())

    def selected_multi_trace_axes(self):
        axes = [
            axis_index
            for axis_index, var in enumerate(self.multi_trace_axis_vars)
            if var.get()
        ]
        return axes or [0]

    def multi_trace_series_names(self, axes, value_name):
        names = []
        for axis_index in axes:
            pos_unit, vel_unit, _accel_unit, _jerk_unit = self.axis_unit_labels(axis_index)
            unit = vel_unit if "Velocity" in value_name else pos_unit
            names.append(f"{self.axis_names[axis_index]} {value_name} {unit}")
        return names

    def send_manual_controlword(self, controlword):
        axis_index = self.selected_axis()
        self.try_send(lambda: self.client.send_controlword(controlword, axis_index))

    def toggle_axis_enable(self):
        axis_index = self.selected_axis()
        if self.selected_axis_operation_enabled:
            self.try_send(lambda: self.client.send_axis_disable(axis_index))
        else:
            self.try_send(lambda: self.client.send_axis_enable(axis_index))

    def jog_start(self, direction):
        axis_index = self.selected_axis()
        self.jog_active_axis = axis_index
        self.try_send(lambda: self.client.send_jog_start(axis_index, direction))

    def jog_stop(self):
        if self.jog_active_axis is None:
            return
        axis_index = self.jog_active_axis
        self.jog_active_axis = None
        self.try_send(lambda: self.client.send_jog_stop(axis_index))

    def stop_jog(self):
        self.jog_stop()

    def apply_motion_mode(self):
        mode = self.motion_mode_var.get()
        axis_index = self.selected_axis()
        if mode == "pv" and not self.axis_pv_allowed(axis_index):
            messagebox.showinfo(
                "PV Not Available",
                "PV mode is available only for rad, degree, or revolution axes.",
            )
            self.motion_mode_var.set(self.latest_motion_modes[axis_index])
            return
        self.try_send(lambda: self.client.send_motion_mode(mode, axis_index))

    def start_repeat(self):
        self.stop_multi_repeat()
        repeat_config = self.read_repeat_values()
        if repeat_config is None:
            return
        self.repeat_generation += 1
        point_a, point_b, profile_velocity, period = repeat_config
        self.repeat_enabled = True
        self.repeat_axis_index = self.selected_axis()
        self.repeat_points = [point_a, point_b]
        self.repeat_profile_velocity = profile_velocity
        self.repeat_period = period
        self.repeat_index = 0
        self.repeat_wait_until = 0.0
        self.last_sent_repeat_target = None
        self.repeat_waiting_to_send = False

    def stop_repeat(self):
        self.repeat_generation += 1
        self.repeat_enabled = False
        self.last_sent_repeat_target = None
        self.repeat_waiting_to_send = False

    def start_multi_repeat(self):
        self.stop_repeat()
        repeat_config = self.read_multi_repeat_values()
        if repeat_config is None:
            return
        self.multi_repeat_generation += 1
        axes, modes, point_a, point_b, profile_velocities, period = repeat_config
        self.multi_repeat_enabled = True
        self.multi_repeat_axes = axes
        self.multi_repeat_modes = modes
        self.multi_repeat_points = [point_a, point_b]
        self.multi_repeat_profile_velocities = profile_velocities
        self.multi_repeat_period = period
        self.multi_repeat_index = 0
        self.multi_repeat_wait_until = 0.0
        self.multi_repeat_last_targets = None
        self.multi_repeat_waiting_to_send = False

    def stop_multi_repeat(self):
        self.multi_repeat_generation += 1
        self.multi_repeat_enabled = False
        self.multi_repeat_axes = []
        self.multi_repeat_modes = []
        self.multi_repeat_points = None
        self.multi_repeat_last_targets = None
        self.multi_repeat_waiting_to_send = False

    def stop_multi_repeat_motion(self):
        axes = list(self.multi_repeat_axes)
        self.stop_multi_repeat()
        if axes:
            self.try_send(lambda: self.client.send_axes_stop(axes))

    def read_selected_profile_values(self):
        is_pv = self.latest_motion_modes[self.selected_axis()] == "pv"
        profile_vars = self.profile_vars[1:3] if is_pv else self.profile_vars
        try:
            return [float(var.get()) for var in profile_vars]
        except ValueError:
            fields = "Profile Accel, Decel" if is_pv else "Profile Velocity, Accel, Decel"
            if not is_pv:
                fields += ", Jerk"
            messagebox.showerror(
                "Invalid Input",
                f"{fields} must be numeric values.",
            )
            return None

    def read_selected_motion_profile_velocity(self):
        try:
            return float(self.profile_vars[0].get())
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Profile Velocity must be numeric.",
            )
            return None

    def read_selected_limit_values(self):
        try:
            return [float(var.get()) for var in self.limit_vars]
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Max Profile Velocity +/-, Max Accel, Max Decel must be numeric values.",
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
                "Target Position must be numeric.",
            )
            return None

    def selected_multi_axes(self):
        axes = [
            axis_index
            for axis_index, var in enumerate(self.multi_axis_vars)
            if var.get()
        ]
        if not axes:
            messagebox.showerror(
                "Invalid Input",
                "Select at least one axis.",
            )
            return None
        return axes

    def read_multi_axis_command(self):
        axes = self.selected_multi_axes()
        if axes is None:
            return None

        modes = []
        values = []
        profile_velocities = []
        try:
            for axis_index in axes:
                mode = self.multi_motion_mode_vars[axis_index].get()
                modes.append(mode)
                values.append(float(self.multi_target_position_vars[axis_index].get()))
                if mode == "pv":
                    profile_velocities.append(None)
                else:
                    profile_velocities.append(
                        float(self.multi_profile_velocity_vars[axis_index].get())
                    )
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Multi-axis command values and profile velocities must be numeric.",
            )
            return None

        return axes, modes, values, profile_velocities

    def read_multi_repeat_values(self):
        axes = self.selected_multi_axes()
        if axes is None:
            return None

        point_a = []
        point_b = []
        modes = []
        profile_velocities = []
        try:
            for axis_index in axes:
                mode = self.multi_motion_mode_vars[axis_index].get()
                modes.append(mode)
                point_a.append(
                    float(self.multi_repeat_point_a_vars[axis_index].get())
                )
                point_b.append(
                    float(self.multi_repeat_point_b_vars[axis_index].get())
                )
                if mode == "pv":
                    profile_velocities.append(None)
                else:
                    profile_velocity = float(
                        self.multi_repeat_profile_velocity_vars[axis_index].get()
                    )
                    if profile_velocity <= 0:
                        raise ValueError
                    profile_velocities.append(profile_velocity)
            period = float(self.multi_repeat_period_var.get())
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Multi-axis repeat values and period must be numeric. "
                "Position-mode profile velocities and period must be greater than 0.",
            )
            return None

        if period <= 0:
            messagebox.showerror(
                "Invalid Input",
                "Multi-axis repeat period must be greater than 0.",
            )
            return None

        return axes, modes, point_a, point_b, profile_velocities, period

    def read_repeat_values(self):
        try:
            point_a = float(self.repeat_point_a_var.get())
            point_b = float(self.repeat_point_b_var.get())
            profile_velocity = float(self.repeat_profile_velocity_var.get())
            period = float(self.repeat_period_var.get())
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Repeat points, profile velocity, and period must be numeric.",
            )
            return None
        if profile_velocity <= 0:
            messagebox.showerror(
                "Invalid Input",
                "Repeat profile velocity must be greater than 0.",
            )
            return None
        if period <= 0:
            messagebox.showerror(
                "Invalid Input",
                "Repeat period must be greater than 0.",
            )
            return None
        return (
            point_a,
            point_b,
            profile_velocity,
            period,
        )

    def read_diagnosis_request(self, include_value):
        data_type = self.diagnosis_type_var.get().strip().lower()
        if data_type not in {
            "uint8",
            "int8",
            "uint16",
            "int32",
            "uint32",
            "udint",
            "float32",
        }:
            messagebox.showerror("Invalid Input", "Unsupported SDO data type.")
            return None

        index = self.diagnosis_index_var.get().strip()
        subindex = self.diagnosis_subindex_var.get().strip()
        try:
            int(index, 0)
            int(subindex, 0)
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Index and subindex must be decimal or hex values.",
            )
            return None

        value = None
        if include_value:
            raw_value = self.diagnosis_value_var.get().strip()
            try:
                if data_type == "float32":
                    value = float(raw_value)
                else:
                    int(raw_value, 0)
                    value = raw_value
            except ValueError:
                messagebox.showerror(
                    "Invalid Input",
                    "Value must match the selected SDO data type.",
                )
                return None

        return self.selected_axis(), index, subindex, data_type, value

    def queue_panel_sdo_reads(self, tasks):
        with self.client.lock:
            self._queue_panel_sdo_reads_locked(tasks)

    def _queue_panel_sdo_reads_locked(self, tasks):
        self.panel_sdo_read_queue = list(tasks) + list(self.panel_sdo_read_queue)
        self.panel_sdo_read_next_time = time.monotonic() + PANEL_SDO_READ_PERIOD

    @staticmethod
    def _format_sdo_index(value):
        return f"0x{int(value):04X}"

    @staticmethod
    def _format_sdo_subindex(value):
        return f"0x{int(value):02X}"

    def reset_panel_sdo_read_queue(self):
        self.panel_sdo_read_queue = []
        self.panel_sdo_read_next_time = 0.0
        self.panel_sdo_read_connected = False

    def start_panel_sdo_read_queue(self):
        self.panel_sdo_read_queue = []
        for axis_index in range(self.axis_count):
            self.panel_sdo_read_queue.extend([
                (axis_index, "0x2145", "0x0C", "uint32"),
                (axis_index, "0x6061", "0x00", "int8"),
                (axis_index, "0x607D", "0x01", "int32"),
                (axis_index, "0x607D", "0x02", "int32"),
                (axis_index, "0x6081", "0x00", "uint32"),
                (axis_index, "0x6083", "0x00", "uint32"),
                (axis_index, "0x6084", "0x00", "uint32"),
                (axis_index, "0x60A4", "0x01", "uint32"),
                (axis_index, "0x607F", "0x00", "uint32"),
                (axis_index, "0x2183", "0x0C", "float32"),
                (axis_index, "0x60C5", "0x00", "uint32"),
                (axis_index, "0x60C6", "0x00", "uint32"),
            ])
        self.panel_sdo_read_next_time = time.monotonic() + PANEL_SDO_READ_DELAY
        self.panel_sdo_read_connected = True

    def process_panel_sdo_read_queue(self, connected):
        if not connected:
            if self.panel_sdo_read_connected:
                self.reset_panel_sdo_read_queue()
            return

        if not self.panel_sdo_read_connected:
            self.start_panel_sdo_read_queue()

        if not self.panel_sdo_read_queue:
            return

        now = time.monotonic()
        if now < self.panel_sdo_read_next_time:
            return

        axis_index, index, subindex, data_type = self.panel_sdo_read_queue.pop(0)
        try:
            self.client.send_param_read(axis_index, index, subindex, data_type)
        except Exception as exc:
            self.diagnosis_result_var.set(
                "Panel SDO auto-read failed: "
                f"axis={axis_index} index={index}:{subindex} ({exc})"
            )
        finally:
            self.panel_sdo_read_next_time = now + PANEL_SDO_READ_PERIOD

    def try_send(self, send_func):
        try:
            send_func()
            return True
        except Exception as exc:
            messagebox.showerror("Send Failed", str(exc))
            return False

    def update_gui(self):
        connected, error, feedback, notice, diagnosis_result = self.client.get_snapshot()
        self.connection_var.set(
            f"Connected {self.client.host}:{self.client.port}"
            if connected
            else f"Disconnected {error}"
        )
        if notice:
            messagebox.showinfo("Axis Server", notice)
        if diagnosis_result:
            self.diagnosis_result_var.set(diagnosis_result)
        self.process_panel_sdo_read_queue(connected)

        target_positions = self._values(feedback, "target_positions", 0.0)
        actual_positions = self._values(feedback, "actual_positions", 0.0)
        actual_velocities = self._values(feedback, "actual_velocities", 0.0)
        setpoint_positions = self._values(feedback, "setpoint_positions", 0.0)
        command_positions = self._values(feedback, "command_positions", 0.0)
        command_velocities = self._values(feedback, "command_velocities", 0.0)
        statuswords = self._values(feedback, "statuswords", 0)
        diagnostics = feedback.get("diagnostics", [])
        self.server_mode = str(feedback.get("server_mode", self.server_mode)).lower()
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
        profile_settings = self._profile_settings(feedback)
        motion_limits = self._motion_limits(feedback)
        software_position_limits = self._software_position_limits(feedback)
        user_position_units = self._values(feedback, "user_position_units", None)
        converting_unit_exponents = self._axis_lists(
            feedback,
            "converting_unit_exponents",
            4,
            None,
        )
        axis_metadata = self._axis_metadata(
            feedback,
            user_position_units,
            converting_unit_exponents,
        )
        self.latest_target_positions = target_positions
        self.latest_actual_positions = actual_positions
        self.latest_profile_settings = profile_settings
        self.latest_motion_limits = motion_limits
        self.latest_software_position_limits = software_position_limits
        self.latest_motion_modes = motion_modes[:self.axis_count]
        self.latest_user_position_units = user_position_units
        self.latest_converting_unit_exponents = converting_unit_exponents
        self.latest_axis_metadata = axis_metadata
        for axis_index, mode in enumerate(self.latest_motion_modes):
            if axis_index < len(self.multi_motion_mode_vars):
                self.multi_motion_mode_vars[axis_index].set(mode)
        self.server_capabilities = dict(feedback.get("capabilities", {}))
        self.update_command_authority(feedback.get("command_authority", {}))
        self.position_counts_per_unit = max(position_counts_per_unit, 1e-9)
        self.scale_var.set(
            f"Position scale: {self.position_counts_per_unit:g} count/mm"
        )
        selected_axis = self.selected_axis()
        selected_statusword = int(statuswords[selected_axis])
        self.update_statusword_lamps(selected_statusword)
        self.update_axis_enable_button(selected_statusword)

        selected_motion_mode = self.latest_motion_modes[selected_axis]
        if selected_motion_mode in {"pp", "pv", "csp"}:
            self.server_motion_mode = selected_motion_mode
            if self.motion_mode_var.get() != selected_motion_mode:
                self.motion_mode_var.set(selected_motion_mode)
            self.update_mode_dependent_controls()
        self.update_unit_labels(selected_axis, selected_motion_mode)
        pos_unit, vel_unit, _accel_unit, _jerk_unit = self.axis_unit_labels(selected_axis)

        self.target_var.set(
            f"{self.position_count_to_unit(target_positions[selected_axis], selected_axis):.3f}"
        )
        self.actual_position_var.set(
            f"{self.position_count_to_unit(actual_positions[selected_axis], selected_axis):.3f}"
        )
        actual_velocity = self.velocity_count_to_unit(
            actual_velocities[selected_axis],
            selected_axis,
        )
        self.actual_velocity_var.set(f"{actual_velocity:.3f}")
        self.command_velocity_var.set(
            f"{self.velocity_count_to_unit(command_velocities[selected_axis], selected_axis):.3f}"
            if selected_motion_mode == "csp"
            else "n/a"
        )
        self.statusword_var.set(
            self.statusword_state_text(selected_statusword)
        )

        diag = diagnostics[selected_axis] if selected_axis < len(diagnostics) else {}
        self.error_code_var.set(self._format_error_code(diag))

        profile_kinds = ["velocity", "acceleration", "deceleration", "jerk"]
        for limit_index in range(4):
            if selected_motion_mode == "pv" and limit_index in (0, 3):
                continue
            var = self.profile_vars[limit_index]
            if id(var) not in self.dirty_vars:
                var.set(
                    f"{self.motion_drive_to_unit(profile_settings[selected_axis][limit_index], selected_axis, profile_kinds[limit_index]):.3f}"
                )

        limit_kinds = ["velocity", "velocity", "acceleration", "deceleration"]
        for limit_index in range(4):
            var = self.limit_vars[limit_index]
            if id(var) not in self.dirty_vars:
                var.set(
                    f"{self.motion_drive_to_unit(motion_limits[selected_axis][limit_index], selected_axis, limit_kinds[limit_index]):.3f}"
                )

        for limit_index in range(2):
            var = self.software_limit_vars[limit_index]
            if id(var) not in self.dirty_vars:
                var.set(
                    f"{self.position_count_to_unit(software_position_limits[selected_axis][limit_index], selected_axis):.3f}"
                )

        self.update_multi_axis_fields(actual_positions, profile_settings)
        self.update_multi_axis_mode_controls()

        if selected_motion_mode == "csp":
            self.position_trace.set_series_names(
                [
                    f"Actual Position {pos_unit}",
                    f"Target Position {pos_unit}",
                    f"CSP Command Position {pos_unit}",
                    f"Drive Setpoint Position {pos_unit}",
                ]
            )
            self.velocity_trace.set_series_names(
                [f"Actual Velocity {vel_unit}", f"Command Velocity {vel_unit}"]
            )
            self.position_trace.add_sample(
                [
                    self.position_count_to_unit(actual_positions[selected_axis], selected_axis),
                    self.position_count_to_unit(target_positions[selected_axis], selected_axis),
                    self.position_count_to_unit(command_positions[selected_axis], selected_axis),
                    self.position_count_to_unit(setpoint_positions[selected_axis], selected_axis),
                ]
            )
            self.velocity_trace.add_sample(
                [
                    actual_velocity,
                    self.velocity_count_to_unit(command_velocities[selected_axis], selected_axis),
                ]
            )
        else:
            self.position_trace.set_series_names(
                [f"Actual Position {pos_unit}", f"Target Position {pos_unit}"]
            )
            self.velocity_trace.set_series_names([f"Actual Velocity {vel_unit}"])
            self.position_trace.add_sample(
                [
                    self.position_count_to_unit(actual_positions[selected_axis], selected_axis),
                    self.position_count_to_unit(target_positions[selected_axis], selected_axis),
                ]
            )
            self.velocity_trace.add_sample([actual_velocity])
        self.position_trace.draw()
        self.velocity_trace.draw()
        multi_trace_axes = self.selected_multi_trace_axes()
        if self.multi_position_trace is not None:
            self.multi_position_trace.set_series_names(
                self.multi_trace_series_names(multi_trace_axes, "Actual Position")
            )
            self.multi_position_trace.add_sample([
                self.position_count_to_unit(actual_positions[axis_index], axis_index)
                for axis_index in multi_trace_axes
            ])
            self.multi_position_trace.draw()
        if self.multi_velocity_trace is not None:
            self.multi_velocity_trace.set_series_names(
                self.multi_trace_series_names(multi_trace_axes, "Actual Velocity")
            )
            self.multi_velocity_trace.add_sample([
                self.velocity_count_to_unit(actual_velocities[axis_index], axis_index)
                for axis_index in multi_trace_axes
            ])
            self.multi_velocity_trace.draw()

        self.update_repeat(actual_positions)
        self.update_multi_repeat(actual_positions)
        self.root.after(GUI_PERIOD_MS, self.update_gui)

    def update_multi_axis_fields(self, actual_positions, profile_settings):
        for axis_index in range(self.axis_count):
            self.multi_actual_position_vars[axis_index].set(
                f"{self.position_count_to_unit(actual_positions[axis_index], axis_index):.3f}"
            )
            mode = self.multi_motion_mode_vars[axis_index].get()
            if mode != "pv":
                velocity_var = self.multi_profile_velocity_vars[axis_index]
                if id(velocity_var) not in self.dirty_vars:
                    velocity_var.set(
                        f"{self.motion_drive_to_unit(profile_settings[axis_index][0], axis_index):.3f}"
                    )

            actual_position_text = (
                f"{self.position_count_to_unit(actual_positions[axis_index], axis_index):.3f}"
            )
            for repeat_var in (
                self.multi_repeat_point_a_vars[axis_index],
                self.multi_repeat_point_b_vars[axis_index],
            ):
                if not repeat_var.get().strip():
                    repeat_var.set(actual_position_text)

            if mode != "pv":
                repeat_velocity_var = self.multi_repeat_profile_velocity_vars[axis_index]
                if id(repeat_velocity_var) not in self.dirty_vars:
                    repeat_velocity_var.set(
                        f"{self.motion_drive_to_unit(profile_settings[axis_index][0], axis_index):.3f}"
                    )

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
        selected_axis = self.selected_axis()
        if self.pv_mode_button is not None:
            self.pv_mode_button.configure(
                state="normal" if self.axis_pv_allowed(selected_axis) else "disabled"
            )
            if (
                not self.axis_pv_allowed(selected_axis)
                and self.motion_mode_var.get() == "pv"
            ):
                self.motion_mode_var.set(self.latest_motion_modes[selected_axis])
        if self.csp_mode_button is not None:
            if self.server_mode == "advanced":
                if not self.csp_mode_button.winfo_ismapped():
                    self.csp_mode_button.pack(side="left", padx=8, pady=5)
            elif self.csp_mode_button.winfo_ismapped():
                self.csp_mode_button.pack_forget()
            if (
                self.server_mode != "advanced"
                and self.motion_mode_var.get() == "csp"
            ):
                self.motion_mode_var.set(self.latest_motion_modes[selected_axis])
        manual_cw_state = "normal" if self.server_mode == "advanced" else "disabled"
        for button in self.manual_controlword_buttons:
            button.configure(state=manual_cw_state)
        if self.manual_controlword_frame is not None:
            if self.server_mode == "advanced":
                if not self.manual_controlword_frame.winfo_ismapped():
                    self.manual_controlword_frame.pack(side="left", padx=(12, 0))
            else:
                if self.manual_controlword_frame.winfo_ismapped():
                    self.manual_controlword_frame.pack_forget()

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
            target_position = target[axis_index]
            self.try_send(
                lambda: self.client.send_axis_move_absolute(
                    axis_index,
                    target_position,
                    self.repeat_profile_velocity,
                )
            )
            self.last_sent_repeat_target = target_position
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
        generation = self.repeat_generation
        self.root.after(
            int(self.repeat_period * 1000),
            lambda: self._send_repeat_target(axis_index, next_target, generation),
        )

    def _send_repeat_target(self, axis_index, target_position, generation):
        if not self.repeat_enabled or generation != self.repeat_generation:
            return
        target = self._target_vector_for_axis(axis_index, target_position)
        target_count = target[axis_index]
        self.try_send(
            lambda: self.client.send_axis_move_absolute(
                axis_index,
                target_count,
                self.repeat_profile_velocity,
            )
        )
        self.last_sent_repeat_target = target_count
        self.repeat_waiting_to_send = False

    def update_multi_repeat(self, actual_positions):
        if not self.multi_repeat_enabled or self.multi_repeat_points is None:
            return

        now = time.monotonic()
        axes = list(self.multi_repeat_axes)
        modes = list(self.multi_repeat_modes)
        targets = list(self.multi_repeat_points[self.multi_repeat_index])
        if self.multi_repeat_last_targets is None:
            self.try_send(
                lambda: self.send_multi_axis_command(
                    axes,
                    modes,
                    targets,
                    self.multi_repeat_profile_velocities,
                )
            )
            self.multi_repeat_last_targets = targets
            return

        if self.multi_repeat_waiting_to_send or now < self.multi_repeat_wait_until:
            return

        position_targets = [
            (axis_index, target)
            for axis_index, mode, target in zip(axes, modes, self.multi_repeat_last_targets)
            if mode != "pv"
        ]
        reached = not position_targets or all(
            abs(actual_positions[axis_index] - target) <= REPEAT_TOLERANCE
            for axis_index, target in position_targets
        )
        if not reached:
            return

        self.multi_repeat_wait_until = now + self.multi_repeat_period
        self.multi_repeat_index = 1 - self.multi_repeat_index
        next_targets = list(self.multi_repeat_points[self.multi_repeat_index])
        self.multi_repeat_waiting_to_send = True
        generation = self.multi_repeat_generation
        self.root.after(
            int(self.multi_repeat_period * 1000),
            lambda: self._send_multi_repeat_targets(axes, modes, next_targets, generation),
        )

    def _send_multi_repeat_targets(self, axes, modes, targets, generation):
        if (
            not self.multi_repeat_enabled
            or generation != self.multi_repeat_generation
        ):
            return
        self.try_send(
            lambda: self.send_multi_axis_command(
                axes,
                modes,
                targets,
                self.multi_repeat_profile_velocities,
            )
        )
        self.multi_repeat_last_targets = list(targets)
        self.multi_repeat_waiting_to_send = False

    def _target_vector_for_axis(self, axis_index, target_position):
        targets = list(self.latest_target_positions)
        targets[axis_index] = self.position_unit_to_count(
            float(target_position),
            axis_index,
        )
        return targets

    def position_count_to_unit(self, position_count, axis_index=None):
        return float(position_count)

    def position_unit_to_count(self, position_unit, axis_index=None):
        return float(position_unit)

    def velocity_count_to_unit(self, velocity_count, axis_index=None):
        return float(velocity_count)

    def motion_drive_to_unit(self, value, axis_index=None, kind="velocity"):
        return float(value)

    def motion_unit_to_drive(self, value, axis_index=None, kind="velocity"):
        return float(value)

    def _values(self, feedback, key, default):
        values = list(feedback.get(key, []))
        while len(values) < self.axis_count:
            values.append(default)
        return values[:self.axis_count]

    def _axis_lists(self, feedback, key, fields_per_axis, default):
        values = list(feedback.get(key, []))
        if values and all(isinstance(value, list) for value in values):
            rows = [list(value) for value in values]
        else:
            flat = values
            required = self.axis_count * fields_per_axis
            while len(flat) < required:
                flat.append(default)
            rows = [
                flat[index * fields_per_axis:(index + 1) * fields_per_axis]
                for index in range(self.axis_count)
            ]
        while len(rows) < self.axis_count:
            rows.append([default for _ in range(fields_per_axis)])
        return [
            (row + [default for _ in range(fields_per_axis)])[:fields_per_axis]
            for row in rows[:self.axis_count]
        ]

    def _axis_metadata(self, feedback, user_position_units, converting_unit_exponents):
        metadata = list(feedback.get("axis_metadata", []))
        while len(metadata) < self.axis_count:
            metadata.append({})
        rows = []
        for axis_index in range(self.axis_count):
            axis_metadata = metadata[axis_index]
            if isinstance(axis_metadata, dict) and axis_metadata:
                rows.append(axis_metadata)
                continue
            rows.append(build_axis_metadata(
                axis_index,
                user_position_units[axis_index],
                converting_unit_exponents[axis_index],
            ))
        return rows

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

    def _profile_settings(self, feedback):
        flat = list(feedback.get("profile_settings", []))
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

    def _format_error_code(self, diagnostics):
        text = diagnostics.get("error_code_text", None)
        if isinstance(text, str) and text:
            return text

        value = diagnostics.get("error_code", None)
        if isinstance(value, int):
            if value == 0:
                return "No error"
            return f"Error {value}"
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
