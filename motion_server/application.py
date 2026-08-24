from configuration import (
    BackendType,
    CliOverrides,
    ConfigurationSource,
    build_motion_server_config,
    load_configuration,
    set_active_configuration,
)
from device import available_device_names
from motion_server.diagnostic import DiagnosticManager
from types import SimpleNamespace


class MotionServerApplication:
    """Composition root for one immutable Motion Server configuration."""

    def __init__(self, config, legacy_args):
        self._config = config
        self._legacy_args = legacy_args

    @property
    def config(self):
        return self._config

    @classmethod
    def from_source(cls, source, argv=None, environ=None):
        if not isinstance(source, ConfigurationSource):
            raise TypeError("source must be a ConfigurationSource")
        raw_config = load_configuration(
            source.project_root,
            project_filename=source.project_filename,
            device_filename=source.device_filename,
            environ=environ,
            available_profiles=available_device_names(),
        )

        argv = list(argv or ())
        if argv:
            # Transitional CLI adapter through S03. The raw model is registered
            # before importing the legacy parser so files are not read twice.
            set_active_configuration(raw_config)
            from motion_server.config import parse_args

            legacy_args = parse_args(argv)
            typed_config = build_motion_server_config(
                raw_config,
                CliOverrides(
                    host=legacy_args.host,
                    port=legacy_args.port,
                    backend=BackendType(legacy_args.backend),
                    interface=legacy_args.interface,
                ),
            )
        else:
            typed_config = build_motion_server_config(raw_config)
            legacy_args = legacy_args_from_config(typed_config, raw_config)
        return cls(typed_config, legacy_args)

    def run(self, runner=None):
        if runner is not None:
            return runner(
                args=self._legacy_args,
                diagnostic_manager=DiagnosticManager(),
            )

        # S03 replaces the Namespace adapter with typed projections. Runtime
        # reset/reconnect lifecycle already belongs to this composition root.
        from motion_server.server import (
            ServerResetRequested,
            ServerRestartRequested,
            restart_current_process,
            run_main_once,
        )

        diagnostic_manager = DiagnosticManager()
        while True:
            try:
                run_main_once(diagnostic_manager, args=self._legacy_args)
                return
            except ServerResetRequested:
                print(
                    "Motion Server runtime reinitialization requested; "
                    "reinitializing runtime and bus.",
                    flush=True,
                )
                continue
            except ServerRestartRequested:
                print(
                    "Motion Server restart requested; restarting process.",
                    flush=True,
                )
                restart_current_process()


def legacy_args_from_config(config, raw_config):
    values = raw_config.values
    devices = config.devices
    axis_slave_indices = tuple(
        device.slave_index
        for device in devices
        if device.role.value == "axis"
    )
    io_devices = tuple(
        {
            "id": device.logical_id,
            "profile": device.profile_name,
            "slave_index": device.slave_index,
        }
        for device in devices
        if device.role.value == "io"
    )
    cmmt_configs = [
        device.device
        for device in devices
        if device.role.value == "axis"
    ]
    interpolation_mode = (
        int(cmmt_configs[0].csp_interpolation_mode)
        if cmmt_configs
        else 1
    )
    velocity_offset = (
        bool(cmmt_configs[0].csp_velocity_offset)
        if cmmt_configs
        else False
    )
    limits = config.motion.default_limits
    dc = config.ethercat.dc
    logs = config.logging
    return SimpleNamespace(
        acceleration=limits.acceleration,
        axis_count=config.axis_count,
        axis_slave_indices=axis_slave_indices,
        backend=config.ethercat.backend.value,
        bus=str(values.get("MOTION_SERVER_BUS", "cmmt_as")),
        csp_command_step_error_threshold=logs.csp_command_step.error_threshold,
        csp_command_step_threshold=logs.csp_command_step.step_threshold,
        csp_interpolation_mode=interpolation_mode,
        csp_profile=config.motion.csp_profile.value,
        csp_velocity_offset=velocity_offset,
        cycle_time=config.ethercat.cycle.period,
        dc_absolute_shift=dc.absolute_shift,
        dc_enabled=dc.enabled,
        dc_phase_ki=dc.phase_ki,
        dc_phase_kp=dc.phase_kp,
        dc_phase_lock=dc.phase_lock,
        dc_phase_max_correction=dc.phase_max_correction,
        dc_phase_offset=dc.phase_offset_ns,
        dc_sync0_shift_time=dc.sync0_shift_time_ns,
        deceleration=limits.deceleration,
        derived_velocity_alpha=float(
            values.get("MOTION_SERVER_DERIVED_VELOCITY_ALPHA", "0.2")
        ),
        device_profile_names=tuple(device.profile_name for device in devices),
        host=config.server.host,
        interface=config.ethercat.interface,
        io_devices=io_devices,
        jerk=limits.jerk,
        list_adapters=False,
        max_velocity=limits.max_velocity,
        mock_axis_types=str(values.get("MOCK_AXIS_TYPES", "")),
        mock_axis_user_units=str(values.get("MOCK_AXIS_USER_UNITS", "")),
        motion_mode=config.motion.initial_motion_mode,
        port=config.server.port,
        pp_jerk=limits.pp_jerk,
        server_mode=config.server.mode.value,
        spin_wait_time=config.ethercat.cycle.spin_wait_time,
        sync_mode=(
            "" if config.ethercat.sync_mode is None else str(config.ethercat.sync_mode)
        ),
    )
