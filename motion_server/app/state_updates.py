def update_derived_velocities(runtime, state, now):
    positions = [
        float(slave.txpdo.actual_position)
        for slave in runtime.slaves
    ]
    previous_time = state.get("derived_velocity_time")
    previous_positions = state.get("derived_velocity_positions")

    if previous_time is None or previous_positions is None:
        state["derived_velocities"] = [0.0 for _ in positions]
    else:
        dt = max(now - previous_time, 1e-9)
        raw_velocities = [
            (position - previous_position) / dt
            for position, previous_position in zip(positions, previous_positions)
        ]
        alpha = state["derived_velocity_alpha"]
        state["derived_velocities"] = [
            previous_velocity * (1.0 - alpha) + raw_velocity * alpha
            for previous_velocity, raw_velocity in zip(
                state["derived_velocities"],
                raw_velocities,
            )
        ]

    state["derived_velocity_time"] = now
    state["derived_velocity_positions"] = positions
