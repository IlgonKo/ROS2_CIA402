from dataclasses import dataclass
import os

from configuration import split_indexed_config_list
from device.pdo_metadata import (
    ObjectDictionaryEntry,
    PdoPadding,
    padding,
    padding_object,
)


DEFAULT_PDO_CONFIGURATION = "motion_server_default"


@dataclass(frozen=True)
class PdoOdRole:
    role: str
    index: int
    subindex: int
    name: str
    data_type: str
    default: int | float = 0

    def object_entry(self):
        return ObjectDictionaryEntry(
            self.index,
            self.subindex,
            self.name,
            self.data_type,
            self.role,
            self.default,
        )

    def mapping_entry(self):
        return self.object_entry().mapping_entry()


@dataclass(frozen=True)
class CMMTPdoConfiguration:
    name: str
    rxpdo_items: tuple
    txpdo_items: tuple

    def rxpdo_mapping_entries(self):
        return pdo_mapping_entries(self.rxpdo_items)

    def txpdo_mapping_entries(self):
        return pdo_mapping_entries(self.txpdo_items)

    def rxpdo_objects(self):
        return pdo_objects(self.rxpdo_items)

    def txpdo_objects(self):
        return pdo_objects(self.txpdo_items)

    def od_roles(self):
        return [
            item
            for item in (*self.rxpdo_items, *self.txpdo_items)
            if isinstance(item, PdoOdRole)
        ]


def rx(role, index, subindex, name, data_type, default=0):
    return PdoOdRole(role, index, subindex, name, data_type, default)


def tx(role, index, subindex, name, data_type, default=0):
    return PdoOdRole(role, index, subindex, name, data_type, default)


CMMT_PDO_CONFIGURATIONS = {
    "motion_server_default": CMMTPdoConfiguration(
        name="motion_server_default",
        rxpdo_items=(
            rx("controlword", 0x6040, 0x00, "Controlword", "uint16"),
            rx("mode_of_operation", 0x6060, 0x00, "Modes of operation", "int8", 8),
            rx("target_position", 0x607A, 0x00, "Target position", "int32"),
            rx("profile_velocity", 0x6081, 0x00, "Profile velocity", "uint32"),
            rx("target_velocity", 0x60FF, 0x00, "Target velocity", "int32"),
            rx("target_torque", 0x6071, 0x00, "Target torque", "int16"),
            rx("velocity_offset", 0x60B1, 0x00, "Velocity offset", "int32"),
            rx("torque_offset", 0x60B2, 0x00, "Torque offset", "int16"),
            padding(8),
        ),
        txpdo_items=(
            tx("statusword", 0x6041, 0x00, "Statusword", "uint16", 0x0040),
            tx("mode_of_operation_display", 0x6061, 0x00, "Modes of operation display", "int8", 8),
            tx("actual_position", 0x6064, 0x00, "Position actual value", "int32"),
            tx("actual_velocity", 0x606C, 0x00, "Velocity actual value", "int32"),
            tx("actual_torque", 0x6077, 0x00, "Torque actual value", "int16"),
            padding(8),
        ),
    ),
    "profile_position_basic": CMMTPdoConfiguration(
        name="profile_position_basic",
        rxpdo_items=(
            rx("controlword", 0x6040, 0x00, "Controlword", "uint16"),
            rx("mode_of_operation", 0x6060, 0x00, "Modes of operation", "int8", 8),
            rx("target_position", 0x607A, 0x00, "Target position", "int32"),
            rx("profile_velocity", 0x6081, 0x00, "Profile velocity", "uint32"),
        ),
        txpdo_items=(
            tx("statusword", 0x6041, 0x00, "Statusword", "uint16", 0x0040),
            tx("mode_of_operation_display", 0x6061, 0x00, "Modes of operation display", "int8", 8),
            tx("actual_position", 0x6064, 0x00, "Position actual value", "int32"),
            tx("actual_velocity", 0x606C, 0x00, "Velocity actual value", "int32"),
        ),
    ),
    "csp_basic": CMMTPdoConfiguration(
        name="csp_basic",
        rxpdo_items=(
            rx("controlword", 0x6040, 0x00, "Controlword", "uint16"),
            rx("mode_of_operation", 0x6060, 0x00, "Modes of operation", "int8", 8),
            rx("target_position", 0x607A, 0x00, "Target position", "int32"),
            rx("velocity_offset", 0x60B1, 0x00, "Velocity offset", "int32"),
        ),
        txpdo_items=(
            tx("statusword", 0x6041, 0x00, "Statusword", "uint16", 0x0040),
            tx("mode_of_operation_display", 0x6061, 0x00, "Modes of operation display", "int8", 8),
            tx("actual_position", 0x6064, 0x00, "Position actual value", "int32"),
            tx("actual_velocity", 0x606C, 0x00, "Velocity actual value", "int32"),
        ),
    ),
}


