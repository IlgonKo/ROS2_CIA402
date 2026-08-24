from dataclasses import dataclass
from enum import Enum, IntEnum
from pathlib import Path

from configuration.bus import DeviceRole


class ServerMode(str, Enum):
    BASIC = "basic"
    ADVANCED = "advanced"


class BackendType(str, Enum):
    PYSOEM = "pysoem"
    MOCK = "mock"


class CspProfile(str, Enum):
    TRAPEZOID = "trapezoid"
    QUINTIC = "quintic"


class CspInterpolationMode(IntEnum):
    CSP = 1
    CSP_V = 4
    CSP_T = 5
    CSP_VT = 6


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    mode: ServerMode
    feedback_period: float
    axis_restart_disable_settle_time: float


@dataclass(frozen=True)
class CycleConfig:
    period: float
    spin_wait_time: float


@dataclass(frozen=True)
class DistributedClockConfig:
    enabled: bool
    sync0_shift_time_ns: int
    phase_lock: bool
    absolute_shift: bool
    phase_offset_ns: int
    phase_kp: float
    phase_ki: float
    phase_max_correction: float


@dataclass(frozen=True)
class EtherCATConfig:
    backend: BackendType
    interface: str
    sync_mode: int | None
    cycle: CycleConfig
    dc: DistributedClockConfig


@dataclass(frozen=True)
class MotionLimitConfig:
    max_velocity: float
    acceleration: float
    deceleration: float
    jerk: float
    pp_jerk: int


@dataclass(frozen=True)
class MotionConfig:
    default_limits: MotionLimitConfig
    initial_motion_mode: str
    csp_profile: CspProfile


@dataclass(frozen=True)
class CommandLogConfig:
    enabled: bool


@dataclass(frozen=True)
class StatusLogConfig:
    enabled: bool
    period: float


@dataclass(frozen=True)
class CycleStatsLogConfig:
    enabled: bool
    period: float


@dataclass(frozen=True)
class PositionFeedbackLagLogConfig:
    enabled: bool
    period: float


@dataclass(frozen=True)
class TrajectoryLogConfig:
    debug_enabled: bool
    snapshot_enabled: bool


@dataclass(frozen=True)
class VelocityAnomalyLogConfig:
    enabled: bool
    error_threshold: float
    jump_threshold: float
    period: float


@dataclass(frozen=True)
class CspCommandStepLogConfig:
    enabled: bool
    step_threshold: float
    error_threshold: float


@dataclass(frozen=True)
class PreLoggingConfig:
    enabled: bool
    length: int


@dataclass(frozen=True)
class LoggingConfig:
    command: CommandLogConfig
    status: StatusLogConfig
    cycle_stats: CycleStatsLogConfig
    trajectory: TrajectoryLogConfig
    velocity_anomaly: VelocityAnomalyLogConfig
    position_feedback_lag: PositionFeedbackLagLogConfig
    csp_command_step: CspCommandStepLogConfig
    pre_logging: PreLoggingConfig


@dataclass(frozen=True)
class OdStartupParameter:
    index: int
    subindex: int
    value: int | float | str


@dataclass(frozen=True)
class CmmtDeviceConfig:
    profile_name: str
    axis_index: int
    pdo_configuration: str
    csp_interpolation_mode: CspInterpolationMode
    csp_velocity_offset: bool
    startup_parameters: tuple[OdStartupParameter, ...] = ()


@dataclass(frozen=True)
class IoModuleConfig:
    slot: int
    module_type: str


@dataclass(frozen=True)
class IoLinkPortConfig:
    selector: str
    device_name: str


@dataclass(frozen=True)
class CpxApIEcDeviceConfig:
    profile_name: str
    logical_id: str
    modules: tuple[IoModuleConfig, ...]
    io_link_ports: tuple[IoLinkPortConfig, ...]


DeviceConfig = CmmtDeviceConfig | CpxApIEcDeviceConfig


@dataclass(frozen=True)
class BusDeviceConfig:
    slave_index: int
    role: DeviceRole
    profile_name: str
    logical_id: str | None
    device: DeviceConfig


@dataclass(frozen=True)
class MotionServerConfig:
    project_root: Path
    server: ServerConfig
    ethercat: EtherCATConfig
    motion: MotionConfig
    logging: LoggingConfig
    devices: tuple[BusDeviceConfig, ...]

    @property
    def axis_count(self):
        return sum(device.role is DeviceRole.AXIS for device in self.devices)
