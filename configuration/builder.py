from dataclasses import dataclass

from configuration.file_parser import split_config_list, split_indexed_config_list
from configuration.loader import ConfigurationModel
from configuration.bus import parse_bus_config
from configuration.models import (
    BackendType,
    BootstrapServerConfig,
    BusDeviceConfig,
    CmmtDeviceConfig,
    CommandLogConfig,
    CpxApIEcDeviceConfig,
    CspCommandStepLogConfig,
    CspInterpolationMode,
    CspProfile,
    CycleConfig,
    CycleStatsLogConfig,
    DistributedClockConfig,
    EtherCATConfig,
    IoLinkPortConfig,
    IoModuleConfig,
    LoggingConfig,
    MotionConfig,
    MotionServerConfig,
    PositionFeedbackLagLogConfig,
    PreLoggingConfig,
    ServerConfig,
    ServerMode,
    StatusLogConfig,
    TrajectoryLogConfig,
    VelocityAnomalyLogConfig,
)
from device.cmmt.pdo_configuration import get_pdo_configuration
from device.cmmt.non_pdo_configuration import get_non_pdo_configuration


@dataclass(frozen=True)
class CliOverrides:
    port: int | None = None
    backend: BackendType | None = None
    interface: str | None = None
    bus: str | None = None
    server_mode: ServerMode | None = None
    cycle_time: float | None = None
    spin_wait_time: float | None = None
    sync_mode: int | None = None
    dc_enabled: bool | None = None
    dc_sync0_shift_time_ns: int | None = None
    dc_phase_lock: bool | None = None
    dc_absolute_shift: bool | None = None
    dc_phase_offset_ns: int | None = None
    dc_phase_kp: float | None = None
    dc_phase_ki: float | None = None
    dc_phase_max_correction: float | None = None
    csp_jerk: float | None = None
    motion_mode: str | None = None
    csp_profile: CspProfile | None = None
    csp_interpolation_mode: CspInterpolationMode | None = None
    csp_velocity_offset: bool | None = None
    csp_command_step_threshold: float | None = None
    csp_command_step_error_threshold: float | None = None

def build_bootstrap_server_config(source, cli=None):
    values = source.values
    cli = cli or CliOverrides()
    config = BootstrapServerConfig(
        port=(
            cli.port
            if cli.port is not None
            else integer(values, "MOTION_SERVER_PORT", 15000)
        ),
    )
    if not 1 <= config.port <= 65535:
        raise ValueError("Motion Server port must be in range 1..65535")
    return config


