import math


def axis_timed_points(points, local_index):
    axis_points = []
    for point in points:
        axis_point = {
            "position": point["positions"][local_index],
            "time_from_start": point["time_from_start"],
        }
        if "velocities" in point:
            axis_point["velocity"] = point["velocities"][local_index]
        if "accelerations" in point:
            axis_point["acceleration"] = point["accelerations"][local_index]
        axis_points.append(axis_point)
    return axis_points

def normalize_trajectory_points(raw_points, axes):
    points = []
    expected = len(axes)
    for point_index, raw_point in enumerate(raw_points):
        positions = [float(value) for value in raw_point.get("positions", [])]
        if len(positions) < expected:
            raise ValueError(
                f"point {point_index} positions length {len(positions)} "
                f"is smaller than axes length {expected}"
            )

        point = {
            "positions": positions[:expected],
            "time_from_start": float(raw_point.get("time_from_start", 0.0)),
        }
        velocities = raw_point.get("velocities", None)
        if velocities is not None:
            if len(velocities) < expected:
                raise ValueError(
                    f"point {point_index} velocities length {len(velocities)} "
                    f"is smaller than axes length {expected}"
                )
            point["velocities"] = [
                float(value)
                for value in velocities[:expected]
            ]
        accelerations = raw_point.get("accelerations", None)
        if accelerations is not None:
            if len(accelerations) < expected:
                raise ValueError(
                    f"point {point_index} accelerations length {len(accelerations)} "
                    f"is smaller than axes length {expected}"
                )
            point["accelerations"] = [
                float(value)
                for value in accelerations[:expected]
            ]
        points.append(point)

    previous_time = -1e-9
    for point_index, point in enumerate(points):
        point_time = point["time_from_start"]
        if point_time < previous_time:
            raise ValueError(
                f"point {point_index} time_from_start is not monotonic"
            )
        previous_time = point_time
    return points

def estimate_trajectory_duration(master, axes, current, target):
    duration = 0.0
    for axis_index, start, end in zip(axes, current, target):
        distance = abs(float(end) - float(start))
        max_velocity = max(
            float(master.slaves[axis_index].motion_limits.max_velocity)
            * master.csp_counts_per_unit,
            1e-9,
        )
        acceleration_limit = max(
            float(master.slaves[axis_index].motion_limits.acceleration)
            * master.csp_counts_per_unit,
            1e-9,
        )
        deceleration_limit = max(
            float(master.slaves[axis_index].motion_limits.deceleration)
            * master.csp_counts_per_unit,
            1e-9,
        )
        accel_limit = min(acceleration_limit, deceleration_limit)
        duration = max(
            duration,
            1.875 * distance / max_velocity,
            (5.773502691896258 * distance / accel_limit) ** 0.5,
        )
    return max(duration, master.cycle_time)

def required_segment_duration_for_axis(
    master,
    axis_index,
    previous,
    current,
    local_index,
    initial_dt,
):
    distance = abs(
        float(current["positions"][local_index])
        - float(previous["positions"][local_index])
    )
    if distance <= 1e-9:
        return max(float(initial_dt), master.cycle_time)

    velocity_limit = max(
        float(master.slaves[axis_index].motion_limits.max_velocity)
        * master.csp_counts_per_unit,
        1e-9,
    )
    acceleration_limit = max(
        float(master.slaves[axis_index].motion_limits.acceleration)
        * master.csp_counts_per_unit,
        1e-9,
    )
    deceleration_limit = max(
        float(master.slaves[axis_index].motion_limits.deceleration)
        * master.csp_counts_per_unit,
        1e-9,
    )
    accel_limit = min(acceleration_limit, deceleration_limit)

    duration = max(
        float(initial_dt),
        1.875 * distance / velocity_limit,
        math.sqrt(5.773502691896258 * distance / accel_limit),
        master.cycle_time,
    )

    if "velocities" not in previous and "velocities" not in current:
        return duration

    for _ in range(24):
        peak_velocity, peak_acceleration = sample_segment_peaks(
            previous,
            current,
            local_index,
            duration,
        )
        velocity_ratio = peak_velocity / velocity_limit
        acceleration_ratio = peak_acceleration / accel_limit
        ratio = max(velocity_ratio, math.sqrt(acceleration_ratio), 1.0)
        if ratio <= 1.0001:
            return duration
        duration *= min(max(ratio, 1.02), 2.0)

    return duration

