import time

from motion_server.device_manager.axis_diagnostics import format_diagnostics


def format_latest_cycle_value(cycle_stats, name):
    value = cycle_stats.latest.get(name)
    if value is None:
        return "None"
    return f"{value * 1000.0:.3f}"


def velocity_anomaly_dc_snapshot(runtime, cycle_stats, dc_config):
    if dc_config is None or not dc_config.enabled:
        return "dc_enabled=False"
    cycle_time_ns = max(1, int(round(float(runtime.cycle_time) * 1_000_000_000.0)))
    phase_offset_ns = int(dc_config.phase_offset_ns)
    target_phase_ns = (cycle_time_ns - phase_offset_ns) % cycle_time_ns
    tx_dc_time_ns = getattr(runtime, "last_tx_dc_time_ns", None)
    direct_tx_dc_time_ns = getattr(runtime, "last_direct_tx_dc_time_ns", None)
    actual_phase_ns = None
    phase_error_ns = None
    if tx_dc_time_ns is not None:
        actual_phase_ns = int(tx_dc_time_ns) % cycle_time_ns
        phase_error_ns = actual_phase_ns - target_phase_ns
        half_cycle_ns = cycle_time_ns // 2
        if phase_error_ns > half_cycle_ns:
            phase_error_ns -= cycle_time_ns
        elif phase_error_ns < -half_cycle_ns:
            phase_error_ns += cycle_time_ns

    direct_phase_ns = None
    if direct_tx_dc_time_ns is not None:
        direct_phase_ns = int(direct_tx_dc_time_ns) % cycle_time_ns

    def ns_to_ms(value):
        return "None" if value is None else f"{value / 1_000_000.0:.3f}"

    return (
        f"dc_phase_ms={format_latest_cycle_value(cycle_stats, 'dc_phase_error')} "
        f"dc_corr_ms={format_latest_cycle_value(cycle_stats, 'dc_phase_correction')} "
        f"tx_prepare_ms={format_latest_cycle_value(cycle_stats, 'tx_prepare')} "
        f"send_call_ms={format_latest_cycle_value(cycle_stats, 'send_call')} "
        f"pdo_io_ms={format_latest_cycle_value(cycle_stats, 'pdo_io')} "
        f"tx_gap_ms={format_latest_cycle_value(cycle_stats, 'tx_gap')} "
        f"tx_phase_ms={ns_to_ms(actual_phase_ns)} "
        f"target_phase_ms={ns_to_ms(target_phase_ns)} "
        f"phase_err_calc_ms={ns_to_ms(phase_error_ns)} "
        f"direct_tx_phase_ms={ns_to_ms(direct_phase_ns)} "
        f"dc_tx_est_delta_ms={format_latest_cycle_value(cycle_stats, 'dc_tx_estimation_delta')}"
    )


def record_pre_log_snapshot(runtime, state, cycle_stats):
    if not runtime.logger.history_enabled:
        return

    cycle_time_ns = max(1, int(round(float(runtime.cycle_time) * 1_000_000_000.0)))
    tx_dc_time_ns = getattr(runtime, "last_tx_dc_time_ns", None)
    tx_phase_ms = None
    if tx_dc_time_ns is not None:
        tx_phase_ms = (int(tx_dc_time_ns) % cycle_time_ns) / 1_000_000.0

    runtime.logger.record_snapshot(
        {
            "time": time.monotonic(),
            "targets": [
                int(slave.rxpdo.target_position)
                for slave in runtime.slaves
            ],
            "actual_positions": [
                int(slave.txpdo.actual_position)
                for slave in runtime.slaves
            ],
            "actual_velocities": [
                float(slave.txpdo.actual_velocity)
                for slave in runtime.slaves
            ],
            "statuswords": [
                int(slave.txpdo.statusword)
                for slave in runtime.slaves
            ],
            "modes": [
                int(slave.rxpdo.mode_of_operation)
                for slave in runtime.slaves
            ],
            "command_velocities": [
                (
                    float(generator.command_velocity)
                    / max(
                        float(runtime.axis_position_counts_per_api_unit(axis_index)),
                        1e-9,
                    )
                )
                for axis_index, generator in enumerate(
                    runtime.trajectory_generators
                )
            ],
            "command_positions": [
                float(generator.command_position)
                for generator in runtime.trajectory_generators
            ],
            "wkc": int(runtime.wkc),
            "expected_wkc": int(runtime.expected_wkc()),
            "tx_gap_ms": cycle_stats.latest.get("tx_gap", 0.0) * 1000.0,
            "tx_phase_ms": tx_phase_ms,
        }
    )


def format_pre_history_for_axes(runtime, axes, sample_count=10):
    history = list(runtime.logger.history)
    if not history:
        return "PRE_HISTORY=None"

    samples = history[-sample_count:]
    parts = []
    for axis_index in axes:
        previous_target = None
        entries = []
        for sample in samples:
            target = sample["targets"][axis_index]
            delta = None if previous_target is None else target - previous_target
            previous_target = target
            phase = sample.get("tx_phase_ms")
            phase_text = "None" if phase is None else f"{phase:.3f}"
            entries.append(
                f"{target}/{delta if delta is not None else 'NA'}"
                f"@{phase_text}"
            )
        parts.append(f"A{axis_index}=[" + ",".join(entries) + "]")

    return "PRE_HISTORY " + " ".join(parts)


