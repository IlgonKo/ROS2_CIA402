from dataclasses import dataclass


@dataclass(frozen=True)
class RequiredNonPdoOdRole:
    role: str
    index: int
    subindex: int
    name: str
    data_type: str
    access: str = ""
    default: int | float = 0


def od(role, index, subindex, name, data_type, access="", default=0):
    return RequiredNonPdoOdRole(
        role,
        index,
        subindex,
        name,
        data_type,
        access,
        default,
    )


CMMT_REQUIRED_NON_PDO_OD = {
    item.role: item
    for item in (
        od(
            "user_position_unit",
            0x216E,
            0x01,
            "User unit position",
            "uint16",
            "ro",
            0x4100,
        ),
        od(
            "converting_unit_position",
            0x2194,
            0x01,
            "Resolution position",
            "int8",
            "ro",
            6,
        ),
        od(
            "converting_unit_velocity",
            0x2194,
            0x02,
            "Resolution velocity",
            "int8",
            "ro",
            3,
        ),
        od(
            "converting_unit_acceleration",
            0x2194,
            0x03,
            "Resolution acceleration",
            "int8",
            "ro",
            3,
        ),
        od(
            "converting_unit_jerk",
            0x2194,
            0x04,
            "Resolution jerk",
            "int8",
            "ro",
            3,
        ),
        od(
            "software_position_limit_negative",
            0x607D,
            0x01,
            "Minimum position limit",
            "int32",
            "rw",
            -1000000,
        ),
        od(
            "software_position_limit_positive",
            0x607D,
            0x02,
            "Maximum position limit",
            "int32",
            "rw",
            1000000,
        ),
        od(
            "position_window",
            0x6067,
            0x00,
            "Position window",
            "uint32",
            "rw",
            20,
        ),
        od(
            "position_window_time",
            0x6068,
            0x00,
            "Position window time",
            "uint16",
            "rw",
            20,
        ),
        od(
            "max_profile_velocity",
            0x607F,
            0x00,
            "Max profile velocity",
            "uint32",
            "rw",
            200,
        ),
        od(
            "negative_velocity_limit",
            0x2183,
            0x0C,
            "Limit value velocity limit negative direction of movement",
            "float32",
            "rw",
            -0.1,
        ),
        od(
            "profile_velocity",
            0x6081,
            0x00,
            "Profile velocity",
            "uint32",
            "rw",
        ),
        od(
            "profile_acceleration",
            0x6083,
            0x00,
            "Profile acceleration",
            "uint32",
            "rw",
            1000,
        ),
        od(
            "profile_deceleration",
            0x6084,
            0x00,
            "Profile deceleration",
            "uint32",
            "rw",
            1000,
        ),
        od(
            "homing_method",
            0x6098,
            0x00,
            "Homing method",
            "int8",
            "rw",
            35,
        ),
        od(
            "homing_speed_search_switch",
            0x6099,
            0x01,
            "Speed during search for switch",
            "uint32",
            "rw",
            100,
        ),
        od(
            "homing_speed_search_zero",
            0x6099,
            0x02,
            "Speed during search for zero",
            "uint32",
            "rw",
            50,
        ),
        od(
            "homing_acceleration",
            0x609A,
            0x00,
            "Homing acceleration",
            "uint32",
            "rw",
            100,
        ),
        od(
            "max_acceleration",
            0x60C5,
            0x00,
            "Max acceleration",
            "uint32",
            "rw",
            2000,
        ),
        od(
            "max_deceleration",
            0x60C6,
            0x00,
            "Max deceleration",
            "uint32",
            "rw",
            2000,
        ),
        od(
            "pp_jerk",
            0x60A4,
            0x01,
            "Jerk",
            "uint32",
            "rw",
            100000,
        ),
        od(
            "csp_interpolation_mode",
            0x217B,
            0x0D,
            "CSP interpolation mode",
            "uint32",
            "rw",
        ),
        od(
            "sync_mode",
            0x212E,
            0x01,
            "Synchronisation mode",
            "uint16",
            "rw",
        ),
        od(
            "sync_cycle_time",
            0x212E,
            0x02,
            "Cycle time",
            "float32",
            "rw",
        ),
        od(
            "sync_interpolation_time",
            0x212E,
            0x09,
            "Interpolation time",
            "float32",
            "rw",
        ),
        od(
            "output_sync_manager_synchronization_type",
            0x1C32,
            0x01,
            "Output sync manager synchronization type",
            "uint16",
            "rw",
            1,
        ),
        od(
            "output_sync_manager_cycle_time",
            0x1C32,
            0x02,
            "Output sync manager cycle time",
            "uint32",
            "rw",
            8000000,
        ),
        od(
            "device_reset_command",
            0x2000,
            0x01,
            "Reset device control",
            "uint8",
            "rw",
        ),
        od(
            "parameter_save_command",
            0x2005,
            0x01,
            "Save parameter set control",
            "uint8",
            "rw",
        ),
        od(
            "parameter_save_status",
            0x2005,
            0x02,
            "Save parameter set status",
            "uint8",
            "ro",
        ),
        od(
            "parameter_save_selection",
            0x2005,
            0x03,
            "Save parameter set selection",
            "uint16",
            "rw",
        ),
        od(
            "parameter_save_return_code",
            0x2005,
            0x04,
            "Save parameter set return code",
            "uint16",
            "ro",
        ),
        od(
            "parameter_save_return_value",
            0x2005,
            0x05,
            "Save parameter set return value",
            "uint16",
            "ro",
        ),
        od(
            "error_code",
            0x2145,
            0x0C,
            "CMMT most serious error",
            "uint32",
            "ro",
        ),
    )
}


def required_non_pdo_od(role):
    return CMMT_REQUIRED_NON_PDO_OD[role]


def required_non_pdo_od_roles():
    return tuple(CMMT_REQUIRED_NON_PDO_OD.values())