def build_motion_server_config(
    source: ConfigurationModel,
    cli: CliOverrides | None = None,
    bootstrap: BootstrapServerConfig | None = None,
):
    values = source.values
    cli = cli or CliOverrides()
    bootstrap = bootstrap or build_bootstrap_server_config(source, cli)
    server = ServerConfig(
        port=bootstrap.port,
        mode=cli.server_mode or enum_value(ServerMode, value(values, "MOTION_SERVER_MODE", "basic")),
        feedback_period=number(values, "MOTION_SERVER_FEEDBACK_PERIOD", 0.05),
        axis_restart_disable_settle_time=number(
            values,
            "MOTION_SERVER_AXIS_RESTART_DISABLE_SETTLE_TIME",
            1.0,
        ),
        bus_reconnect_timeout=number(
            values,
            "MOTION_SERVER_BUS_RECONNECT_TIMEOUT",
            10.0,
        ),
        axis_restart_timeout=number(
            values,
            "MOTION_SERVER_AXIS_RESTART_TIMEOUT",
            30.0,
        ),
        simulation_api_enabled=boolean(
            values,
            "MOTION_SERVER_SIMULATION_API_ENABLED",
            False,
        ),
        expert_mode=boolean(
            values,
            "MOTION_SERVER_EXPERT_MODE",
            False,
        ),
    )
    cycle = CycleConfig(
        period=choose(cli.cycle_time, number(values, "PYSOEM_CYCLE_TIME", 0.01)),
        spin_wait_time=choose(cli.spin_wait_time, number(values, "PYSOEM_SPIN_WAIT_TIME", 0.00015)),
    )
    dc = DistributedClockConfig(
        enabled=choose(cli.dc_enabled, boolean(values, "PYSOEM_DC_ENABLED", False)),
        sync0_shift_time_ns=choose(cli.dc_sync0_shift_time_ns, integer(values, "PYSOEM_DC_SYNC0_SHIFT_TIME_NS", 0)),
        phase_lock=choose(cli.dc_phase_lock, boolean(values, "PYSOEM_DC_PHASE_LOCK", False)),
        absolute_shift=choose(cli.dc_absolute_shift, boolean(values, "PYSOEM_DC_ABSOLUTE_SHIFT", False)),
        phase_offset_ns=choose(cli.dc_phase_offset_ns, integer(values, "PYSOEM_DC_PHASE_OFFSET_NS", 800000)),
        phase_kp=choose(cli.dc_phase_kp, number(values, "PYSOEM_DC_PHASE_KP", 0.05)),
        phase_ki=choose(cli.dc_phase_ki, number(values, "PYSOEM_DC_PHASE_KI", 0.0005)),
        phase_max_correction=choose(cli.dc_phase_max_correction, number(
            values,
            "PYSOEM_DC_PHASE_MAX_CORRECTION",
            0.001,
        )),
    )
    backend = cli.backend or enum_value(
        BackendType,
        value(values, "MOTION_SERVER_BACKEND", "pysoem"),
    )
    ethercat = EtherCATConfig(
        backend=backend,
        interface=cli.interface if cli.interface is not None else value(values, "PYSOEM_INTERFACE", ""),
        sync_mode=choose(cli.sync_mode, optional_integer(values, "PYSOEM_SYNC_MODE")),
        cycle=cycle,
        dc=dc,
    )
    motion = MotionConfig(
        initial_motion_mode=choose(cli.motion_mode, value(values, "MOTION_SERVER_MOTION_MODE", "pp")).lower(),
        csp_profile=cli.csp_profile or enum_value(
            CspProfile,
            value(values, "MOTION_SERVER_CSP_PROFILE", "quintic"),
        ),
        csp_jerk=choose(cli.csp_jerk, number(values, "MOTION_SERVER_CSP_JERK", 100000.0)),
        csp_interpolation_mode=cli.csp_interpolation_mode or enum_value(
            CspInterpolationMode,
            integer(values, "MOTION_SERVER_CSP_INTERPOLATION_MODE", 1),
        ),
        csp_velocity_offset=choose(cli.csp_velocity_offset, boolean(
            values,
            "MOTION_SERVER_CSP_VELOCITY_OFFSET",
            False,
        )),
    )
    logging = build_logging_config(values, cli)
    bus = source.bus if cli.bus is None else parse_bus_config(cli.bus)
    devices = build_device_configs(source, bus=bus, cli=cli)
    config = MotionServerConfig(
        project_root=source.project_root,
        server=server,
        ethercat=ethercat,
        motion=motion,
        logging=logging,
        devices=devices,
    )
    validate_motion_server_config(config)
    return config


def build_logging_config(values, cli=None):
    cli = cli or CliOverrides()
    return LoggingConfig(
        command=CommandLogConfig(boolean(values, "MOTION_SERVER_COMMAND_LOGS", False)),
        status=StatusLogConfig(
            boolean(values, "MOTION_SERVER_STATUS_LOGS", False),
            number(values, "MOTION_SERVER_STATUS_LOG_PERIOD", 1.0),
        ),
        cycle_stats=CycleStatsLogConfig(
            boolean(values, "MOTION_SERVER_CYCLE_STATS_LOGS", True),
            number(values, "MOTION_SERVER_CYCLE_STATS_PERIOD", 1.0),
        ),
        trajectory=TrajectoryLogConfig(
            boolean(values, "MOTION_SERVER_TRAJECTORY_DEBUG_LOGS", False),
            boolean(values, "MOTION_SERVER_TRAJECTORY_SNAPSHOT_LOGS", False),
        ),
        velocity_anomaly=VelocityAnomalyLogConfig(
            boolean(values, "MOTION_SERVER_VELOCITY_ANOMALY_LOGS", False),
            number(values, "MOTION_SERVER_VELOCITY_ANOMALY_THRESHOLD", 15.0),
            number(values, "MOTION_SERVER_VELOCITY_JUMP_THRESHOLD", 15.0),
            number(values, "MOTION_SERVER_VELOCITY_ANOMALY_LOG_PERIOD", 0.05),
        ),
        position_feedback_lag=PositionFeedbackLagLogConfig(
            boolean(values, "MOTION_SERVER_POSITION_FEEDBACK_LAG_LOGS", False),
            number(values, "MOTION_SERVER_POSITION_FEEDBACK_LAG_LOG_PERIOD", 0.2),
        ),
        csp_command_step=CspCommandStepLogConfig(
            boolean(values, "MOTION_SERVER_CSP_COMMAND_STEP_LOGS", False),
            choose(cli.csp_command_step_threshold, number(values, "MOTION_SERVER_CSP_COMMAND_STEP_THRESHOLD", 250.0)),
            choose(cli.csp_command_step_error_threshold, number(values, "MOTION_SERVER_CSP_COMMAND_STEP_ERROR_THRESHOLD", 75.0)),
        ),
        pre_logging=PreLoggingConfig(
            boolean(values, "MOTION_SERVER_PRE_LOGGING_ENABLED", False),
            integer(values, "MOTION_SERVER_PRE_LOGGING_LENGTH", 16),
        ),
    )


