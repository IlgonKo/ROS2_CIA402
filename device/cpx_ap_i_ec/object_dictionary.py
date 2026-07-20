from device.common_object_dictionary import (
    ETHERCAT_OBJECTS,
    ObjectDictionaryEntry,
    od_key,
    pdo_object_from_dictionary,
)


CPX_AP_I_EC_VENDOR_OBJECTS = {
    od_key(0x27F0): ObjectDictionaryEntry(
        0x27F0,
        0,
        "AP parameter access entries",
        "uint8",
        default=7,
    ),
    od_key(0x27F0, 0x01): ObjectDictionaryEntry(
        0x27F0,
        0x01,
        "AP parameter access direction",
        "uint8",
    ),
    od_key(0x27F0, 0x02): ObjectDictionaryEntry(
        0x27F0,
        0x02,
        "AP parameter access module number",
        "uint16",
    ),
    od_key(0x27F0, 0x03): ObjectDictionaryEntry(
        0x27F0,
        0x03,
        "AP parameter ID",
        "uint32",
    ),
    od_key(0x27F0, 0x04): ObjectDictionaryEntry(
        0x27F0,
        0x04,
        "AP parameter instance",
        "uint16",
    ),
    od_key(0x27F0, 0x05): ObjectDictionaryEntry(
        0x27F0,
        0x05,
        "AP parameter access status/error",
        "uint16",
    ),
    od_key(0x27F0, 0x06): ObjectDictionaryEntry(
        0x27F0,
        0x06,
        "AP parameter access data length",
        "uint16",
    ),
    od_key(0x27F0, 0x07): ObjectDictionaryEntry(
        0x27F0,
        0x07,
        "AP parameter access data",
        "byte_array",
    ),
    od_key(0x27F1): ObjectDictionaryEntry(
        0x27F1,
        0,
        "Stored parameter NV entries",
        "uint8",
        default=3,
    ),
    od_key(0x27F1, 0x01): ObjectDictionaryEntry(
        0x27F1,
        0x01,
        "Stored parameter NV mode",
        "uint8",
    ),
    od_key(0x27F1, 0x02): ObjectDictionaryEntry(
        0x27F1,
        0x02,
        "Stored parameter NV loaded",
        "bool",
    ),
    od_key(0x27F1, 0x03): ObjectDictionaryEntry(
        0x27F1,
        0x03,
        "Stored parameter NV used memory percent",
        "uint8",
    ),
    od_key(0xF000): ObjectDictionaryEntry(
        0xF000,
        0,
        "Modular device profile entries",
        "uint8",
    ),
    od_key(0xF000, 0x01): ObjectDictionaryEntry(
        0xF000,
        0x01,
        "Module index distance",
        "uint16",
        default=0x10,
    ),
    od_key(0xF000, 0x02): ObjectDictionaryEntry(
        0xF000,
        0x02,
        "Maximum number of modules",
        "uint16",
    ),
    od_key(0xF000, 0x03): ObjectDictionaryEntry(
        0xF000,
        0x03,
        "General configuration",
        "uint32",
    ),
    od_key(0xF000, 0x04): ObjectDictionaryEntry(
        0xF000,
        0x04,
        "General information",
        "uint32",
    ),
    od_key(0xF980, 0x01): ObjectDictionaryEntry(
        0xF980,
        0x01,
        "Safety address of first safety module",
        "uint16",
    ),
}

CPX_AP_I_EC_OBJECTS = {
    **ETHERCAT_OBJECTS,
    **CPX_AP_I_EC_VENDOR_OBJECTS,
}


def cpx_object(index, subindex=0):
    key = od_key(index, subindex)
    if key in CPX_AP_I_EC_OBJECTS:
        return CPX_AP_I_EC_OBJECTS[key]

    dynamic_object = cpx_dynamic_object(index, subindex)
    if dynamic_object is not None:
        return dynamic_object

    return pdo_object_from_dictionary(
        CPX_AP_I_EC_OBJECTS,
        index,
        subindex,
    )


