"""Motion Server startup summary field contract."""


def startup_summary_fields(
    server_config,
    ethercat_config,
    motion_config,
    axis_count,
):
    fields = [
        ("backend", ethercat_config.backend.value),
        ("server_mode", server_config.mode.value),
        ("axes", int(axis_count)),
        ("cycle_time", ethercat_config.cycle.period),
        ("spin_wait_time", ethercat_config.cycle.spin_wait_time),
        ("motion_mode", motion_config.initial_motion_mode),
        ("dc_enabled", bool(ethercat_config.dc.enabled)),
    ]

    if ethercat_config.dc.enabled:
        phase_lock = bool(ethercat_config.dc.phase_lock)
        fields.append(("dc_phase_lock", phase_lock))
        if phase_lock:
            fields.extend((
                ("dc_absolute_shift", bool(ethercat_config.dc.absolute_shift)),
                ("dc_phase_offset_ns", int(ethercat_config.dc.phase_offset_ns)),
                ("dc_phase_kp", ethercat_config.dc.phase_kp),
                ("dc_phase_ki", ethercat_config.dc.phase_ki),
                (
                    "dc_phase_max_correction",
                    ethercat_config.dc.phase_max_correction,
                ),
            ))

    if motion_config.initial_motion_mode == "csp":
        fields.extend((
            ("csp_profile", motion_config.csp_profile.value),
            ("csp_jerk", motion_config.csp_jerk),
            (
                "csp_interpolation_mode",
                motion_config.csp_interpolation_mode.name.lower(),
            ),
            ("csp_velocity_offset", bool(motion_config.csp_velocity_offset)),
        ))

    return tuple(fields)


def format_startup_summary(
    server_config,
    ethercat_config,
    motion_config,
    axis_count,
):
    fields = startup_summary_fields(
        server_config,
        ethercat_config,
        motion_config,
        axis_count,
    )
    details = " ".join(f"{name}={value}" for name, value in fields)
    return f"Motion Server initialized. {details}"
