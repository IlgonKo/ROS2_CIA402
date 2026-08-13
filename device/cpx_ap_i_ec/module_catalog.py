from device.cpx_ap_i_ec.module_layout import IoLinkModuleSpec


INTERFACE_MODULE_IDENT = 0x00002084  # CPX-AP-I-EC-M12


DEFAULT_MODULE_IDENTS = {
    ("di", 8): 0x00002007,       # CPX-AP-I-8DI-M8-3P
    ("di", 16): 0x00002135,      # CPX-AP-I-16DI-M8-3P
    ("do", 8): 0x00002139,       # CPX-AP-I-8DO-M8-3P
    ("dio", 4, 4): 0x00002004,   # CPX-AP-I-4DI4DO-M8-3P
    ("dio", 16, 16): 0x0000213B, # CPX-AP-I-16DIO-M8-3P
    ("ai", 4): 0x0000200A,       # CPX-AP-I-4AI-U-I-RTD-M12
    ("aio", 4, 4): 0x00002134,   # CPX-AP-I-4AI4AO-U-I-M12
}


IO_LINK_VARIANT_IDENTS = {
    2: 0x0000200E,   # CPX-AP-I-4IOL-M12 Variant 2
    4: 0x00002010,   # CPX-AP-I-4IOL-M12 Variant 4
    8: 0x00002009,   # CPX-AP-I-4IOL-M12 Variant 8
    16: 0x00002012,  # CPX-AP-I-4IOL-M12 Variant 16
    32: 0x00002014,  # CPX-AP-I-4IOL-M12 Variant 32
}


MODULE_NAME_IDENTS = {
    "cpx-ap-i-8di-m12-5p": 0x00002008,
    "cpx-ap-i-8di-m8-3p": 0x00002007,
    "cpx-ap-i-8di-m8-3p-a": 0x00002142,
    "cpx-ap-i-8di-m12-5p-ex2-cs": 0x0000213F,
    "cpx-ap-i-16di-m12-5p": 0x00002136,
    "cpx-ap-i-16di-m8-3p": 0x00002135,
    "cpx-ap-i-8do-m12-5p": 0x0000213A,
    "cpx-ap-i-8do-m8-3p": 0x00002139,
    "cpx-ap-i-4di4do-m12-5p": 0x00002005,
    "cpx-ap-i-4di4do-m8-3p": 0x00002004,
    "cpx-ap-i-4di4do-m12-5p-ex2-cs": 0x00002140,
    "cpx-ap-i-16dio-m12-5p": 0x0000213C,
    "cpx-ap-i-16dio-m8-3p": 0x0000213B,
    "cpx-ap-i-4ai-u-i-rtd-m12": 0x0000200A,
    "cpx-ap-i-4ai-u-i-rtd-m12-ex2-cs": 0x00002141,
    "cpx-ap-i-4ai4ao-u-i-m12": 0x00002134,
    "cpx-ap-i-4iol-m12-variant-2": 0x0000200E,
    "cpx-ap-i-4iol-m12-variant-4": 0x00002010,
    "cpx-ap-i-4iol-m12-variant-8": 0x00002009,
    "cpx-ap-i-4iol-m12-variant-16": 0x00002012,
    "cpx-ap-i-4iol-m12-variant-32": 0x00002014,
}


def expected_module_idents(layout):
    return [
        INTERFACE_MODULE_IDENT,
        *[
            module_ident(module)
            for module in layout.modules
        ],
    ]


def module_ident(module):
    explicit_ident = explicit_module_ident(module.raw)
    if explicit_ident is not None:
        return explicit_ident

    name_ident = module_name_ident(module.raw)
    if name_ident is not None:
        return name_ident

    if isinstance(module.spec, IoLinkModuleSpec):
        return io_link_module_ident(module)

    key = default_module_key(module)
    try:
        return DEFAULT_MODULE_IDENTS[key]
    except KeyError as exc:
        raise ValueError(
            f"No CPX-AP module ident mapping for {module.raw!r}. "
            "Use an exact module name such as "
            "'CPX-AP-I-8DI-M12-5P' or an explicit 'ident:0x00002008'."
        ) from exc


def explicit_module_ident(raw_module):
    value = str(raw_module).strip().lower()
    for prefix in ("ident:", "module_ident:"):
        if value.startswith(prefix):
            return int(value[len(prefix):], 0)
    return None


def module_name_ident(raw_module):
    value = normalized_module_name(raw_module)
    return MODULE_NAME_IDENTS.get(value)


def normalized_module_name(raw_module):
    return (
        str(raw_module)
        .strip()
        .lower()
        .replace("_", "-")
        .replace(" ", "-")
    )


def io_link_module_ident(module):
    if module.io_link_ports != 4:
        raise ValueError(
            f"No CPX-AP-I-EC IO-Link ident mapping for {module.raw!r}. "
            "Only 4-port CPX-AP-I-4IOL-M12 variants are supported."
        )
    bytes_per_port = io_link_bytes_per_port(module)
    try:
        return IO_LINK_VARIANT_IDENTS[bytes_per_port]
    except KeyError as exc:
        raise ValueError(
            f"No CPX-AP-I-4IOL-M12 ident mapping for {module.raw!r}. "
            f"Supported per-port process data bytes: "
            f"{', '.join(str(value) for value in sorted(IO_LINK_VARIANT_IDENTS))}."
        ) from exc


def io_link_bytes_per_port(module):
    spec = module.spec
    input_bytes = int(spec.input_data_bytes)
    output_bytes = int(spec.output_data_bytes)
    ports = int(spec.ports)
    if ports <= 0:
        raise ValueError(f"Invalid IO-Link port count in {module.raw!r}")
    if input_bytes % ports != 0 or output_bytes % ports != 0:
        raise ValueError(
            f"IO-Link process data bytes must divide evenly by port count: "
            f"{module.raw!r}"
        )
    input_per_port = input_bytes // ports
    output_per_port = output_bytes // ports
    if input_per_port != output_per_port:
        raise ValueError(
            f"CPX-AP-I-4IOL-M12 variants require equal input/output bytes "
            f"per port: {module.raw!r}"
        )
    return input_per_port


def default_module_key(module):
    if module.module_type == "di":
        return ("di", module.digital_inputs)
    if module.module_type == "do":
        return ("do", module.digital_outputs)
    if module.module_type == "dio":
        return ("dio", module.digital_inputs, module.digital_outputs)
    if module.module_type == "ai":
        return ("ai", module.analog_inputs)
    if module.module_type == "ao":
        return ("ao", module.analog_outputs)
    if module.module_type == "aio":
        return ("aio", module.analog_inputs, module.analog_outputs)
    return (module.module_type,)
