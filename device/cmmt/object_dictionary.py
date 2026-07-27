from device.cia402 import CIA402_OBJECTS
from device.common_object_dictionary import (
    ETHERCAT_OBJECTS,
    ObjectDictionaryEntry,
    od_key,
    padding,
    pdo_mapping_entries as common_pdo_mapping_entries,
    pdo_mapping_entry as common_pdo_mapping_entry,
    pdo_object_by_field as common_pdo_object_by_field,
    pdo_object_from_dictionary,
    pdo_objects_from_mapping_entries as common_pdo_objects_from_mapping_entries,
)


CMMT_VENDOR_OBJECTS = {
    od_key(0x2000, 0x01): ObjectDictionaryEntry(
        0x2000,
        0x01,
        "Reset device control",
        "uint8",
    ),
    od_key(0x2005, 0x01): ObjectDictionaryEntry(
        0x2005,
        0x01,
        "Save parameter set control",
        "uint8",
    ),
    od_key(0x2005, 0x02): ObjectDictionaryEntry(
        0x2005,
        0x02,
        "Save parameter set status",
        "uint8",
    ),
    od_key(0x2005, 0x03): ObjectDictionaryEntry(
        0x2005,
        0x03,
        "Save parameter set selection",
        "uint16",
    ),
    od_key(0x2005, 0x04): ObjectDictionaryEntry(
        0x2005,
        0x04,
        "Save parameter set return code",
        "uint16",
    ),
    od_key(0x2005, 0x05): ObjectDictionaryEntry(
        0x2005,
        0x05,
        "Save parameter set return value",
        "uint16",
    ),
    od_key(0x1C32, 0x01): ObjectDictionaryEntry(
        0x1C32,
        0x01,
        "Synchronisation mode",
        "uint16",
        default=1,
    ),
    od_key(0x1C32, 0x02): ObjectDictionaryEntry(
        0x1C32,
        0x02,
        "Cycle time",
        "uint32",
        default=8000000,
    ),
    od_key(0x2145, 0x0C): ObjectDictionaryEntry(
        0x2145,
        0x0C,
        "CMMT most serious error",
        "uint32",
    ),
    od_key(0x216E, 0x01): ObjectDictionaryEntry(
        0x216E,
        0x01,
        "User unit position",
        "uint16",
        default=0x4100,
    ),
    od_key(0x217A, 0x01): ObjectDictionaryEntry(
        0x217A,
        0x01,
        "Fine interpolator output position",
        "int64",
        "setpoint_position",
    ),
    od_key(0x2183, 0x0C): ObjectDictionaryEntry(
        0x2183,
        0x0C,
        "Limit value velocity limit negative direction of movement",
        "float32",
        default=-0.1,
    ),
    od_key(0x2194, 0x01): ObjectDictionaryEntry(
        0x2194,
        0x01,
        "Resolution position",
        "int8",
        default=6,
    ),
    od_key(0x2194, 0x02): ObjectDictionaryEntry(
        0x2194,
        0x02,
        "Resolution velocity",
        "int8",
        default=3,
    ),
    od_key(0x2194, 0x03): ObjectDictionaryEntry(
        0x2194,
        0x03,
        "Resolution acceleration",
        "int8",
        default=3,
    ),
    od_key(0x2194, 0x04): ObjectDictionaryEntry(
        0x2194,
        0x04,
        "Resolution jerk",
        "int8",
        default=3,
    ),
}

CMMT_OBJECTS = {
    **ETHERCAT_OBJECTS,
    **CIA402_OBJECTS,
    **CMMT_VENDOR_OBJECTS,
}


def pdo_object(index, subindex=0):
    return pdo_object_from_dictionary(CMMT_OBJECTS, index, subindex)


def pdo_object_by_field(field):
    return common_pdo_object_by_field(CMMT_OBJECTS, field)


def pdo_mapping_entry(item):
    return common_pdo_mapping_entry(CMMT_OBJECTS, item)


def pdo_mapping_entries(items):
    return common_pdo_mapping_entries(CMMT_OBJECTS, items)


def pdo_objects_from_mapping_entries(mapping_entries):
    return common_pdo_objects_from_mapping_entries(
        CMMT_OBJECTS,
        mapping_entries,
    )
