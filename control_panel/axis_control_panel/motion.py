"""Motion command helpers for Axis Control Panel."""

import time
from tkinter import messagebox


REPEAT_TOLERANCE = 10.0


class MotionMixin:
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

    def multi_axis_fault_reset(self):
        self.stop_multi_repeat()
        axes = self.selected_multi_axes()
        if axes is not None:
            self.try_send(lambda: self.client.send_axes_fault_reset(axes))

    def axis_fault_reset(self):
        axis_index = self.selected_axis()
        self.try_send(lambda: self.client.send_axis_fault_reset(axis_index))

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

    def read_selected_command_value(self):
        try:
            return float(self.command_var.get())
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Target Position must be numeric.",
            )
            return None

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