def build_device_configs(source, bus=None, cli=None):
    values = source.values
    bus = bus or source.bus
    cli = cli or CliOverrides()
    slave_non_pdo_selections = parse_unique_indexed_values(
        value(values, "MOTION_SERVER_CMMT_SLAVE_NON_PDO_CONFIGURATIONS", ""),
        "MOTION_SERVER_CMMT_SLAVE_NON_PDO_CONFIGURATIONS",
    )
    devices = []
    axis_index = 0
    for bus_device in bus.devices:
        if bus_device.profile in {"cmmt_as", "cmmt_st"}:
            device_config = build_cmmt_config(
                values,
                bus_device,
                axis_index,
                cli,
                slave_non_pdo_selections,
            )
            axis_index += 1
        elif bus_device.profile == "cpx_ap_i_ec":
            device_config = build_cpx_config(values, bus_device)
        else:
            raise ValueError(f"No typed device config for {bus_device.profile!r}")
        devices.append(
            BusDeviceConfig(
                slave_index=bus_device.slave_index,
                role=bus_device.role,
                profile_name=bus_device.profile,
                logical_id=bus_device.logical_id,
                device=device_config,
            )
        )
    return tuple(devices)


def build_cmmt_config(
    values,
    bus_device,
    axis_index,
    cli=None,
    slave_non_pdo_selections=None,
):
    cli = cli or CliOverrides()
    pdo_name = value(
        values,
        f"MOTION_SERVER_CMMT_AXIS_{axis_index}_PDO_CONFIGURATION",
        "",
    )
    if not pdo_name:
        indexed = dict(split_indexed_config_list(
            value(values, "MOTION_SERVER_CMMT_AXIS_PDO_CONFIGURATIONS", ""),
            default_start=0,
        ))
        pdo_name = indexed.get(axis_index, "")
    if not pdo_name:
        pdo_name = value(
            values,
            f"MOTION_SERVER_CMMT_SLAVE_{bus_device.slave_index}_PDO_CONFIGURATION",
            "",
        )
    if not pdo_name:
        pdo_name = value(
            values,
            "MOTION_SERVER_CMMT_PDO_CONFIGURATION",
            "motion_server_default",
        )
    configuration = get_pdo_configuration(pdo_name)
    slave_non_pdo_selections = slave_non_pdo_selections or {}
    selection_key = (
        f"MOTION_SERVER_CMMT_SLAVE_{bus_device.slave_index}_"
        "NON_PDO_CONFIGURATION"
    )
    selected_name = value(values, selection_key, "").lower()
    if not selected_name:
        selected_name = str(
            slave_non_pdo_selections.get(bus_device.slave_index, "")
        ).strip().lower()
    selected = None
    if selected_name:
        selected = get_non_pdo_configuration(selected_name)

    return CmmtDeviceConfig(
        profile_name=bus_device.profile,
        axis_index=axis_index,
        pdo_configuration=configuration.name,
        non_pdo_configuration=selected,
    )


def parse_unique_indexed_values(raw_value, setting_name):
    result = {}
    for index, item_value in split_indexed_config_list(raw_value, default_start=0):
        if index in result:
            raise ValueError(f"Duplicate slave {index} in {setting_name}")
        result[index] = item_value
    return result


