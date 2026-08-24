from dataclasses import dataclass
import os
from pathlib import Path
from types import MappingProxyType

from configuration.bus import BusConfig, parse_bus_config
from configuration.file_parser import read_key_value_config


DEFAULT_BUS = "cmmt_as"
CONFIG_ENV_PREFIXES = (
    "AXIS_",
    "COMPOSE_",
    "IO_",
    "MOCK_",
    "MOTION_SERVER_",
    "PYSOEM_",
    "ROS_",
    "ROS2_",
    "VIRTUAL_",
)
_active_configuration = None


@dataclass(frozen=True)
class ConfigurationModel:
    values: MappingProxyType
    bus: BusConfig

    def value(self, name, default=""):
        return self.values.get(name, default)


def active_configuration():
    return _active_configuration


def set_active_configuration(model):
    global _active_configuration
    _active_configuration = model


def device_config_profile_name(profile_name):
    normalized = str(profile_name or "").strip().lower().replace("-", "_")
    if normalized in {"cmmt_as", "cmmt_st"}:
        return "cmmt"
    return normalized


def resolve_path(root, raw_path, default_path):
    path = Path(raw_path or default_path)
    if not path.is_absolute():
        path = Path(root) / path
    return path


def load_configuration(
    project_root,
    *,
    project_filename=".env",
    device_filename=".env",
    environ=None,
    available_profiles=None,
):
    project_root = Path(project_root).resolve()
    raw_environment = os.environ if environ is None else environ
    project_values = read_key_value_config(project_root / project_filename)
    bootstrap_environment = {
        key: str(value)
        for key, value in raw_environment.items()
        if key in project_values or key.startswith(CONFIG_ENV_PREFIXES)
    }
    effective_common = dict(project_values)
    effective_common.update(bootstrap_environment)

    raw_bus = effective_common.get("MOTION_SERVER_BUS", DEFAULT_BUS)
    bus = parse_bus_config(raw_bus, available_profiles=available_profiles)
    config_root = resolve_path(
        project_root,
        effective_common.get("MOTION_SERVER_DEVICE_CONFIG_ROOT", "device"),
        "device",
    )

    device_defaults = {}
    for profile_name in bus.profile_names:
        config_profile = device_config_profile_name(profile_name)
        device_path = config_root / config_profile / device_filename
        for key, value in read_key_value_config(device_path).items():
            device_defaults.setdefault(key, value)

    if effective_common.get("MOTION_SERVER_BACKEND", "pysoem").strip().lower() == "mock":
        virtual_path = resolve_path(
            project_root,
            effective_common.get(
                "VIRTUAL_SERVO_DRIVE_ENV_FILE",
                f"device/virtual_servo_drive/{device_filename}",
            ),
            f"device/virtual_servo_drive/{device_filename}",
        )
        for key, value in read_key_value_config(virtual_path).items():
            device_defaults.setdefault(key, value)

    known_keys = set(project_values) | set(device_defaults)
    process_values = {
        key: str(value)
        for key, value in raw_environment.items()
        if key in known_keys or key.startswith(CONFIG_ENV_PREFIXES)
    }
    values = device_defaults
    values.update(project_values)
    values.update(process_values)
    return ConfigurationModel(MappingProxyType(values), bus)
