from dataclasses import dataclass

from motion_server.control.csp_trajectory_generator import CspTrajectoryGenerator


@dataclass
class AxisMotionLimits:
    max_velocity: float
    acceleration: float
    deceleration: float
    jerk: float = 0.0


class MotionController:
    """Calculates axis motion commands without depending on a fieldbus."""

    def __init__(
        self,
        axis_count,
        cycle_time,
        motion_limits=None,
        csp_counts_per_unit=1.0,
        csp_velocity_offset_enabled=False,
        csp_command_step_threshold=0.0,
        csp_command_step_error_threshold=0.0,
        csp_profile="quintic",
    ):
        self.axis_count = int(axis_count)
        if self.axis_count < 1:
            raise ValueError("axis_count must be at least one")
        self.cycle_time = float(cycle_time)
        self.csp_counts_per_unit = float(csp_counts_per_unit)
        self.csp_velocity_offset_enabled = bool(csp_velocity_offset_enabled)
        self.csp_command_step_threshold = float(csp_command_step_threshold)
        self.csp_command_step_error_threshold = float(
            csp_command_step_error_threshold
        )
        self.csp_profile = str(csp_profile).strip().lower()
        self.axis_csp_counts_per_unit = [
            self.csp_counts_per_unit for _ in range(self.axis_count)
        ]
        self.motion_limits = [
            self._motion_limits_for_index(motion_limits, index)
            for index in range(self.axis_count)
        ]
        self.trajectory_generators = [
            CspTrajectoryGenerator(csp_profile=self.csp_profile)
            for _ in range(self.axis_count)
        ]
        self.last_csp_command_steps = []
        self.last_csp_output_steps = []
        self._last_output_target_positions = [None] * self.axis_count

    def set_target_positions(self, target_positions):
        for generator, target_position in zip(
            self.trajectory_generators, target_positions
        ):
            generator.set_target_position(target_position)

    def sync_trajectory_to_actual_positions(self, actual_positions):
        for generator, actual_position in zip(
            self.trajectory_generators,
            actual_positions,
        ):
            generator.reset(float(actual_position))

    def sync_trajectory_to_actual_position(self, axis_index, actual_position):
        self.trajectory_generators[axis_index].reset(
            float(actual_position)
        )

    def set_axis_motion_limits(
        self, axis_index, max_velocity, acceleration, deceleration, jerk=0.0
    ):
        self.motion_limits[axis_index] = AxisMotionLimits(
            float(max_velocity),
            float(acceleration),
            float(deceleration),
            float(jerk),
        )

    def set_axis_csp_counts_per_unit(self, axis_index, counts_per_unit):
        self.axis_csp_counts_per_unit[axis_index] = float(counts_per_unit)

    def hold_axes(self, target_positions, actual_positions, axis_indices):
        positions = list(target_positions)
        for axis_index in axis_indices:
            actual_position = float(actual_positions[axis_index])
            positions[axis_index] = actual_position
            self.trajectory_generators[axis_index].reset(actual_position)
        return positions

    @staticmethod
    def relative_target_positions(actual_positions, axis_indices, distances):
        positions = [float(position) for position in actual_positions]
        for axis_index, distance in zip(axis_indices, distances):
            positions[axis_index] += float(distance)
        return positions

    def trajectory_progress(self, axis_indices):
        positions = {}
        elapsed = 0.0
        segment = 0
        active = False
        for axis_index in axis_indices:
            generator = self.trajectory_generators[axis_index]
            positions[axis_index] = float(generator.command_position)
            elapsed = max(elapsed, float(generator.timed_elapsed))
            segment = max(segment, int(generator.timed_segment))
            active = active or bool(generator.timed_active)
        return {
            "positions": positions,
            "elapsed": elapsed,
            "segment": segment,
            "active": active,
        }

    def command_positions(self, axis_indices):
        return [
            float(self.trajectory_generators[index].command_position)
            for index in axis_indices
        ]

    def set_axis_trajectories(self, axis_indices, timed_points_by_axis):
        for axis_index, timed_points in zip(
            axis_indices,
            timed_points_by_axis,
        ):
            self.trajectory_generators[axis_index].set_trajectory_move(
                timed_points
            )

    def sync_velocity_command(self, axis_index, velocity, actual_position):
        generator = self.trajectory_generators[axis_index]
        generator.command_velocity = float(velocity)
        generator.target_position = float(actual_position)
        generator.command_position = float(actual_position)

    def complete_trajectory(self, axis_indices, final_positions):
        completed = {}
        for axis_index, final_position in zip(axis_indices, final_positions):
            final_position = float(final_position)
            generator = self.trajectory_generators[axis_index]
            generator.command_position = final_position
            generator.target_position = final_position
            generator.command_velocity = 0.0
            generator.command_acceleration = 0.0
            generator.clear_timed_trajectory()
            completed[axis_index] = final_position
        return completed

    def update_commands(self, modes_of_operation, previous_target_positions):
        self.last_csp_command_steps = []
        commands = [None] * self.axis_count
        for axis_index, (mode, previous_target, generator) in enumerate(zip(
            modes_of_operation,
            previous_target_positions,
            self.trajectory_generators,
        )):
            if int(mode) != 8:
                continue

            limits = self.motion_limits[axis_index]
            scale = self.axis_csp_counts_per_unit[axis_index]
            previous_command_position = float(generator.command_position)
            previous_sent_position = int(previous_target)
            command_position = float(generator.update(
                self.cycle_time,
                limits.max_velocity * scale,
                limits.acceleration * scale,
                limits.deceleration * scale,
                limits.jerk * scale,
            ))
            sent_position = int(round(command_position))
            velocity_offset = 0
            if self.csp_velocity_offset_enabled:
                velocity_offset = int(round(
                    float(generator.command_velocity) / max(scale, 1e-9)
                ))
            commands[axis_index] = {
                "target_position": sent_position,
                "velocity_offset": velocity_offset,
            }

            command_step = command_position - previous_command_position
            sent_step = sent_position - previous_sent_position
            expected_step = float(generator.command_velocity) * self.cycle_time
            step_error = sent_step - expected_step
            if self._step_is_reportable(sent_step, step_error):
                self.last_csp_command_steps.append({
                    "axis": axis_index,
                    "previous_command_position": previous_command_position,
                    "command_position": command_position,
                    "command_step": command_step,
                    "previous_sent_position": previous_sent_position,
                    "sent_position": sent_position,
                    "sent_step": sent_step,
                    "expected_step": expected_step,
                    "step_error": step_error,
                    "command_velocity": float(generator.command_velocity),
                    "target_position": float(generator.target_position),
                })
        self._track_output_target_steps(commands, modes_of_operation)
        return commands

    def _track_output_target_steps(self, commands, modes_of_operation):
        self.last_csp_output_steps = []
        for axis_index, (command, mode, generator) in enumerate(zip(
            commands,
            modes_of_operation,
            self.trajectory_generators,
        )):
            if command is None:
                continue
            output_target = int(command["target_position"])
            previous = self._last_output_target_positions[axis_index]
            self._last_output_target_positions[axis_index] = output_target
            if previous is None or int(mode) != 8:
                continue
            output_step = output_target - previous
            expected_step = float(generator.command_velocity) * self.cycle_time
            step_error = output_step - expected_step
            if self._step_is_reportable(output_step, step_error):
                self.last_csp_output_steps.append({
                    "axis": axis_index,
                    "previous_output_target": previous,
                    "output_target": output_target,
                    "output_step": output_step,
                    "command_target": output_target,
                    "expected_step": expected_step,
                    "step_error": step_error,
                    "command_position": float(generator.command_position),
                    "command_velocity": float(generator.command_velocity),
                    "target_position": float(generator.target_position),
                })

    def _step_is_reportable(self, step, error):
        return (
            self.csp_command_step_threshold > 0.0
            and abs(step) >= self.csp_command_step_threshold
        ) or (
            self.csp_command_step_error_threshold > 0.0
            and abs(error) >= self.csp_command_step_error_threshold
        )

    @staticmethod
    def _motion_limits_for_index(motion_limits, index):
        if motion_limits is None:
            return AxisMotionLimits(1000.0, 1000.0, 1000.0, 0.0)
        limits = motion_limits[index]
        if isinstance(limits, AxisMotionLimits):
            return limits
        return AxisMotionLimits(
            float(limits["max_velocity"]),
            float(limits["acceleration"]),
            float(limits["deceleration"]),
            float(limits.get("jerk", 0.0)),
        )
