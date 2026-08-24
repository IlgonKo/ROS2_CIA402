import time

from motion_server.device_manager.profile_access import axis_device_profile
from motion_server.control.axis_units import trajectory_message_api_to_drive
from motion_server.control.trajectory_logging import (
    log_trajectory_debug,
    log_trajectory_snapshot,
)
from motion_server.handlers.status import axes_status_message
from motion_server.control.axis_operations import (
    actual_positions,
    axis_count,
    disabled_operation_axes,
    ensure_csp_mode,
    faulted_axes,
    hold_faulted_axes,
    reject_if_any_axis_disabled,
)
from motion_server.control.setpoint_output import command_csp_positions
from motion_server.api import public_command_name
from motion_server.api.encoder import status_data
from motion_server.api.decoder import selected_axes
from motion_server.app.state import inactive_trajectory_state
from motion_server.control.trajectory_verifier import (
    axis_timed_points,
    estimate_trajectory_duration,
    normalize_trajectory_points,
    validate_trajectory_limits,
)
from motion_server.failure import OperationException, UnsupportedOperationException


def reject_trajectory(state, message, inactive_trajectory_state):
    state["trajectory"] = inactive_trajectory_state("rejected")
    state["trajectory"]["message"] = message
    print(f"Ignored trajectory/move: {message}", flush=True)
    raise OperationException("system/axes/trajectory")

def fault_trajectory(state, message, inactive_trajectory_state):
    state["trajectory"] = inactive_trajectory_state("fault")
    state["trajectory"]["message"] = message
    print(f"Faulted trajectory/move: {message}", flush=True)
    raise OperationException("system/axes/trajectory")

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


def move_api(message, runtime, state, client):
    move(
        trajectory_message_api_to_drive(message, state),
        runtime,
        state,
        axis_count=axis_count,
        faulted_axes=faulted_axes,
        disabled_operation_axes=disabled_operation_axes,
        hold_faulted_axes=hold_faulted_axes,
        ensure_csp_mode=ensure_csp_mode,
        inactive_trajectory_state=inactive_trajectory_state,
    )
    return {"trajectory": dict(state["trajectory"])}


