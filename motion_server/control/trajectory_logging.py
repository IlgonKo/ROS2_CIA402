import json
import time

from motion_server.config import (
    TRAJECTORY_DEBUG_LOGS,
    TRAJECTORY_SNAPSHOT_LOGS,
)


def trajectory_debug_snapshot(runtime, state, axes):
    snapshots = []
    trajectory = state.get("trajectory", {})
    for axis_index in axes:
        generator = runtime.trajectory_generators[axis_index]
        timed_start = None
        timed_end = None
        if generator.timed_points:
            timed_start = generator.timed_points[0]
            timed_end = generator.timed_points[-1]
        snapshots.append(
            {
                "axis": axis_index,
                "rxpdo_target": int(runtime.slaves[axis_index].rxpdo.target_position),
                "actual": int(runtime.slaves[axis_index].txpdo.actual_position),
                "command": round(float(generator.command_position), 3),
                "target": round(float(generator.target_position), 3),
                "velocity": round(float(generator.command_velocity), 3),
                "timed_active": bool(generator.timed_active),
                "timed_elapsed": round(float(generator.timed_elapsed), 6),
                "timed_segment": int(generator.timed_segment),
                "timed_start": timed_start,
                "timed_end": timed_end,
            }
        )
    return {
        "trajectory_active": bool(trajectory.get("active", False)),
        "trajectory_state": trajectory.get("state"),
        "trajectory_time": round(float(trajectory.get("time_from_start", 0.0)), 6),
        "axes": snapshots,
    }


def log_trajectory_debug(label, runtime, state, axes, extra=None):
    if not TRAJECTORY_DEBUG_LOGS:
        return

    payload = trajectory_debug_snapshot(runtime, state, axes)
    if extra:
        payload.update(extra)
    print(
        f"Trajectory debug {label}: {json.dumps(payload, sort_keys=True)}",
        flush=True,
    )


def log_trajectory_snapshot(label, runtime, state, axes, points=None, extra=None):
    if not TRAJECTORY_SNAPSHOT_LOGS:
        return

    axis_parts = []
    for axis_index in axes:
        scale = max(
            float(runtime.axis_position_counts_per_api_unit(axis_index)),
            1e-9,
        )
        slave = runtime.slaves[axis_index]
        generator = runtime.trajectory_generators[axis_index]
        command_position = float(generator.command_position)
        actual_position = float(slave.txpdo.actual_position)
        command_velocity = float(generator.command_velocity) / scale
        axis_parts.append(
            "A"
            f"{axis_index}:"
            f"SW=0x{int(slave.txpdo.statusword):04X},"
            f"MD={int(slave.txpdo.mode_of_operation_display)},"
            f"AP={actual_position:.3f},"
            f"AV={float(slave.txpdo.actual_velocity):.3f},"
            f"CP={command_position:.3f},"
            f"CV={command_velocity:.3f},"
            f"GAP={command_position - actual_position:.3f}"
        )

    now = time.monotonic()
    last_complete_time = state.get("last_trajectory_complete_time")
    since_complete = (
        "None"
        if last_complete_time is None
        else f"{now - last_complete_time:.3f}"
    )
    duration = None
    target = None
    if points:
        duration = points[-1].get("time_from_start")
        target = points[-1].get("positions")

    details = [
        f"seq={state.get('trajectory_sequence', 0)}",
        f"since_complete_s={since_complete}",
        f"duration={duration}",
        f"target={target}",
    ]
    if extra:
        details.extend(f"{key}={value}" for key, value in extra.items())

    print(
        f"Trajectory snapshot {label}: "
        f"{' '.join(details)} "
        f"{' | '.join(axis_parts)}",
        flush=True,
    )
