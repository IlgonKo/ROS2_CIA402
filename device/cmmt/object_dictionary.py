from dataclasses import dataclass
import struct


DATA_TYPE_FORMATS = {
    "uint8": "<B",
    "int8": "<b",
    "uint16": "<H",
    "int16": "<h",
    "uint32": "<I",
    "int32": "<i",
    "uint64": "<Q",
    "int64": "<q",
    "float32": "<f",
}

DATA_TYPE_BITS = {
    data_type: struct.calcsize(fmt) * 8
    for data_type, fmt in DATA_TYPE_FORMATS.items()
}


@dataclass(frozen=True)
class CiA402Object:
    index: int
    subindex: int
    name: str
    data_type: str
    field: str | None = None
    default: int | float = 0

    @property
    def bit_length(self):
        if self.data_type.startswith("padding"):
            return int(self.data_type.removeprefix("padding"))
        return DATA_TYPE_BITS[self.data_type]

    @property
    def byte_length(self):
        return self.bit_length // 8

    def mapping_entry(self):
        return (self.index << 16) | (self.subindex << 8) | self.bit_length


def od_key(index, subindex=0):
    return int(index), int(subindex)


CMMT_OBJECTS = {
    od_key(0x1C32, 0x01): CiA402Object(
        0x1C32,
        0x01,
        "Synchronisation mode",
        "uint16",
        default=1,
    ),
    od_key(0x1C32, 0x02): CiA402Object(
        0x1C32,
        0x02,
        "Cycle time",
        "uint32",
        default=8000000,
    ),
    od_key(0x2145, 0x0C): CiA402Object(
        0x2145,
        0x0C,
        "CMMT most serious error",
        "uint32",
    ),
    od_key(0x6040): CiA402Object(
        0x6040,
        0,
        "Controlword",
        "uint16",
        "controlword",
    ),
    od_key(0x6041): CiA402Object(
        0x6041,
        0,
        "Statusword",
        "uint16",
        "statusword",
        0x0040,
    ),
    od_key(0x6060): CiA402Object(
        0x6060,
        0,
        "Mode of operation",
        "int8",
        "mode_of_operation",
        8,
    ),
    od_key(0x6061): CiA402Object(
        0x6061,
        0,
        "Mode of operation display",
        "int8",
        "mode_of_operation_display",
        8,
    ),
    od_key(0x6062): CiA402Object(
        0x6062,
        0,
        "Position demand value / set-point position",
        "int32",
        "setpoint_position",
    ),
    od_key(0x6064): CiA402Object(
        0x6064,
        0,
        "Position actual value",
        "int32",
        "actual_position",
    ),
    od_key(0x6067): CiA402Object(
        0x6067,
        0,
        "Position window",
        "uint32",
        default=20,
    ),
    od_key(0x6068): CiA402Object(
        0x6068,
        0,
        "Position window time",
        "uint16",
        default=20,
    ),
    od_key(0x606B): CiA402Object(
        0x606B,
        0,
        "Velocity demand value / setpoint velocity",
        "int32",
        "setpoint_velocity",
    ),
    od_key(0x606C): CiA402Object(
        0x606C,
        0,
        "Velocity actual value",
        "int32",
        "actual_velocity",
    ),
    od_key(0x6071): CiA402Object(
        0x6071,
        0,
        "Target torque",
        "int16",
        "target_torque",
    ),
    od_key(0x6077): CiA402Object(
        0x6077,
        0,
        "Torque actual value",
        "int16",
        "actual_torque",
    ),
    od_key(0x607D, 0x01): CiA402Object(
        0x607D,
        0x01,
        "Negative software position limit",
        "int32",
        default=-1000000,
    ),
    od_key(0x607D, 0x02): CiA402Object(
        0x607D,
        0x02,
        "Positive software position limit",
        "int32",
        default=1000000,
    ),
    od_key(0x607F): CiA402Object(
        0x607F,
        0,
        "Limit value velocity limit positive direction of movement",
        "uint32",
        default=100,
    ),
    od_key(0x2183, 0x0C): CiA402Object(
        0x2183,
        0x0C,
        "Limit value velocity limit negative direction of movement",
        "float32",
        default=-0.1,
    ),
    od_key(0x607A): CiA402Object(
        0x607A,
        0,
        "Target position",
        "int32",
        "target_position",
    ),
    od_key(0x6081): CiA402Object(
        0x6081,
        0,
        "Profile velocity",
        "uint32",
        "profile_velocity",
        100,
    ),
    od_key(0x6083): CiA402Object(
        0x6083,
        0,
        "Profile acceleration",
        "uint32",
        default=50,
    ),
    od_key(0x6084): CiA402Object(
        0x6084,
        0,
        "Profile deceleration",
        "uint32",
        default=50,
    ),
    od_key(0x60C5): CiA402Object(
        0x60C5,
        0,
        "Max acceleration",
        "uint32",
        default=50,
    ),
    od_key(0x60C6): CiA402Object(
        0x60C6,
        0,
        "Max deceleration",
        "uint32",
        default=50,
    ),
    od_key(0x6098): CiA402Object(
        0x6098,
        0,
        "Homing method",
        "int8",
        default=35,
    ),
    od_key(0x6099, 0x01): CiA402Object(
        0x6099,
        0x01,
        "Homing speed during search for switch",
        "uint32",
        default=100,
    ),
    od_key(0x6099, 0x02): CiA402Object(
        0x6099,
        0x02,
        "Homing speed during search for zero",
        "uint32",
        default=50,
    ),
    od_key(0x609A): CiA402Object(
        0x609A,
        0,
        "Homing acceleration",
        "uint32",
        default=100,
    ),
    od_key(0x216E, 0x01): CiA402Object(
        0x216E,
        0x01,
        "User unit position",
        "uint16",
        default=0x4100,
    ),
    od_key(0x2194, 0x01): CiA402Object(
        0x2194,
        0x01,
        "Resolution position",
        "int8",
        default=6,
    ),
    od_key(0x2194, 0x02): CiA402Object(
        0x2194,
        0x02,
        "Resolution velocity",
        "int8",
        default=3,
    ),
    od_key(0x2194, 0x03): CiA402Object(
        0x2194,
        0x03,
        "Resolution acceleration",
        "int8",
        default=3,
    ),
    od_key(0x2194, 0x04): CiA402Object(
        0x2194,
        0x04,
        "Resolution jerk",
        "int8",
        default=3,
    ),
    od_key(0x60A4, 0x01): CiA402Object(
        0x60A4,
        0x01,
        "Profile jerk",
        "uint32",
        default=100000,
    ),
    od_key(0x60B1): CiA402Object(
        0x60B1,
        0,
        "Velocity offset",
        "int32",
        "velocity_offset",
    ),
    od_key(0x60B2): CiA402Object(
        0x60B2,
        0,
        "Torque offset",
        "int16",
        "torque_offset",
    ),
    od_key(0x60FF): CiA402Object(
        0x60FF,
        0,
        "Target velocity",
        "int32",
        "target_velocity",
    ),
    od_key(0x217A, 0x01): CiA402Object(
        0x217A,
        0x01,
        "Fine interpolator output position",
        "int64",
        "setpoint_position",
    ),
}


def padding_object(bit_length):
    return CiA402Object(
        0x0000,
        0x00,
        f"Padding {bit_length}",
        f"padding{bit_length}",
    )


def pdo_object(index, subindex=0):
    return CMMT_OBJECTS[od_key(index, subindex)]
