"""Motion profile and limit setting helpers for Axis Control Panel."""

from tkinter import messagebox


class MotionSettingsMixin:
    def apply_profile_settings(self):
        profile_settings = self.read_selected_profile_values()
        if profile_settings is None:
            return
        axis_index = self.selected_axis()
        for var in self._selected_profile_dirty_vars(axis_index, profile_settings):
            self.dirty_vars.discard(id(var))
        self.try_send(
            lambda: self.client.send_profile_settings(axis_index, profile_settings)
        )

    def apply_motion_limits(self):
        axis_limits = self.read_selected_limit_values()
        if axis_limits is None:
            return
        axis_index = self.selected_axis()
        for var in self.limit_vars:
            self.dirty_vars.discard(id(var))
        self.try_send(
            lambda: self.client.send_axis_motion_limits(axis_index, axis_limits)
        )

    def apply_software_limits(self):
        software_limits_mm = self.read_selected_software_limit_values()
        if software_limits_mm is None:
            return

        axis_index = self.selected_axis()
        for var in self.software_limit_vars:
            self.dirty_vars.discard(id(var))
        self.try_send(
            lambda: self.client.send_axis_software_position_limits(
                axis_index,
                software_limits_mm[0],
                software_limits_mm[1],
            )
        )

    def _selected_profile_dirty_vars(self, axis_index, profile_settings):
        if self.latest_motion_modes[axis_index] == "pv":
            return self.profile_vars[1:3]
        return self.profile_vars[:len(profile_settings)]

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
