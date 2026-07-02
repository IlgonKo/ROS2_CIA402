import math


class CspTrajectoryGenerator:
    def __init__(self, initial_position=0.0):
        self.command_position = float(initial_position)
        self.target_position = float(initial_position)
        self.command_velocity = 0.0
        self.command_acceleration = 0.0
        self.timed_points = []
        self.timed_elapsed = 0.0
        self.timed_segment = 0
        self.timed_active = False
        self.manual_profile = None

    def set_target_position(self, target_position):
        self.target_position = float(target_position)
        self.timed_active = False
        self.timed_points = []
        self.manual_profile = None

    def reset(self, position):
        self.command_position = float(position)
        self.target_position = float(position)
        self.command_velocity = 0.0
        self.command_acceleration = 0.0
        self.timed_points = []
        self.timed_elapsed = 0.0
        self.timed_segment = 0
        self.timed_active = False
        self.manual_profile = None

    def set_timed_trajectory(self, points):
        self.timed_points = [
            {
                "position": float(point["position"]),
                "velocity": (
                    float(point["velocity"])
                    if "velocity" in point
                    else None
                ),
                "acceleration": (
                    float(point["acceleration"])
                    if "acceleration" in point
                    else None
                ),
                "time_from_start": float(point["time_from_start"]),
            }
            for point in points
        ]
        self._fill_missing_timed_velocities()
        self.timed_elapsed = 0.0
        self.timed_segment = 0
        self.timed_active = len(self.timed_points) >= 2
        self.manual_profile = None
        if self.timed_points:
            first = self.timed_points[0]
            self.command_position = first["position"]
            self.target_position = first["position"]
            self.command_velocity = first["velocity"] or 0.0
            self.command_acceleration = first["acceleration"] or 0.0

    def clear_timed_trajectory(self):
        self.timed_points = []
        self.timed_elapsed = 0.0
        self.timed_segment = 0
        self.timed_active = False
        self.manual_profile = None

    def update(
        self,
        cycle_time,
        max_velocity,
        acceleration,
        deceleration,
        jerk=None,
    ):
        cycle_time = max(float(cycle_time), 1e-9)
        max_velocity = max(float(max_velocity), 0.0)
        acceleration = max(float(acceleration), 1e-9)
        deceleration = max(float(deceleration), 1e-9)
        jerk = float(jerk) if jerk is not None else 0.0

        if self.timed_active:
            return self._update_timed_trajectory(cycle_time)

        if jerk <= 0.0:
            self.manual_profile = None
            return self._update_trapezoid(
                cycle_time,
                max_velocity,
                acceleration,
                deceleration,
            )

        return self._update_smooth_manual_profile(
            cycle_time,
            max_velocity,
            acceleration,
            deceleration,
            jerk,
        )

    def _update_smooth_manual_profile(
        self,
        cycle_time,
        max_velocity,
        acceleration,
        deceleration,
        jerk,
    ):
        if (
            self.manual_profile is None
            or self.manual_profile["target"] != self.target_position
        ):
            self.manual_profile = self._create_smooth_manual_profile(
                self.command_position,
                self.target_position,
                max_velocity,
                acceleration,
                deceleration,
                jerk,
            )

        profile = self.manual_profile
        duration = profile["duration"]
        elapsed = min(profile["elapsed"] + cycle_time, duration)
        if duration - elapsed <= cycle_time * 0.5:
            elapsed = duration
        profile["elapsed"] = elapsed

        if duration <= 0.0:
            self.command_position = self.target_position
            self.command_velocity = 0.0
            self.command_acceleration = 0.0
            self.manual_profile = None
            return self.command_position

        s = max(0.0, min(1.0, elapsed / duration))
        distance = profile["distance"]
        start = profile["start"]

        blend = 10.0 * s**3 - 15.0 * s**4 + 6.0 * s**5
        blend_velocity = 30.0 * s**2 - 60.0 * s**3 + 30.0 * s**4
        blend_acceleration = 60.0 * s - 180.0 * s**2 + 120.0 * s**3

        self.command_position = start + distance * blend
        self.command_velocity = distance * blend_velocity / duration
        self.command_acceleration = (
            distance * blend_acceleration / (duration * duration)
        )

        if elapsed >= duration:
            self.command_position = self.target_position
            self.command_velocity = 0.0
            self.command_acceleration = 0.0
            self.manual_profile = None

        return self.command_position

    def _create_smooth_manual_profile(
        self,
        start,
        target,
        max_velocity,
        acceleration,
        deceleration,
        jerk,
    ):
        distance = float(target) - float(start)
        abs_distance = abs(distance)
        if abs_distance <= 1e-9:
            duration = 0.0
        else:
            velocity_time = 1.875 * abs_distance / max(max_velocity, 1e-9)
            accel_time = math.sqrt(
                5.773502691896258 * abs_distance / max(acceleration, 1e-9)
            )
            decel_time = math.sqrt(
                5.773502691896258 * abs_distance / max(deceleration, 1e-9)
            )
            jerk_time = (60.0 * abs_distance / max(jerk, 1e-9)) ** (1.0 / 3.0)
            duration = max(velocity_time, accel_time, decel_time, jerk_time)

        return {
            "start": float(start),
            "target": float(target),
            "distance": distance,
            "duration": duration,
            "elapsed": 0.0,
        }

    def _update_trapezoid(self, cycle_time, max_velocity, acceleration, deceleration):
        error = self.target_position - self.command_position

        if abs(error) <= 1e-9 and abs(self.command_velocity) <= 1e-9:
            self.command_position = self.target_position
            self.command_velocity = 0.0
            self.command_acceleration = 0.0
            return self.command_position

        direction = 1.0 if error >= 0.0 else -1.0
        distance_remaining = abs(error)
        braking_distance = (
            self.command_velocity * self.command_velocity
        ) / (2.0 * max(deceleration, 1e-9))

        if distance_remaining <= braking_distance:
            desired_velocity = 0.0
        else:
            desired_velocity = direction * max_velocity

        delta_v = desired_velocity - self.command_velocity

        if abs(desired_velocity) > abs(self.command_velocity):
            velocity_limit = acceleration
        else:
            velocity_limit = deceleration

        max_delta_v = velocity_limit * cycle_time
        delta_v = max(min(delta_v, max_delta_v), -max_delta_v)

        previous_velocity = self.command_velocity
        self.command_velocity += delta_v
        self.command_acceleration = (
            self.command_velocity - previous_velocity
        ) / cycle_time
        next_position = self.command_position + self.command_velocity * cycle_time

        if self._crossed_target(next_position):
            self.command_position = self.target_position
            self.command_velocity = 0.0
            self.command_acceleration = 0.0
        else:
            self.command_position = next_position

        return self.command_position

    def _update_timed_trajectory(self, cycle_time):
        points = self.timed_points
        if not points:
            self.timed_active = False
            return self.command_position

        if self.timed_elapsed >= points[-1]["time_from_start"]:
            final = points[-1]
            self.command_position = final["position"]
            self.target_position = final["position"]
            self.command_velocity = final["velocity"] or 0.0
            self.command_acceleration = final["acceleration"] or 0.0
            self.timed_segment = max(0, len(points) - 2)
            self.timed_active = False
            return self.command_position

        self.timed_segment = self._find_timed_segment(self.timed_elapsed)
        start = points[self.timed_segment]
        end = points[self.timed_segment + 1]
        segment_start = start["time_from_start"]
        duration = end["time_from_start"] - segment_start
        local_time = self.timed_elapsed - segment_start

        (
            self.command_position,
            self.command_velocity,
            self.command_acceleration,
        ) = self._interpolate_timed_axis(start, end, local_time, duration)
        self.target_position = self.command_position
        self.timed_elapsed += cycle_time
        return self.command_position

    def _find_timed_segment(self, elapsed):
        for index in range(len(self.timed_points) - 1):
            if elapsed <= self.timed_points[index + 1]["time_from_start"]:
                return index
        return len(self.timed_points) - 2

    def _fill_missing_timed_velocities(self):
        points = self.timed_points
        if len(points) < 2:
            return

        slopes = []
        for start, end in zip(points, points[1:]):
            duration = max(
                end["time_from_start"] - start["time_from_start"],
                1e-9,
            )
            slopes.append((end["position"] - start["position"]) / duration)

        for index, point in enumerate(points):
            if point["velocity"] is not None:
                continue

            if index == 0 or index == len(points) - 1:
                point["velocity"] = 0.0
                continue

            previous_slope = slopes[index - 1]
            next_slope = slopes[index]
            if previous_slope == 0.0 or next_slope == 0.0:
                point["velocity"] = 0.0
            elif previous_slope * next_slope < 0.0:
                point["velocity"] = 0.0
            else:
                point["velocity"] = 0.5 * (previous_slope + next_slope)

    def _interpolate_timed_axis(self, start, end, local_time, duration):
        duration = max(float(duration), 1e-9)
        t = max(0.0, min(duration, float(local_time)))
        p0 = start["position"]
        p1 = end["position"]
        v0 = start["velocity"]
        v1 = end["velocity"]
        a0 = start["acceleration"]
        a1 = end["acceleration"]

        if v0 is None and v1 is None:
            ratio = t / duration
            position = p0 + (p1 - p0) * ratio
            velocity = (p1 - p0) / duration
            return position, velocity, 0.0

        v0 = v0 or 0.0
        v1 = v1 or 0.0
        if a0 is None or a1 is None:
            c0 = p0
            c1 = v0
            c2 = (3.0 * (p1 - p0) / duration - 2.0 * v0 - v1) / duration
            c3 = (2.0 * (p0 - p1) / duration + v0 + v1) / (
                duration * duration
            )
            position = c0 + c1 * t + c2 * t * t + c3 * t * t * t
            velocity = c1 + 2.0 * c2 * t + 3.0 * c3 * t * t
            acceleration = 2.0 * c2 + 6.0 * c3 * t
            return position, velocity, acceleration

        c0 = p0
        c1 = v0
        c2 = a0 / 2.0
        duration2 = duration * duration
        duration3 = duration2 * duration
        duration4 = duration3 * duration
        duration5 = duration4 * duration
        c3 = (
            20.0 * (p1 - p0)
            - (8.0 * v1 + 12.0 * v0) * duration
            - (3.0 * a0 - a1) * duration2
        ) / (2.0 * duration3)
        c4 = (
            30.0 * (p0 - p1)
            + (14.0 * v1 + 16.0 * v0) * duration
            + (3.0 * a0 - 2.0 * a1) * duration2
        ) / (2.0 * duration4)
        c5 = (
            12.0 * (p1 - p0)
            - (6.0 * v1 + 6.0 * v0) * duration
            - (a0 - a1) * duration2
        ) / (2.0 * duration5)
        position = (
            c0
            + c1 * t
            + c2 * t * t
            + c3 * t * t * t
            + c4 * t * t * t * t
            + c5 * t * t * t * t * t
        )
        velocity = (
            c1
            + 2.0 * c2 * t
            + 3.0 * c3 * t * t
            + 4.0 * c4 * t * t * t
            + 5.0 * c5 * t * t * t * t
        )
        acceleration = (
            2.0 * c2
            + 6.0 * c3 * t
            + 12.0 * c4 * t * t
            + 20.0 * c5 * t * t * t
        )
        return position, velocity, acceleration

    def _crossed_target(self, next_position):
        if self.target_position >= self.command_position:
            return next_position >= self.target_position

        return next_position <= self.target_position