def cpx_dynamic_object(index, subindex=0):
    index = int(index)
    subindex = int(subindex)
    if is_isdu_access_index(index):
        return cpx_isdu_access_object(index, subindex)
    if 0x9000 <= index <= 0x9FFF:
        return cpx_module_information_object(index, subindex)
    if is_module_diagnosis_index(index):
        return cpx_module_diagnosis_object(index, subindex)
    if 0xF030 <= index <= 0xF03F:
        return cpx_module_ident_list_object(
            index,
            subindex,
            "Configured module ident",
        )
    if 0xF050 <= index <= 0xF05F:
        return cpx_module_ident_list_object(
            index,
            subindex,
            "Detected module ident",
        )
    return None


def is_isdu_access_index(index):
    return 0x2001 <= int(index) <= 0x2FF1 and ((int(index) - 0x2001) % 0x10) == 0


def is_module_diagnosis_index(index):
    return 0xA000 <= int(index) <= 0xA4F0 and ((int(index) - 0xA000) % 0x10) == 0


def cpx_isdu_access_object(index, subindex):
    entries = {
        0: ("ISDU access entries", "uint8"),
        1: ("ISDU access direction", "uint8"),
        2: ("ISDU channel", "uint8"),
        3: ("ISDU index", "uint16"),
        4: ("ISDU subindex", "uint8"),
        5: ("ISDU error", "uint16"),
        6: ("ISDU data length", "uint8"),
        7: ("ISDU data", "byte_array"),
    }
    if subindex not in entries:
        return None
    name, data_type = entries[subindex]
    return ObjectDictionaryEntry(index, subindex, name, data_type)


def cpx_module_information_object(index, subindex):
    entries = {
        0: ("Module information entries", "uint8"),
        1: ("Address of the module", "uint16"),
        2: ("Module type string", "visible_string"),
        3: ("Module name string", "visible_string"),
        4: ("Module device type", "uint32"),
        5: ("Module vendor ID", "uint32"),
        6: ("Module product code", "uint32"),
        7: ("Module revision number", "uint32"),
        8: ("Module serial number", "uint32"),
        9: ("Module PDO group", "uint16"),
        10: ("Module ident", "uint32"),
        11: ("Module slot", "uint16"),
        12: ("Module slot group", "uint16"),
        30: ("Module network segment address", "octet_string"),
        31: ("Module network port", "uint32"),
        32: ("Festo product key", "visible_string"),
        33: ("Festo part number", "uint32"),
        34: ("Module firmware version", "visible_string"),
    }
    if subindex not in entries:
        return None
    name, data_type = entries[subindex]
    return ObjectDictionaryEntry(index, subindex, name, data_type)


def cpx_module_diagnosis_object(index, subindex):
    entries = {
        0: ("Module diagnosis entries", "uint8"),
        1: ("Module diagnosis state", "uint32"),
        2: ("Active diagnosis count", "uint16"),
        3: ("Submodule of latest diagnosis", "uint16"),
        4: ("Channel of diagnosis", "uint16"),
        5: ("Diagnosis code", "uint32"),
    }
    if subindex in entries:
        name, data_type = entries[subindex]
        return ObjectDictionaryEntry(index, subindex, name, data_type)
    if 6 <= subindex <= 255:
        return ObjectDictionaryEntry(
            index,
            subindex,
            f"IO-Link port {subindex - 6} event code",
            "uint32",
        )
    return None


def cpx_module_ident_list_object(index, subindex, label):
    if subindex == 0:
        return ObjectDictionaryEntry(index, subindex, f"{label} list entries", "uint8")
    if 1 <= subindex <= 255:
        return ObjectDictionaryEntry(
            index,
            subindex,
            f"{label} at position {subindex}",
            "uint32",
        )
    return None