def pdo_mapping_entries(items):
    return [pdo_mapping_entry(item) for item in items]


def pdo_mapping_entry(item):
    if isinstance(item, PdoPadding):
        return int(item.bit_length) & 0xFF
    if isinstance(item, PdoOdRole):
        return item.mapping_entry()
    return int(item)


def pdo_objects(items):
    result = []
    for item in items:
        if isinstance(item, PdoPadding):
            result.append(padding_object(item.bit_length))
        elif isinstance(item, PdoOdRole):
            result.append(item.object_entry())
        else:
            raise TypeError(f"Unsupported CMMT PDO item: {item!r}")
    return result


def pdo_configuration_names():
    return sorted(CMMT_PDO_CONFIGURATIONS)


def pdo_od_role(role, configuration_name=None):
    configuration = get_pdo_configuration(configuration_name)
    matches = [
        item
        for item in configuration.od_roles()
        if item.role == role
    ]
    if not matches:
        raise KeyError(
            f"PDO configuration {configuration.name!r} does not define "
            f"role {role!r}."
        )
    if len(matches) > 1:
        locations = ", ".join(
            f"0x{item.index:04X}:{item.subindex:02X}"
            for item in matches
        )
        raise KeyError(
            f"PDO configuration {configuration.name!r} defines "
            f"role {role!r} more than once: {locations}"
        )
    return matches[0]


def get_pdo_configuration(name=None, *, context="CMMT PDO configuration"):
    requested_name = normalize_pdo_configuration_name(
        name or DEFAULT_PDO_CONFIGURATION
    )
    try:
        return CMMT_PDO_CONFIGURATIONS[requested_name]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported {context}: {name!r}. "
            f"Supported: {', '.join(pdo_configuration_names())}"
        ) from exc


def pdo_configuration_from_env(axis_index=None, slave_index=None):
    raw_value, source = pdo_configuration_env_value(axis_index, slave_index)
    configuration = get_pdo_configuration(
        raw_value,
        context=source or "CMMT PDO configuration",
    )
    return configuration, source


def pdo_configuration_env_value(axis_index=None, slave_index=None):
    candidates = []
    if axis_index is not None:
        candidates.append((
            f"MOTION_SERVER_CMMT_AXIS_{int(axis_index)}_PDO_CONFIGURATION",
            os.environ.get(
                f"MOTION_SERVER_CMMT_AXIS_{int(axis_index)}_PDO_CONFIGURATION"
            ),
        ))
        list_value = axis_pdo_configuration_from_list(axis_index)
        if list_value is not None:
            candidates.append((
                f"MOTION_SERVER_CMMT_AXIS_PDO_CONFIGURATIONS[{int(axis_index)}]",
                list_value,
            ))
    if slave_index is not None:
        candidates.append((
            f"MOTION_SERVER_CMMT_SLAVE_{int(slave_index)}_PDO_CONFIGURATION",
            os.environ.get(
                f"MOTION_SERVER_CMMT_SLAVE_{int(slave_index)}_PDO_CONFIGURATION"
            ),
        ))
    candidates.append((
        "MOTION_SERVER_CMMT_PDO_CONFIGURATION",
        os.environ.get("MOTION_SERVER_CMMT_PDO_CONFIGURATION"),
    ))

    for key, value in candidates:
        if value is not None and str(value).strip():
            return value, key
    return DEFAULT_PDO_CONFIGURATION, "default"


def axis_pdo_configuration_from_list(axis_index):
    raw_value = os.environ.get("MOTION_SERVER_CMMT_AXIS_PDO_CONFIGURATIONS")
    if raw_value is None:
        return None
    axis_index = int(axis_index)
    for current_axis, configuration_name in split_indexed_config_list(
        raw_value,
        default_start=0,
    ):
        if int(current_axis) == axis_index:
            return configuration_name.strip()
    return None


def normalize_pdo_configuration_name(value):
    return str(value or "").strip().lower().replace("-", "_")
