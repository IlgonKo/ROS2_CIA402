from device.cpx_ap_i_ec.module_catalog import expected_module_idents


CONFIGURED_MODULE_LIST_INDEX = 0xF030
DETECTED_MODULE_LIST_INDEX = 0xF050
MAX_MODULE_IDENTS = 80


def configure_ap_module_idents(master, slave_index, config):
    expected = expected_module_idents(config.layout)
    if len(expected) > MAX_MODULE_IDENTS:
        raise ValueError(
            f"CPX-AP-I-EC station {config.io_id!r} has {len(expected)} "
            f"modules; max supported by 0xF030/0xF050 is {MAX_MODULE_IDENTS}."
        )

    detected = read_detected_module_idents(master, slave_index)
    validate_module_idents(
        "detected",
        config.io_id,
        expected,
        detected,
    )

    write_configured_module_idents(master, slave_index, expected)
    configured = read_configured_module_idents(master, slave_index)
    validate_module_idents(
        "configured",
        config.io_id,
        detected,
        configured,
    )

    print(
        "Slave "
        f"{slave_index}: CPX-AP-I-EC module idents validated "
        f"io_id={config.io_id} idents={format_idents(configured)}",
        flush=True,
    )
    return configured


def read_detected_module_idents(master, slave_index):
    return read_module_idents(master, slave_index, DETECTED_MODULE_LIST_INDEX)


def read_configured_module_idents(master, slave_index):
    return read_module_idents(master, slave_index, CONFIGURED_MODULE_LIST_INDEX)


def read_module_idents(master, slave_index, index):
    count = int(master.sdo.read_uint8(slave_index, index, 0))
    if count > MAX_MODULE_IDENTS:
        raise RuntimeError(
            f"CPX module ident list 0x{index:04X} has invalid count {count}; "
            f"max supported is {MAX_MODULE_IDENTS}."
        )
    return [
        int(master.sdo.read_uint32(slave_index, index, subindex))
        for subindex in range(1, count + 1)
    ]


def write_configured_module_idents(master, slave_index, idents):
    idents = [int(ident) for ident in idents]
    master.sdo.write_uint8(
        slave_index,
        CONFIGURED_MODULE_LIST_INDEX,
        0,
        len(idents),
    )
    for subindex, ident in enumerate(idents, start=1):
        master.sdo.write_uint32(
            slave_index,
            CONFIGURED_MODULE_LIST_INDEX,
            subindex,
            ident,
        )


def validate_module_idents(label, io_id, expected, actual):
    expected = [int(value) for value in expected]
    actual = [int(value) for value in actual]
    if expected == actual:
        return
    raise RuntimeError(
        f"CPX-AP-I-EC {label} module ident mismatch for io_id={io_id}. "
        f"Expected={format_idents(expected)} Actual={format_idents(actual)}"
    )


def format_idents(idents):
    return [
        f"0x{int(ident):08X}"
        for ident in idents
    ]