def position_feedback_lag(runtime, axis_index, feedback_position):
    history = list(runtime.logger.history)
    if not history:
        return None

    best = None
    last_index = len(history) - 1
    for sample_index, sample in enumerate(history):
        target = int(sample["targets"][axis_index])
        error = float(feedback_position) - float(target)
        candidate = {
            "lag": last_index - sample_index,
            "target": target,
            "error": error,
            "abs_error": abs(error),
            "tx_phase_ms": sample.get("tx_phase_ms"),
        }
        if best is None or candidate["abs_error"] < best["abs_error"]:
            best = candidate

    return best


def format_position_feedback_lag(runtime, state, axes):
    parts = []
    for axis_index in axes:
        generator = runtime.trajectory_generators[axis_index]
        feedback_position = float(runtime.slaves[axis_index].txpdo.actual_position)
        command_position = float(generator.command_position)
        command_diff = feedback_position - command_position
        lag = position_feedback_lag(runtime, axis_index, feedback_position)
        if lag is None:
            parts.append(
                f"A{axis_index}:FB={feedback_position:.0f},"
                f"CP={command_position:.3f},DIFF={command_diff:.3f},LAG=None"
            )
            continue

        phase = lag.get("tx_phase_ms")
        phase_text = "None" if phase is None else f"{phase:.3f}"
        parts.append(
            f"A{axis_index}:FB={feedback_position:.0f},"
            f"CP={command_position:.3f},"
            f"DIFF={command_diff:.3f},"
            f"LAG={lag['lag']},"
            f"LAG_TARGET={lag['target']},"
            f"LAG_ERR={lag['error']:.3f},"
            f"LAG_PHASE_MS={phase_text}"
        )

    return "POS_FB_LAG " + " | ".join(parts)


def log_position_feedback_lag(runtime, state):
    config = runtime.logger.config.position_feedback_lag
    if not config.enabled:
        return

    now = time.monotonic()
    last_log_time = state.get("position_feedback_lag_last_log_time", 0.0)
    if now - last_log_time < config.period:
        return

    axes = list(state.get("trajectory", {}).get("axes", []))
    if not axes:
        return

    runtime.logger.event(
        "Position feedback lag: "
        f"trajectory_state={state.get('trajectory', {}).get('state')} "
        f"trajectory_time={state.get('trajectory', {}).get('time_from_start', 0.0):.3f} "
        f"{format_position_feedback_lag(runtime, state, axes)}",
    )
    state["position_feedback_lag_last_log_time"] = now


def log_velocity_anomalies(runtime, state, cycle_stats, dc_config=None):
    config = runtime.logger.config.velocity_anomaly
    if not config.enabled:
        return

    now = time.monotonic()
    last_log_time = state.get("velocity_anomaly_last_log_time", 0.0)
    if now - last_log_time < config.period:
        return

    previous_actual = state.get("velocity_anomaly_previous_actual")
    current_actual = [
        float(slave.txpdo.actual_velocity)
        for slave in runtime.slaves
    ]
    state["velocity_anomaly_previous_actual"] = current_actual
    if previous_actual is None:
        return

    active_axes = set(state.get("trajectory", {}).get("axes", []))
    dc_phase_values = cycle_stats.values.get("dc_phase_error", {})
    latest_dc_phase_ms = None
    if dc_phase_values.get("count"):
        latest_dc_phase_ms = (
            dc_phase_values["sum"] / dc_phase_values["count"]
        ) * 1000.0

    anomalies = []
    anomaly_axes = []
    for axis_index, actual_velocity in enumerate(current_actual):
        if axis_index not in active_axes:
            continue

        generator = runtime.trajectory_generators[axis_index]
        scale = max(
            float(runtime.axis_position_counts_per_api_unit(axis_index)),
            1e-9,
        )
        command_velocity = (
            float(generator.command_velocity)
            / scale
        )
        velocity_error = actual_velocity - command_velocity
        velocity_jump = actual_velocity - previous_actual[axis_index]
        if (
            abs(velocity_error) < config.error_threshold
            and abs(velocity_jump) < config.jump_threshold
        ):
            continue

        anomalies.append(
            "A"
            f"{axis_index}:"
            f"AV={actual_velocity:.3f},"
            f"CV={command_velocity:.3f},"
            f"ERR={velocity_error:.3f},"
            f"JUMP={velocity_jump:.3f},"
            f"AP={runtime.slaves[axis_index].txpdo.actual_position},"
            f"CP={generator.command_position:.3f},"
            f"TP={generator.target_position:.3f}"
        )
        anomaly_axes.append(axis_index)

    if anomalies:
        runtime.logger.event(
            "Velocity anomaly: "
            f"{' | '.join(anomalies)} "
            f"trajectory_state={state.get('trajectory', {}).get('state')} "
            f"trajectory_time={state.get('trajectory', {}).get('time_from_start', 0.0):.3f} "
            f"dc_phase_avg_ms={latest_dc_phase_ms} "
            f"{format_position_feedback_lag(runtime, state, anomaly_axes)} "
            f"{velocity_anomaly_dc_snapshot(runtime, cycle_stats, dc_config)} "
            f"{format_pre_history_for_axes(runtime, anomaly_axes)}",
            include_history=False,
        )
        state["velocity_anomaly_last_log_time"] = now


