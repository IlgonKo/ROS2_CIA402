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
)


@dataclass(frozen=True)
class ConfigurationModel:
    project_root: Path
    values: MappingProxyType
    bus: BusConfig

    def value(self, name, default=""):
        return self.values.get(name, default)


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


def _environment_values(raw_environment, canonical_keys):
    """Return relevant environment values using config-file key casing.

    Windows environment-variable names are case-insensitive.  Canonicalizing
    known names here prevents a process variable such as ``..._IO0_...`` from
    coexisting with the configured ``..._io0_...`` spelling in the model.
    """
    canonical_by_casefold = {key.casefold(): key for key in canonical_keys}
    selected = {}
    for key, value in raw_environment.items():
        canonical_key = canonical_by_casefold.get(key.casefold())
        if canonical_key is not None:
            selected[canonical_key] = str(value)
        elif key.startswith(CONFIG_ENV_PREFIXES):
            selected[key] = str(value)
    return selected


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
    bootstrap_environment = _environment_values(raw_environment, project_values)
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

    known_keys = set(project_values) | set(device_defaults)
    process_values = _environment_values(raw_environment, known_keys)
    values = device_defaults
    values.update(project_values)
    values.update(process_values)
    return ConfigurationModel(project_root, MappingProxyType(values), bus)