def sample_segment_peaks(previous, current, local_index, duration):
    duration = max(float(duration), 1e-9)
    p0 = float(previous["positions"][local_index])
    p1 = float(current["positions"][local_index])
    v0 = trajectory_point_value(previous, "velocities", local_index, 0.0)
    v1 = trajectory_point_value(current, "velocities", local_index, 0.0)
    a0 = trajectory_point_value(previous, "accelerations", local_index, 0.0)
    a1 = trajectory_point_value(current, "accelerations", local_index, 0.0)

    duration2 = duration * duration
    duration3 = duration2 * duration
    duration4 = duration3 * duration
    duration5 = duration4 * duration
    c1 = v0
    c2 = a0 / 2.0
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

    peak_velocity = 0.0
    peak_acceleration = 0.0
    for sample_index in range(65):
        t = duration * sample_index / 64.0
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
        peak_velocity = max(peak_velocity, abs(velocity))
        peak_acceleration = max(peak_acceleration, abs(acceleration))

    return peak_velocity, peak_acceleration

def trajectory_point_value(point, key, local_index, default):
    values = point.get(key)
    if values is None:
        return default
    return float(values[local_index])

def validate_trajectory_limits(master, axes, points):
    for point_index, (previous, current) in enumerate(zip(points, points[1:]), start=1):
        dt = current["time_from_start"] - previous["time_from_start"]
        if dt <= 0.0:
            return (
                f"trajectory segment {point_index} time must be greater than zero"
            )

        for local_index, axis_index in enumerate(axes):
            start = previous["positions"][local_index]
            end = current["positions"][local_index]
            velocity_limit = (
                float(master.slaves[axis_index].motion_limits.max_velocity)
                * master.csp_counts_per_unit
            )
            acceleration_limit = (
                float(master.slaves[axis_index].motion_limits.acceleration)
                * master.csp_counts_per_unit
            )
            deceleration_limit = (
                float(master.slaves[axis_index].motion_limits.deceleration)
                * master.csp_counts_per_unit
            )
            required_dt = required_segment_duration_for_axis(
                master,
                axis_index,
                previous,
                current,
                local_index,
                master.cycle_time,
            )
            if required_dt > dt + 1e-9:
                return (
                    f"axis {axis_index} trajectory segment {point_index} "
                    "exceeds motion limits: "
                    f"requested_dt={dt:.6f}s required_dt={required_dt:.6f}s "
                    f"start={start:.3f} end={end:.3f} "
                    f"velocity_limit={velocity_limit:.3f} "
                    f"accel_limit={acceleration_limit:.3f} "
                    f"decel_limit={deceleration_limit:.3f}"
                )

            for point in (previous, current):
                velocities = point.get("velocities")
                if velocities is not None:
                    required = abs(velocities[local_index])
                    if required > velocity_limit + 1e-9:
                        return (
                            f"axis {axis_index} waypoint velocity limit exceeded: "
                            f"required={required:.3f} limit={velocity_limit:.3f}"
                        )

                accelerations = point.get("accelerations")
                if accelerations is not None:
                    required_accel = accelerations[local_index]
                    accel_limit = (
                        acceleration_limit
                        if required_accel >= 0.0
                        else deceleration_limit
                    )
                    if abs(required_accel) > accel_limit + 1e-9:
                        return (
                            f"axis {axis_index} waypoint acceleration limit exceeded: "
                            f"required={required_accel:.3f} limit={accel_limit:.3f}"
                        )

            if "velocities" in previous or "velocities" in current:
                start_velocity = previous.get(
                    "velocities",
                    [0.0 for _ in previous["positions"]],
                )[local_index]
                end_velocity = current.get(
                    "velocities",
                    [0.0 for _ in current["positions"]],
                )[local_index]
                a2 = (
                    3.0 * (end - start) / dt
                    - 2.0 * start_velocity
                    - end_velocity
                ) / dt
                a3 = (
                    2.0 * (start - end) / dt
                    + start_velocity
                    + end_velocity
                ) / (dt * dt)
                for accel in (2.0 * a2, 2.0 * a2 + 6.0 * a3 * dt):
                    accel_limit = acceleration_limit if accel >= 0.0 else deceleration_limit
                    if abs(accel) > accel_limit + 1e-9:
                        return (
                            f"axis {axis_index} segment acceleration limit exceeded: "
                            f"required={accel:.3f} limit={accel_limit:.3f}"
                        )
    return ""