def log_csp_command_step_anomalies(runtime, state):
    if not runtime.logger.config.csp_command_step.enabled:
        return

    trajectory = state.get("trajectory", {})
    events = getattr(runtime, "last_csp_command_steps", [])
    for event in events:
        axis_index = int(event["axis"])
        scale = max(
            float(runtime.axis_position_counts_per_api_unit(axis_index)),
            1e-9,
        )
        generator = runtime.trajectory_generators[axis_index]
        timed_start = None
        timed_end = None
        if generator.timed_points:
            timed_start = generator.timed_points[0]
            timed_end = generator.timed_points[-1]
        actual_position = runtime.slaves[axis_index].txpdo.actual_position
        runtime.logger.event(
            "CSP command step anomaly: "
            f"axis={axis_index} "
            f"previous_sent_position={event['previous_sent_position']} "
            f"sent_position={event['sent_position']} "
            f"sent_step={event['sent_step']} "
            f"expected_step={event['expected_step']:.3f} "
            f"step_error={event['step_error']:.3f} "
            f"previous_command_position={event['previous_command_position']:.3f} "
            f"command_position={event['command_position']:.3f} "
            f"command_step={event['command_step']:.3f} "
            f"command_velocity={event['command_velocity'] / scale:.3f} "
            f"actual_position={actual_position} "
            f"position_gap={event['command_position'] - actual_position:.3f} "
            f"target_position={generator.target_position:.3f} "
            f"timed_active={generator.timed_active} "
            f"timed_elapsed={generator.timed_elapsed:.6f} "
            f"timed_segment={generator.timed_segment} "
            f"timed_start={timed_start} "
            f"timed_end={timed_end} "
            f"trajectory_state={trajectory.get('state')} "
            f"trajectory_time={trajectory.get('time_from_start', 0.0):.3f}",
        )

    output_events = getattr(runtime, "last_csp_output_steps", [])
    for event in output_events:
        axis_index = int(event["axis"])
        scale = max(
            float(runtime.axis_position_counts_per_api_unit(axis_index)),
            1e-9,
        )
        generator = runtime.trajectory_generators[axis_index]
        actual_position = runtime.slaves[axis_index].txpdo.actual_position
        runtime.logger.event(
            "CSP output buffer step anomaly: "
            f"axis={axis_index} "
            f"previous_output_target={event['previous_output_target']} "
            f"output_target={event['output_target']} "
            f"output_step={event['output_step']} "
            f"command_target={event['command_target']} "
            f"expected_step={event['expected_step']:.3f} "
            f"step_error={event['step_error']:.3f} "
            f"command_position={event['command_position']:.3f} "
            f"command_velocity={event['command_velocity'] / scale:.3f} "
            f"actual_position={actual_position} "
            f"position_gap={event['command_position'] - actual_position:.3f} "
            f"target_position={generator.target_position:.3f} "
            f"timed_active={generator.timed_active} "
            f"timed_elapsed={generator.timed_elapsed:.6f} "
            f"timed_segment={generator.timed_segment} "
            f"trajectory_state={trajectory.get('state')} "
            f"trajectory_time={trajectory.get('time_from_start', 0.0):.3f}",
        )


def log_status_if_due(runtime, state, last_status_log_time):
    config = runtime.logger.config.status
    if not config.enabled:
        return last_status_log_time
    if config.period <= 0.0:
        return last_status_log_time

    now = time.monotonic()
    if now - last_status_log_time < config.period:
        return last_status_log_time

    axis_statuses = []
    for axis_index, slave in enumerate(runtime.slaves):
        axis_statuses.append(
            f"A{axis_index}:"
            f"MODE={state['motion_modes'][axis_index].upper()} "
            f"SW=0x{slave.txpdo.statusword:04X} "
            f"TP={slave.rxpdo.target_position:.3f} "
            f"CMD={state['target_positions'][axis_index]:.3f} "
            f"CSP_CV={runtime.trajectory_generators[axis_index].command_velocity:.3f} "
            f"CSP_CP={runtime.trajectory_generators[axis_index].command_position:.3f} "
            f"AP={slave.txpdo.actual_position} "
            f"AV={slave.txpdo.actual_velocity} "
            f"{format_diagnostics(runtime.last_diagnostics[axis_index])}"
        )

    runtime.logger.event(
        "Axis status: "
        f"WKC={runtime.wkc}/{runtime.expected_wkc()} "
        + " | ".join(axis_statuses),
    )
    return now
