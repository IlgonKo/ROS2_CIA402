import time

from axis_server.config import CSP_MODE, ROS_BRIDGE_COMMAND_LOGS
from axis_server.diagnostics import (
    log_trajectory_debug,
    log_trajectory_snapshot,
)
from motion.trajectory_verifier import (
    axis_timed_points,
    estimate_trajectory_duration,
    normalize_trajectory_points,
    validate_trajectory_limits,
)


def reject_trajectory(state, message, inactive_trajectory_state):
    state["trajectory"] = inactive_trajectory_state("rejected")
    state["trajectory"]["message"] = message
    print(f"Ignored trajectory/move: {message}", flush=True)

def fault_trajectory(state, message, inactive_trajectory_state):
    state["trajectory"] = inactive_trajectory_state("fault")
    state["trajectory"]["message"] = message
    print(f"Faulted trajectory/move: {message}", flush=True)

def same_trajectory_target(active_trajectory, axes, points, tolerance=1e-6):
    if not active_trajectory.get("active"):
        return False
    if active_trajectory.get("axes") != axes:
        return False

    active_points = active_trajectory.get("points") or []
    if not active_points or not points:
        return False

    active_target = active_points[-1].get("positions", [])
    target = points[-1].get("positions", [])
    if len(active_target) != len(target):
        return False

    return all(
        abs(float(active_value) - float(target_value)) <= tolerance
        for active_value, target_value in zip(active_target, target)
    )

def handle_trajectory_command(
    message,
    master,
    state,
    *,
    axis_count,
    faulted_axes,
    hold_faulted_axes,
    ensure_csp_mode,
    inactive_trajectory_state,
):
    raw_axes = message.get("axes", [])
    axes = [int(axis) for axis in raw_axes] if raw_axes else list(range(axis_count(master)))
    try:
        points = normalize_trajectory_points(message.get("points", []), axes)
    except (TypeError, ValueError) as exc:
        reject_trajectory(state, str(exc), inactive_trajectory_state)
        return

    if any(axis < 0 or axis >= axis_count(master) for axis in axes):
        reject_trajectory(
            state,
            f"Invalid trajectory axes: {axes}",
            inactive_trajectory_state,
        )
        return
    if not points:
        reject_trajectory(
            state,
            "trajectory/move requires at least one point",
            inactive_trajectory_state,
        )
        return

    faults = faulted_axes(master)
    if faults:
        hold_faulted_axes(master, state)
        master.sync_trajectory_to_actual_positions()
        reject_trajectory(state, f"faulted_axes={faults}", inactive_trajectory_state)
        return

    ensure_csp_mode(master, state, axes)
    log_trajectory_debug(
        "before_command",
        master,
        state,
        axes,
        {
            "raw_points": points,
        },
    )

    if len(points) == 1:
        current = [
            float(master.trajectory_generators[axis_index].command_position)
            for axis_index in axes
        ]
        target = points[0]["positions"]
        duration = estimate_trajectory_duration(master, axes, current, target)
        points = [
            {
                "positions": current,
                "time_from_start": 0.0,
            },
            {
                "positions": target,
                "time_from_start": duration,
            },
        ]

        log_trajectory_debug(
            "expanded_single_point",
            master,
            state,
            axes,
            {
                "expanded_points": points,
            },
        )

    if same_trajectory_target(state.get("trajectory", {}), axes, points):
        print(
            "Ignored duplicate active trajectory/move: "
            f"axes={axes} target={points[-1]['positions']}",
            flush=True,
        )
        return

    validation_error = validate_trajectory_limits(master, axes, points)
    if validation_error:
        fault_trajectory(state, validation_error, inactive_trajectory_state)
        return

    log_trajectory_snapshot("start_request", master, state, axes, points)

    for local_index, axis_index in enumerate(axes):
        master.trajectory_generators[axis_index].set_trajectory_move(
            axis_timed_points(points, local_index)
        )
        master.slaves[axis_index].rxpdo.mode_of_operation = CSP_MODE
        master.slaves[axis_index].rxpdo.controlword = 0x000F

    log_trajectory_debug(
        "after_set_trajectory_move",
        master,
        state,
        axes,
        {
            "points": points,
        },
    )

    state["trajectory"] = {
        "active": True,
        "state": "running",
        "axes": axes,
        "segment": 0,
        "time_from_start": 0.0,
        "points": points,
        "start_time": time.monotonic(),
        "message": "",
    }
    state["trajectory_sequence"] = state.get("trajectory_sequence", 0) + 1
    log_trajectory_snapshot("start_active", master, state, axes, points)
    if ROS_BRIDGE_COMMAND_LOGS:
        print(
            "Received trajectory/move: "
            f"axes={axes} points={len(points)} "
            f"duration={points[-1]['time_from_start']:.3f}",
            flush=True,
        )
