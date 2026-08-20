import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root))

from control_panel.axis_control_panel.client import AxisServerClient
from control_panel.axis_control_panel.config import read_runtime_config
from control_panel.axis_control_panel.connection import ConnectionMixin
from control_panel.axis_control_panel.diagnosis import DiagnosisMixin
from control_panel.axis_control_panel.motion import MotionMixin
from control_panel.axis_control_panel.motion_settings import MotionSettingsMixin
from control_panel.axis_control_panel.panel_update_data import PanelUpdateDataMixin
from control_panel.axis_control_panel.statusword import StatuswordMixin
from control_panel.axis_control_panel.trace import TraceMixin
from control_panel.axis_control_panel.ui_builders.multi_axis_view import MultiAxisViewBuilderMixin
from control_panel.axis_control_panel.ui_builders.panel_layout import PanelLayoutMixin
from control_panel.axis_control_panel.ui_builders.single_axis_view import SingleAxisViewBuilderMixin
from control_panel.axis_control_panel.units import (
    MODE_DISPLAY_NAMES,
    UnitConversionMixin,
)

GUI_PERIOD_MS = 50


class AxisServerControlPanel(
    PanelLayoutMixin,
    SingleAxisViewBuilderMixin,
    MultiAxisViewBuilderMixin,
    ConnectionMixin,
    MotionMixin,
    MotionSettingsMixin,
    DiagnosisMixin,
    PanelUpdateDataMixin,
    StatuswordMixin,
    UnitConversionMixin,
    TraceMixin,
):
    def __init__(self, client, axis_names, auto_sdo_reads=False):
        self.client = client
        self.axis_names = axis_names
        self.axis_count = len(axis_names)
        self.auto_sdo_reads = bool(auto_sdo_reads)
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
        self.server_host_var = tk.StringVar(value=self.client.host)
        self.server_port_var = tk.StringVar(value=str(self.client.port))
        self.connection_button_var = tk.StringVar(value="Connect")
        self.connection_var = tk.StringVar(value="Disconnected")
        self.command_authority_var = tk.StringVar(value="Authority: available")
        self.command_authority_button_var = tk.StringVar(value="Request Authority")
        self.axis_enable_button_var = tk.StringVar(value="Enable")
        self.scale_var = tk.StringVar(value="CSP scale: 1.0 count/unit")
        self.diagnosis_index_var = tk.StringVar(value="0x607F")
        self.diagnosis_subindex_var = tk.StringVar(value="0x00")
        self.diagnosis_type_var = tk.StringVar(value="uint32")
        self.diagnosis_length_var = tk.StringVar(value="")
        self.diagnosis_value_var = tk.StringVar(value="0")
        self.diagnosis_result_var = tk.StringVar(value="No SDO request yet.")
        self.diagnosis_catalog_var = tk.StringVar(value="")
        self.diagnosis_catalog_items = {}
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
        self.connection_button = None
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

    def update_gui(self):
        connected, error, feedback, notice, diagnosis_result = self.client.get_snapshot()
        self._update_connection_feedback(connected, error, notice, diagnosis_result)
        self.process_axis_param_catalog()

        update_data = self._build_gui_update_data(feedback)
        self._apply_gui_update_data(feedback, update_data)
        self._update_selected_axis_display(feedback, update_data)
        self.update_multi_axis_fields(
            update_data["actual_positions"],
            update_data["profile_settings"],
        )
        self.update_multi_axis_mode_controls()
        self._update_traces(update_data)
        self.update_repeat(update_data["actual_positions"])
        self.update_multi_repeat(update_data["actual_positions"])
        self.root.after(GUI_PERIOD_MS, self.update_gui)

    def _update_connection_feedback(self, connected, error, notice, diagnosis_result):
        self.connection_var.set(
            f"Connected {self.client.host}:{self.client.port}"
            if connected
            else f"Disconnected {error}"
        )
        self.update_connection_button(connected)
        if notice:
            messagebox.showinfo("Axis Server", notice)
        if diagnosis_result:
            self.diagnosis_result_var.set(diagnosis_result)
        self.process_panel_sdo_read_queue(connected)

    def _build_gui_update_data(self, feedback):
        target_positions = self._values(feedback, "target_positions", 0.0)
        actual_positions = self._values(feedback, "actual_positions", 0.0)
        actual_velocities = self._values(feedback, "actual_velocities", 0.0)
        command_positions = self._values(feedback, "command_positions", 0.0)
        command_velocities = self._values(feedback, "command_velocities", 0.0)
        statuswords = self._values(feedback, "statuswords", 0)
        motion_modes = self._motion_modes_from_feedback(feedback)
        position_counts_per_unit = float(
            feedback.get("position_counts_per_unit", 1.0)
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
        return {
            "target_positions": target_positions,
            "actual_positions": actual_positions,
            "actual_velocities": actual_velocities,
            "command_positions": command_positions,
            "command_velocities": command_velocities,
            "statuswords": statuswords,
            "motion_modes": motion_modes,
            "position_counts_per_unit": position_counts_per_unit,
            "profile_settings": profile_settings,
            "motion_limits": motion_limits,
            "software_position_limits": software_position_limits,
            "user_position_units": user_position_units,
            "converting_unit_exponents": converting_unit_exponents,
            "axis_metadata": axis_metadata,
        }

    def _motion_modes_from_feedback(self, feedback):
        self.server_mode = str(feedback.get("server_mode", self.server_mode)).lower()
        motion_mode = str(feedback.get("motion_mode", self.server_motion_mode)).lower()
        motion_modes = [
            str(value).lower()
            for value in feedback.get("motion_modes", [])
        ]
        while len(motion_modes) < self.axis_count:
            motion_modes.append(motion_mode)

        mode_displays = self._values(feedback, "mode_displays", None)
        for axis_index, mode_display in enumerate(mode_displays[:self.axis_count]):
            if mode_display is None:
                continue
            try:
                display_mode = MODE_DISPLAY_NAMES.get(int(mode_display))
            except (TypeError, ValueError):
                display_mode = None
            if display_mode is not None:
                motion_modes[axis_index] = display_mode
        return motion_modes

    def _apply_gui_update_data(self, feedback, update_data):
        self.latest_target_positions = update_data["target_positions"]
        self.latest_actual_positions = update_data["actual_positions"]
        self.latest_profile_settings = update_data["profile_settings"]
        self.latest_motion_limits = update_data["motion_limits"]
        self.latest_software_position_limits = update_data["software_position_limits"]
        self.latest_motion_modes = update_data["motion_modes"][:self.axis_count]
        self.latest_user_position_units = update_data["user_position_units"]
        self.latest_converting_unit_exponents = update_data["converting_unit_exponents"]
        self.latest_axis_metadata = update_data["axis_metadata"]
        for axis_index, mode in enumerate(self.latest_motion_modes):
            if axis_index < len(self.multi_motion_mode_vars):
                self.multi_motion_mode_vars[axis_index].set(mode)
        self.server_capabilities = dict(feedback.get("capabilities", {}))
        self.update_command_authority(feedback.get("command_authority", {}))
        self.position_counts_per_unit = max(
            update_data["position_counts_per_unit"],
            1e-9,
        )
        self.scale_var.set(
            f"Position scale: {self.position_counts_per_unit:g} count/mm"
        )

    def _update_selected_axis_display(self, feedback, update_data):
        selected_axis = self.selected_axis()
        statuswords = update_data["statuswords"]
        target_positions = update_data["target_positions"]
        actual_positions = update_data["actual_positions"]
        actual_velocities = update_data["actual_velocities"]
        command_velocities = update_data["command_velocities"]
        profile_settings = update_data["profile_settings"]
        motion_limits = update_data["motion_limits"]
        software_position_limits = update_data["software_position_limits"]
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

        diagnostics = feedback.get("diagnostics", [])
        diag = diagnostics[selected_axis] if selected_axis < len(diagnostics) else {}
        self.error_code_var.set(self._format_error_code(diag))
        self._refresh_selected_axis_settings_fields(update_data, selected_axis)

    def _refresh_selected_axis_settings_fields(self, update_data, selected_axis):
        selected_motion_mode = self.latest_motion_modes[selected_axis]
        profile_settings = update_data["profile_settings"]
        motion_limits = update_data["motion_limits"]
        software_position_limits = update_data["software_position_limits"]
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

    def _update_traces(self, update_data):
        selected_axis = self.selected_axis()
        selected_motion_mode = self.latest_motion_modes[selected_axis]
        target_positions = update_data["target_positions"]
        actual_positions = update_data["actual_positions"]
        actual_velocities = update_data["actual_velocities"]
        command_positions = update_data["command_positions"]
        command_velocities = update_data["command_velocities"]
        pos_unit, vel_unit, _accel_unit, _jerk_unit = self.axis_unit_labels(selected_axis)
        actual_velocity = self.velocity_count_to_unit(
            actual_velocities[selected_axis],
            selected_axis,
        )

        if selected_motion_mode == "csp":
            self.position_trace.set_series_names(
                [
                    f"Actual Position {pos_unit}",
                    f"Target Position {pos_unit}",
                    f"CSP Command Position {pos_unit}",
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
        self._update_multi_axis_traces(actual_positions, actual_velocities)

    def _update_multi_axis_traces(self, actual_positions, actual_velocities):
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

    def close(self):
        self.client.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    host, port, axis_names, auto_sdo_reads = read_runtime_config()
    client = AxisServerClient(host, port, len(axis_names))
    client.start()
    gui = AxisServerControlPanel(client, axis_names, auto_sdo_reads)
    gui.run()

if __name__ == "__main__":
    main()
