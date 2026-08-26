"""TCP client used by the Axis Control Panel."""

import json
import socket
import threading
import time

from control_panel.axis_control_panel.panel_update_data import (
    initial_feedback,
    merge_axis_status,
    merge_system_feedback,
)
from control_panel.axis_control_panel.units import api_to_user_unit_factor
from motion_server_client import decode_server_message, is_fail_message

RECONNECT_PERIOD = 1.0

def axis_count_from_feedback(message):
    for key in (
        "target_positions",
        "actual_positions",
        "actual_velocities",
        "statuswords",
        "mode_displays",
    ):
        value = message.get(key)
        if isinstance(value, list) and value:
            return len(value)
    return 0


class AxisServerClient:
    def __init__(self, host, port, axis_count=0):
        self.host = host
        self.port = port
        self.axis_count = axis_count
        self.sock = None
        self.sock_file = None
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.connected = False
        self.enabled = True
        self.last_error = ""
        self.feedback = initial_feedback(axis_count)
        self.topology_error = ""
        self.last_notice = ""
        self.last_diagnosis_result = ""
        self.last_axis_param_catalog = None
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
            self.feedback["process_data_valid"] = False

    def set_endpoint(self, host, port):
        with self.lock:
            self.host = str(host).strip()
            self.port = int(port)
            self.enabled = True
            self.last_error = "Reconnecting..."
        self.close()

    def disconnect(self):
        with self.lock:
            self.enabled = False
            self.last_error = "Disconnected by user"
        self.close()

    def enable_connection(self):
        with self.lock:
            self.enabled = True
            self.last_error = "Connecting..."

    def _connection_loop(self):
        while not self.stop_event.is_set():
            if not self.enabled:
                time.sleep(RECONNECT_PERIOD)
                continue
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

            message = decode_server_message(json.loads(line))
            if is_fail_message(message):
                self._store_notice(message)
            elif message.get("type") == "system/axes/status":
                self._store_feedback(message)
            elif message.get("type") == "system/axis/status":
                self._merge_axis_status(message)
            elif message.get("type") == "system/feedback":
                if self._merge_system_feedback(message):
                    self.request_system_status()
            elif message.get("type") in {
                "system/authority/request",
                "system/authority/release",
                "system/authority/status",
                "command_rejected",
            }:
                self._store_notice(message)
            elif message.get("type") in {
                "system/axis/param_read",
                "system/axis/param_write",
                "system/axis/param_catalog",
                "system/axis/param_save",
                "system/axis/restart",
                "system/axis/fault_reset",
                "system/axes/fault_reset",
                "system/server/fault_reset",
                "system/server/restart",
                "system/bus/reconnect",
            }:
                self._store_diagnosis_result(message)

    def _store_feedback(self, message):
        with self.lock:
            preserved = {
                key: self.feedback.get(key)
                for key in (
                    "server_health",
                    "process_data_valid",
                    "axis_diagnostic_statuses",
                )
                if key in self.feedback
            }
            self.feedback = dict(message)
            for key, value in preserved.items():
                self.feedback.setdefault(key, value)
            for result in self.sdo_read_results:
                self._apply_param_read_result(result)

    def _merge_system_feedback(self, message):
        with self.lock:
            message_axis_count = axis_count_from_feedback(message)
            topology_initialized = False
            if self.axis_count == 0 and message_axis_count > 0:
                self.axis_count = message_axis_count
                self.feedback = initial_feedback(message_axis_count)
                topology_initialized = True
            elif (
                self.axis_count > 0
                and message_axis_count > 0
                and message_axis_count != self.axis_count
            ):
                self.topology_error = (
                    "Server axis configuration changed. Restart Axis Control Panel."
                )
                self.feedback["process_data_valid"] = False
                self.feedback["server_health"] = dict(
                    message.get("server_health", {})
                )
                return False
            merge_system_feedback(self.feedback, message, self.axis_count)
            return topology_initialized

    def _merge_axis_status(self, message):
        with self.lock:
            merge_axis_status(self.feedback, message, self.axis_count)

    def _store_notice(self, message):
        with self.lock:
            self.last_notice = str(message.get("message", ""))
            if message.get("type") in {
                "system/authority/request",
                "system/authority/release",
                "system/authority/status",
            }:
                self.feedback["command_authority"] = {
                    "owner": message.get("owner"),
                    "owned_by_this_client": bool(
                        message.get("owned_by_this_client", False)
                    ),
                    "available": bool(message.get("available", False)),
                }
            elif message.get("reason") in {
                "authority_required",
                "authority_busy",
            }:
                self.feedback["command_authority"] = {
                    "owner": message.get("owner"),
                    "owned_by_this_client": False,
                    "available": bool(message.get("available", False)),
                }

    def _store_diagnosis_result(self, message):
        with self.lock:
            if message.get("type") == "system/axis/param_catalog":
                self.last_axis_param_catalog = dict(message)
                self.last_diagnosis_result = (
                    "Axis parameter catalog response received: "
                    f"ok={message.get('ok', False)} "
                    f"axis={message.get('axis')} "
                    f"items={len(message.get('objects', []))}"
                )
                return
            self.last_diagnosis_result = json.dumps(message, ensure_ascii=False)
            if message.get("type") == "system/axis/param_read" and message.get("ok"):
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
        diagnostics = self.feedback.setdefault("device_diagnostics", [])
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
        if metadata.get("motion_kind") in ("linear", "rotary"):
            position_scale = max(float(metadata.get("position_scale", 1.0)), 1e-12)
            factor = api_to_user_unit_factor(metadata.get("user_position_unit"))
            counts_per_api_unit = factor / position_scale
        else:
            counts_per_api_unit = float(self.feedback.get("position_counts_per_unit", 1.0))
        return float(value) / max(counts_per_api_unit, 1e-9)

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
        factor = api_to_user_unit_factor(metadata.get("user_position_unit"))
        return float(value) * scale / factor

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

    def get_topology_snapshot(self):
        with self.lock:
            return self.axis_count, self.topology_error

    def process_data_valid(self):
        with self.lock:
            return bool(self.feedback.get("process_data_valid", False))

    def pop_axis_param_catalog(self):
        with self.lock:
            catalog = self.last_axis_param_catalog
            self.last_axis_param_catalog = None
            return catalog

    def send_json(self, message, refresh_status=False):
        payload = (json.dumps(message) + "\n").encode("utf-8")
        with self.lock:
            if self.sock is None:
                raise ConnectionError("Motion Server is not connected")
            self.sock.sendall(payload)
            if refresh_status:
                status_payload = (json.dumps({"cmd": "system/axes/status"}) + "\n").encode(
                    "utf-8",
                )
                self.sock.sendall(status_payload)

    def request_system_status(self):
        self.send_json({"cmd": "system/axes/status"})

    def request_axis_status(self, axis_index):
        self.send_json(
            {
                "cmd": "system/axis/status",
                "axis": int(axis_index),
            }
        )

    def send_axis_move_absolute(self, axis_index, position, profile_velocity=None):
        message = {
            "cmd": "system/axis/move_abs",
            "axis": int(axis_index),
            "position": float(position),
        }
        if profile_velocity is not None:
            message["profile_velocity"] = float(profile_velocity)
        self.send_json(message)

    def send_axes_move_absolute(self, axes, positions, profile_velocities=None):
        message = {
            "cmd": "system/axes/move_abs",
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
                "cmd": "system/axis/move_vel",
                "axis": int(axis_index),
                "velocity": float(velocity),
            }
        )

    def send_axes_move_velocity(self, axes, velocities):
        self.send_json(
            {
                "cmd": "system/axes/move_vel",
                "axes": [int(axis_index) for axis_index in axes],
                "velocities": [float(velocity) for velocity in velocities],
            }
        )

    def send_axis_enable(self, axis_index):
        self.send_json(
            {
                "cmd": "system/axis/enable",
                "axis": int(axis_index),
            }
        )

    def send_axis_disable(self, axis_index):
        self.send_json(
            {
                "cmd": "system/axis/disable",
                "axis": int(axis_index),
            }
        )

    def send_profile_settings(self, axis_index, profile_settings):
        message = {
            "cmd": "system/axis/profile",
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
        self.send_json(message, refresh_status=True)

    def send_axis_motion_limits(self, axis_index, axis_limits):
        self.send_json(
            {
                "cmd": "system/axis/motion_limits",
                "axis": int(axis_index),
                "positive_velocity_limit": float(axis_limits[0]),
                "negative_velocity_limit": float(axis_limits[1]),
                "max_acceleration": float(axis_limits[2]),
                "max_deceleration": float(axis_limits[3]),
            },
            refresh_status=True,
        )

    def send_axis_software_position_limits(
        self,
        axis_index,
        negative_limit,
        positive_limit,
    ):
        self.send_json(
            {
                "cmd": "system/axis/software_position_limits",
                "axis": int(axis_index),
                "negative_limit": float(negative_limit),
                "positive_limit": float(positive_limit),
            },
            refresh_status=True,
        )

    def send_motion_mode(self, mode, axis_index):
        self.send_json(
            {
                "cmd": "system/axis/mode",
                "axis": int(axis_index),
                "mode": str(mode).lower(),
            },
            refresh_status=True,
        )

    def send_controlword(self, controlword, axis_index):
        self.send_json(
            {
                "cmd": "system/axis/manualCW",
                "axis": int(axis_index),
                "controlword": int(controlword),
            }
        )

    def send_axis_move_relative(self, axis_index, distance, profile_velocity=None):
        message = {
            "cmd": "system/axis/move_rel",
            "axis": int(axis_index),
            "distance": float(distance),
        }
        if profile_velocity is not None:
            message["profile_velocity"] = float(profile_velocity)
        self.send_json(message)

    def send_jog_start(self, axis_index, direction, speed="slow"):
        self.send_json(
            {
                "cmd": "system/axis/jog_start",
                "axis": int(axis_index),
                "direction": str(direction),
                "speed": str(speed),
            }
        )

    def send_jog_stop(self, axis_index):
        self.send_json(
            {
                "cmd": "system/axis/jog_stop",
                "axis": int(axis_index),
            }
        )

    def send_axis_stop(self, axis_index):
        self.send_json(
            {
                "cmd": "system/axis/stop",
                "axis": int(axis_index),
            }
        )

    def send_axes_stop(self, axes):
        self.send_json(
            {
                "cmd": "system/axes/stop",
                "axes": [int(axis_index) for axis_index in axes],
            }
        )

    def send_homing_start(self, axis_index):
        self.send_json(
            {
                "cmd": "system/axis/home",
                "axis": int(axis_index),
            }
        )

    def send_axes_homing_start(self, axes):
        for axis_index in axes:
            self.send_homing_start(axis_index)

    def send_axis_fault_reset(self, axis_index):
        self.send_json(
            {
                "cmd": "system/axis/fault_reset",
                "axis": int(axis_index),
            }
        )

    def send_axis_restart(self, axis_index):
        self.send_json(
            {
                "cmd": "system/axis/restart",
                "axis": int(axis_index),
            }
        )

    def send_axes_fault_reset(self, axes):
        self.send_json(
            {
                "cmd": "system/axes/fault_reset",
                "axes": [int(axis_index) for axis_index in axes],
            }
        )

    def request_command_authority(self):
        self.send_json({"cmd": "system/authority/request"})

    def release_command_authority(self):
        self.send_json({"cmd": "system/authority/release"})

    def send_param_read(self, axis_index, index, subindex, data_type, length=None):
        message = {
            "cmd": "system/axis/param_read",
            "axis": int(axis_index),
            "index": str(index),
            "subindex": str(subindex),
            "data_type": str(data_type),
        }
        if length is not None and str(length).strip():
            message["length"] = str(length)
        self.send_json(message)

    def send_param_write(self, axis_index, index, subindex, data_type, value, length=None):
        message = {
            "cmd": "system/axis/param_write",
            "axis": int(axis_index),
            "index": str(index),
            "subindex": str(subindex),
            "data_type": str(data_type),
            "value": value,
        }
        if length is not None and str(length).strip():
            message["length"] = str(length)
        self.send_json(message)

    def send_axis_param_catalog(self, axis_index):
        self.send_json(
            {
                "cmd": "system/axis/param_catalog",
                "axis": int(axis_index),
            }
        )

    def send_param_save(self, axis_index):
        self.send_json(
            {
                "cmd": "system/axis/param_save",
                "axis": int(axis_index),
            },
            refresh_status=False,
        )

    def send_server_fault_reset(self):
        self.send_json({"cmd": "system/server/fault_reset"})

    def send_server_restart(self):
        self.send_json({"cmd": "system/server/restart"})

    def send_bus_reconnect(self):
        self.send_json({"cmd": "system/bus/reconnect"})