def move(
    message,
    runtime,
    state,
    *,
    axis_count,
    faulted_axes,
    disabled_operation_axes,
    hold_faulted_axes,
    ensure_csp_mode,
    inactive_trajectory_state,
):
    raw_axes = message.get("axes", [])
    axes = [int(axis) for axis in raw_axes] if raw_axes else list(range(axis_count(runtime)))
    try:
        points = normalize_trajectory_points(message.get("points", []), axes)
    except (TypeError, ValueError) as exc:
        reject_trajectory(state, str(exc), inactive_trajectory_state)
        return

    if any(axis < 0 or axis >= axis_count(runtime) for axis in axes):
        reject_trajectory(
            state,
            f"Invalid trajectory axes: {axes}",
            inactive_trajectory_state,
        )
        return
    if not points:
        reject_trajectory(
            state,
            "system/axes/trajectory requires at least one point",
            inactive_trajectory_state,
        )
        return

    faults = faulted_axes(runtime)
    if faults:
        hold_faulted_axes(runtime, state)
        runtime.sync_trajectory_to_actual_positions()
        reject_trajectory(state, f"faulted_axes={faults}", inactive_trajectory_state)
        return

    disabled_axes = disabled_operation_axes(runtime, axes)
    if disabled_axes:
        reject_trajectory(
            state,
            f"operation disabled axes={disabled_axes}",
            inactive_trajectory_state,
        )
        return

    ensure_csp_mode(runtime, state, axes)
    log_trajectory_debug(
        "before_command",
        runtime,
        state,
        axes,
        {
            "raw_points": points,
        },
    )

    if len(points) == 1:
        current = runtime.command_positions(axes)
        target = points[0]["positions"]
        duration = estimate_trajectory_duration(runtime, axes, current, target)
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
            runtime,
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

    validation_error = validate_trajectory_limits(runtime, axes, points)
    if validation_error:
        fault_trajectory(state, validation_error, inactive_trajectory_state)
        return

    log_trajectory_snapshot("start_request", runtime, state, axes, points)

    runtime.set_axis_trajectories(
        axes,
        [
            axis_timed_points(points, local_index)
            for local_index in range(len(axes))
        ],
    )
    for axis_index in axes:
        runtime.slaves[axis_index].rxpdo.mode_of_operation = (
            axis_device_profile(runtime, axis_index).CSP_MODE
        )
        runtime.slaves[axis_index].rxpdo.controlword = 0x000F

    log_trajectory_debug(
        "after_set_trajectory_move",
        runtime,
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
    log_trajectory_snapshot("start_active", runtime, state, axes, points)


def stop(message, runtime, state, client):
    command = public_command_name(message)
    mode = str(message.get("mode", "controlled")).strip().lower()
    if mode != "controlled":
        state["trajectory"] = inactive_trajectory_state("stop_rejected")
        state["trajectory"]["message"] = f"Unsupported stop mode: {mode}"
        print(f"Ignored unsupported trajectory/stop mode: {mode}", flush=True)
        raise UnsupportedOperationException(command, f"stop_mode:{mode}")

    state["trajectory"] = inactive_trajectory_state("stopped")
    try:
        axes = selected_axes(message, runtime, command)
    except Exception as exc:
        state["trajectory"] = inactive_trajectory_state("stop_rejected")
        state["trajectory"]["message"] = str(exc)
        print(f"Ignored {command}: {exc}", flush=True)
        raise
    if reject_if_any_axis_disabled(runtime, axes, client, command):
        state["trajectory"] = inactive_trajectory_state("stop_rejected")
        state["trajectory"]["message"] = "Axis operation is disabled."
        return

    ensure_csp_mode(runtime, state, axes)
    positions = actual_positions(runtime)
    state["target_positions"] = positions
    runtime.set_target_positions(positions)
    runtime.sync_trajectory_to_actual_positions()
    command_csp_positions(runtime, positions, axes)
    print(
        "Received trajectory/stop: "
        f"mode={mode} hold_positions={positions}",
        flush=True,
    )


def status(message, runtime, state, client):
    return status_data(axes_status_message(runtime, state, client["id"]))


def update_active(runtime, state):
    trajectory = state.get("trajectory", {})
    if not trajectory.get("active"):
        return

    axes = trajectory["axes"]
    points = trajectory["points"]
    positions = list(state["target_positions"])
    progress = runtime.trajectory_progress(axes)
    elapsed = progress["elapsed"]
    active = progress["active"]
    segment = progress["segment"]
    for axis_index, position in progress["positions"].items():
        positions[axis_index] = position

    state["target_positions"] = positions
    trajectory["time_from_start"] = elapsed
    trajectory["segment"] = segment

    if not active or elapsed >= points[-1]["time_from_start"]:
        log_trajectory_snapshot(
            "complete_before_clear",
            runtime,
            state,
            axes,
            points,
            {
                "elapsed": f"{elapsed:.6f}",
                "active": active,
            },
        )
        log_trajectory_debug(
            "before_complete",
            runtime,
            state,
            axes,
            {
                "elapsed": elapsed,
                "duration": points[-1]["time_from_start"],
                "active": active,
                "final_positions": points[-1]["positions"],
            },
        )
        completed = runtime.complete_trajectory(
            axes,
            points[-1]["positions"],
        )
        for axis_index, final_position in completed.items():
            positions[axis_index] = final_position
        state["target_positions"] = positions
        trajectory["active"] = False
        trajectory["state"] = "complete"
        trajectory["segment"] = max(0, len(points) - 2)
        state["last_trajectory_complete_time"] = time.monotonic()
        log_trajectory_snapshot(
            "complete",
            runtime,
            state,
            axes,
            points,
            {"elapsed": f"{elapsed:.6f}"},
        )
        log_trajectory_debug(
            "after_complete",
            runtime,
            state,
            axes,
            {
                "elapsed": elapsed,
                "duration": points[-1]["time_from_start"],
                "final_positions": points[-1]["positions"],
            },
        )