def build_cpx_config(values, bus_device):
    logical_id = bus_device.logical_id
    modules_key = f"MOTION_SERVER_IO_{logical_id}_MODULES"
    raw_modules = value(values, modules_key, "")
    if not raw_modules:
        raise ValueError(f"Missing {modules_key}")
    modules = tuple(
        IoModuleConfig(slot, module_type)
        for slot, module_type in split_indexed_config_list(raw_modules, default_start=1)
    )
    raw_ports = value(values, f"MOTION_SERVER_IO_{logical_id}_IOL_PORTS", "")
    ports = []
    for declaration in split_config_list(raw_ports):
        ports.append(IoLinkPortConfig.from_declaration(declaration))
    return CpxApIEcDeviceConfig(
        profile_name=bus_device.profile,
        logical_id=logical_id,
        modules=modules,
        io_link_ports=tuple(ports),
    )


def validate_motion_server_config(config):
    if config.server.feedback_period <= 0.0:
        raise ValueError("Motion Server feedback period must be > 0")
    if config.server.axis_restart_disable_settle_time < 0.0:
        raise ValueError("Axis restart disable settle time must be >= 0")
    if config.server.bus_reconnect_timeout <= 0.0:
        raise ValueError("Bus reconnect timeout must be > 0")
    if config.server.axis_restart_timeout <= 0.0:
        raise ValueError("Axis restart timeout must be > 0")
    if config.ethercat.cycle.period <= 0.0:
        raise ValueError("EtherCAT cycle period must be > 0")
    if not 0.0 <= config.ethercat.cycle.spin_wait_time < config.ethercat.cycle.period:
        raise ValueError("EtherCAT spin wait time must satisfy 0 <= value < period")
    if config.ethercat.sync_mode not in {None, 0, 1, 2}:
        raise ValueError("EtherCAT sync mode must be 0, 1, 2, or empty")
    if config.ethercat.backend is BackendType.PYSOEM and not config.ethercat.interface:
        raise ValueError("PySOEM backend requires an interface")
    if (
        config.ethercat.dc.enabled
        and config.ethercat.dc.absolute_shift
        and not config.ethercat.dc.phase_lock
    ):
        raise ValueError("DC absolute shift requires DC phase lock")
    if config.motion.initial_motion_mode not in {"pp", "pv", "jog", "csp"}:
        raise ValueError(
            "Initial motion mode must be one of: pp, pv, jog, csp"
        )
    if config.motion.csp_jerk <= 0:
        raise ValueError("CSP jerk must be > 0")
    for log_config in (
        config.logging.status,
        config.logging.cycle_stats,
        config.logging.position_feedback_lag,
    ):
        if log_config.enabled and log_config.period <= 0.0:
            raise ValueError("Enabled periodic log requires period > 0")
    if config.logging.pre_logging.enabled and config.logging.pre_logging.length < 1:
        raise ValueError("Enabled pre-logging requires length >= 1")
    if config.axis_count < 1:
        raise ValueError("Motion Server requires at least one axis")
    if config.ethercat.backend is BackendType.MOCK:
        missing = [
            device.slave_index
            for device in config.devices
            if isinstance(device.device, CmmtDeviceConfig)
            and device.device.non_pdo_configuration is None
        ]
        if missing:
            raise ValueError(
                "Mock CMMT slaves require a Non-PDO configuration: "
                + ", ".join(str(index) for index in missing)
            )


def value(values, name, default=""):
    return str(values.get(name, default)).strip()


def boolean(values, name, default=False):
    raw = value(values, name, "1" if default else "0").lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def integer(values, name, default):
    return int(value(values, name, default), 0)


def optional_integer(values, name):
    raw = value(values, name, "")
    return None if raw == "" else int(raw, 0)


def number(values, name, default):
    return float(value(values, name, default))


def enum_value(enum_type, raw):
    try:
        return enum_type(raw)
    except ValueError as exc:
        supported = ", ".join(str(item.value) for item in enum_type)
        raise ValueError(
            f"Unsupported {enum_type.__name__} {raw!r}; supported: {supported}"
        ) from exc


def choose(override, default):
    return default if override is None else override
