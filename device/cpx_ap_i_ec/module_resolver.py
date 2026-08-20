from dataclasses import replace

from device.cpx_ap_i_ec.esi_module_catalog import (
    interface_module_info,
    module_info_by_ident,
    module_info_by_name,
)
from device.cpx_ap_i_ec.module_layout import (
    CPXApLayout,
    IoLinkModuleSpec,
    assign_process_image_offsets,
)


DEFAULT_MODULE_NAMES = {
    ("di", 8): "CPX-AP-I-8DI-M8-3P",
    ("di", 16): "CPX-AP-I-16DI-M8-3P",
    ("do", 8): "CPX-AP-I-8DO-M8-3P",
    ("dio", 4, 4): "CPX-AP-I-4DI4DO-M8-3P",
    ("dio", 16, 16): "CPX-AP-I-16DIO-M8-3P",
    ("ai", 4): "CPX-AP-I-4AI-U-I-RTD-M12",
    ("aio", 4, 4): "CPX-AP-I-4AI4AO-U-I-M12",
}


def expected_module_idents(layout):
    return [
        interface_module_info().ident,
        *[
            module_ident(module)
            for module in layout.modules
        ],
    ]


def module_ident(module):
    explicit_ident = explicit_module_ident(module.raw)
    if explicit_ident is not None:
        return explicit_ident

    name_info = module_info_from_raw_name(module.raw)
    if name_info is not None:
        return name_info.ident

    if isinstance(module.spec, IoLinkModuleSpec):
        return io_link_module_info(module).ident

    return default_module_info(module).ident


def module_display_name(module):
    name_info = module_info_from_raw_name(module.raw)
    if name_info is not None:
        return name_info.type_name

    explicit_ident = explicit_module_ident(module.raw)
    if explicit_ident is not None:
        return module_info_by_ident(explicit_ident).type_name

    if isinstance(module.spec, IoLinkModuleSpec):
        return io_link_module_info(module).type_name

    return default_module_info(module).type_name


def validate_layout_against_esi(layout):
    for module in layout.modules:
        info = module_info(module)
        if module.output_bytes != info.rxpdo_bytes:
            raise ValueError(
                "CPX AP module RxPDO/output size mismatch against ESI. "
                f"slot={module.slot} module={module.raw!r} "
                f"configured={module.output_bytes} bytes "
                f"esi={info.rxpdo_bytes} bytes"
            )
        if module.input_bytes != info.txpdo_bytes:
            raise ValueError(
                "CPX AP module TxPDO/input size mismatch against ESI. "
                f"slot={module.slot} module={module.raw!r} "
                f"configured={module.input_bytes} bytes "
                f"esi={info.txpdo_bytes} bytes"
            )


def layout_with_esi_pdo_sizes(layout):
    modules = [
        module_with_esi_pdo_size(module)
        for module in layout.modules
    ]
    return CPXApLayout(
        tuple(assign_process_image_offsets(modules)),
        station_input_bytes=layout.station_input_bytes,
        station_output_bytes=layout.station_output_bytes,
    )


def module_with_esi_pdo_size(module):
    info = module_info(module)
    if (
        int(module.output_bytes) == int(info.rxpdo_bytes)
        and int(module.input_bytes) == int(info.txpdo_bytes)
    ):
        return module
    return replace(
        module,
        input_bytes=info.txpdo_bytes,
        output_bytes=info.rxpdo_bytes,
    )


def module_info(module):
    explicit_ident = explicit_module_ident(module.raw)
    if explicit_ident is not None:
        return module_info_by_ident(explicit_ident)

    name_info = module_info_from_raw_name(module.raw)
    if name_info is not None:
        return name_info

    if isinstance(module.spec, IoLinkModuleSpec):
        return io_link_module_info(module)

    return default_module_info(module)


def module_info_for_ap_module(layout, module_number):
    module_number = int(module_number)
    if module_number == 0:
        return interface_module_info()
    for module in layout.modules:
        if int(module.slot) == module_number:
            return module_info(module)
    raise ValueError(f"Unknown CPX AP module number: {module_number}")


def explicit_module_ident(raw_module):
    value = str(raw_module).strip().lower()
    for prefix in ("ident:", "module_ident:"):
        if value.startswith(prefix):
            return int(value[len(prefix):], 0)
    return None


def module_info_from_raw_name(raw_module):
    value = normalized_module_name(raw_module)
    if not value.startswith("cpx-ap-i-"):
        return None
    try:
        return module_info_by_name(value)
    except KeyError:
        return None


def normalized_module_name(raw_module):
    return (
        str(raw_module)
        .strip()
        .lower()
        .replace("_", "-")
        .replace(" ", "-")
    )


def io_link_module_info(module):
    if module.io_link_ports != 4:
        raise ValueError(
            f"No CPX-AP-I-EC IO-Link ident mapping for {module.raw!r}. "
            "Only 4-port CPX-AP-I-4IOL-M12 variants are supported."
        )
    bytes_per_port = io_link_bytes_per_port(module)
    try:
        return module_info_by_name(
            f"CPX-AP-I-4IOL-M12 Variant {bytes_per_port}"
        )
    except KeyError as exc:
        raise ValueError(
            f"No CPX-AP-I-4IOL-M12 ident mapping for {module.raw!r}. "
            f"Supported per-port process data bytes: "
            "2, 4, 8, 16, 32."
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


def default_module_info(module):
    key = default_module_key(module)
    try:
        return module_info_by_name(DEFAULT_MODULE_NAMES[key])
    except KeyError as exc:
        raise ValueError(
            f"No CPX-AP module mapping for {module.raw!r}. "
            "Use an exact module name such as "
            "'CPX-AP-I-8DI-M12-5P' or an explicit 'ident:0x00002008'."
        ) from exc
