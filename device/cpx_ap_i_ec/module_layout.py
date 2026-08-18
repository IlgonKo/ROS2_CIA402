from dataclasses import dataclass, replace
import re

from config_file import split_indexed_config_list
from device.cpx_ap_i_ec.esi_module_catalog import (
    module_info_by_ident,
    module_info_by_name,
)


DIGITAL_MODULE_TYPES = {"di", "do", "dio"}
ANALOG_MODULE_TYPES = {"ai", "ao", "aio"}
IO_LINK_MODULE_TYPES = {"iol"}
SUPPORTED_MODULE_TYPES = (
    DIGITAL_MODULE_TYPES
    | ANALOG_MODULE_TYPES
    | IO_LINK_MODULE_TYPES
)


@dataclass(frozen=True)
class DigitalModuleSpec:
    digital_inputs: int = 0
    digital_outputs: int = 0

    def to_dict(self):
        return {
            "digital_inputs": self.digital_inputs,
            "digital_outputs": self.digital_outputs,
        }


@dataclass(frozen=True)
class AnalogModuleSpec:
    analog_inputs: int = 0
    analog_outputs: int = 0
    analog_bits: int = 16
    analog_signed: bool = True

    @property
    def analog_bytes(self):
        return self.analog_bits // 8

    def to_dict(self):
        return {
            "analog_inputs": self.analog_inputs,
            "analog_outputs": self.analog_outputs,
            "analog_bits": self.analog_bits,
            "analog_signed": self.analog_signed,
        }


@dataclass(frozen=True)
class IoLinkModuleSpec:
    ports: int
    input_data_bytes: int
    output_data_bytes: int

    def to_dict(self):
        return {
            "io_link_ports": self.ports,
            "io_link_input_data_bytes": self.input_data_bytes,
            "io_link_output_data_bytes": self.output_data_bytes,
        }


@dataclass(frozen=True)
class CPXApModule:
    slot: int
    module_type: str
    raw: str
    spec: DigitalModuleSpec | AnalogModuleSpec | IoLinkModuleSpec
    input_offset: int | None = None
    output_offset: int | None = None
    input_bytes: int = 0
    output_bytes: int = 0

    @property
    def digital_inputs(self):
        if isinstance(self.spec, DigitalModuleSpec):
            return self.spec.digital_inputs
        return 0

    @property
    def digital_outputs(self):
        if isinstance(self.spec, DigitalModuleSpec):
            return self.spec.digital_outputs
        return 0

    @property
    def analog_inputs(self):
        if isinstance(self.spec, AnalogModuleSpec):
            return self.spec.analog_inputs
        return 0

    @property
    def analog_outputs(self):
        if isinstance(self.spec, AnalogModuleSpec):
            return self.spec.analog_outputs
        return 0

    @property
    def analog_bits(self):
        if isinstance(self.spec, AnalogModuleSpec):
            return self.spec.analog_bits
        return 0

    @property
    def analog_signed(self):
        if isinstance(self.spec, AnalogModuleSpec):
            return self.spec.analog_signed
        return True

    @property
    def analog_bytes(self):
        if isinstance(self.spec, AnalogModuleSpec):
            return self.spec.analog_bytes
        return 0

    @property
    def io_link_ports(self):
        if isinstance(self.spec, IoLinkModuleSpec):
            return self.spec.ports
        return 0

    @property
    def io_link_input_data_bytes(self):
        if isinstance(self.spec, IoLinkModuleSpec):
            return self.spec.input_data_bytes
        return 0

    @property
    def io_link_output_data_bytes(self):
        if isinstance(self.spec, IoLinkModuleSpec):
            return self.spec.output_data_bytes
        return 0

    @property
    def has_analog_data(self):
        return isinstance(self.spec, AnalogModuleSpec)

    @property
    def has_input_image(self):
        return self.input_bytes > 0

    @property
    def has_output_image(self):
        return self.output_bytes > 0

    def to_dict(self):
        result = {
            "slot": self.slot,
            "type": self.module_type,
            "raw": self.raw,
            "input_offset": self.input_offset,
            "output_offset": self.output_offset,
            "input_bytes": self.input_bytes,
            "output_bytes": self.output_bytes,
        }
        result.update(self.spec.to_dict())
        return result


@dataclass(frozen=True)
class CPXApLayout:
    modules: tuple[CPXApModule, ...]
    station_input_bytes: int = 0
    station_output_bytes: int = 1

    @property
    def input_bytes(self):
        return (
            sum(module.input_bytes for module in self.modules)
            + self.station_input_bytes
        )

    @property
    def output_bytes(self):
        return (
            sum(module.output_bytes for module in self.modules)
            + self.station_output_bytes
        )

    @property
    def digital_inputs(self):
        return sum(module.digital_inputs for module in self.modules)

    @property
    def digital_outputs(self):
        return sum(module.digital_outputs for module in self.modules)

    @property
    def analog_inputs(self):
        return sum(module.analog_inputs for module in self.modules)

    @property
    def analog_outputs(self):
        return sum(module.analog_outputs for module in self.modules)

    @property
    def io_link_ports(self):
        return sum(module.io_link_ports for module in self.modules)

    @property
    def analog_modules(self):
        return tuple(module for module in self.modules if module.has_analog_data)

    @property
    def analog_bytes(self):
        return common_analog_property(
            self.analog_modules,
            "analog_bytes",
            default=2,
        )

    @property
    def analog_signed(self):
        return common_analog_property(
            self.analog_modules,
            "analog_signed",
            default=True,
        )

    def to_dict(self):
        return {
            "input_bytes": self.input_bytes,
            "output_bytes": self.output_bytes,
            "digital_inputs": self.digital_inputs,
            "digital_outputs": self.digital_outputs,
            "analog_inputs": self.analog_inputs,
            "analog_outputs": self.analog_outputs,
            "io_link_ports": self.io_link_ports,
            "station_input_bytes": self.station_input_bytes,
            "station_output_bytes": self.station_output_bytes,
            "modules": [module.to_dict() for module in self.modules],
        }


def parse_cpx_ap_modules(
    raw_modules,
    analog_bits=16,
    analog_signed=True,
    io_link_module_sizes=None,
):
    io_link_module_sizes = io_link_module_sizes or {}
    modules = []
    for slot, raw_module in split_module_list(raw_modules):
        modules.append(parse_cpx_ap_module(
            slot,
            raw_module,
            analog_bits,
            analog_signed,
            io_link_module_sizes,
        ))
    return CPXApLayout(tuple(assign_process_image_offsets(modules)))


def assign_process_image_offsets(modules):
    input_offset = 0
    output_offset = 0
    result = []

    for module in modules:
        result.append(replace(
            module,
            input_offset=input_offset if module.input_bytes else None,
            output_offset=output_offset if module.output_bytes else None,
        ))
        input_offset += module.input_bytes
        output_offset += module.output_bytes

    return result


def split_module_list(raw_modules):
    return split_indexed_config_list(raw_modules, default_start=1)


def parse_cpx_ap_module(
    slot,
    raw_module,
    analog_bits=16,
    analog_signed=True,
    io_link_module_sizes=None,
):
    explicit_module = parse_explicit_cpx_ap_module(
        slot,
        raw_module,
        analog_signed,
    )
    if explicit_module is not None:
        return explicit_module

    parts = [
        part.strip().lower()
        for part in str(raw_module).split(":")
        if part.strip()
    ]
    if not parts:
        raise ValueError("empty CPX AP module declaration")

    module_type = parts[0]
    if module_type not in SUPPORTED_MODULE_TYPES:
        raise ValueError(
            f"Unsupported CPX AP module type {module_type!r}. "
            f"Supported: {', '.join(sorted(SUPPORTED_MODULE_TYPES))}"
        )

    analog_bytes = analog_byte_width(analog_bits)
    if module_type == "di":
        return digital_input_module(slot, raw_module, parts)
    if module_type == "do":
        return digital_output_module(slot, raw_module, parts)
    if module_type == "dio":
        return mixed_digital_module(slot, raw_module, parts)
    if module_type == "ai":
        return analog_input_module(
            slot,
            raw_module,
            parts,
            analog_bits,
            analog_bytes,
            analog_signed,
        )
    if module_type == "ao":
        return analog_output_module(
            slot,
            raw_module,
            parts,
            analog_bits,
            analog_bytes,
            analog_signed,
        )
    if module_type == "aio":
        return mixed_analog_module(
            slot,
            raw_module,
            parts,
            analog_bits,
            analog_bytes,
            analog_signed,
        )
    if module_type == "iol":
        return io_link_module(
            slot,
            raw_module,
            parts,
            io_link_module_sizes or {},
        )

    raise ValueError(f"Unsupported CPX AP module type {module_type!r}")


def digital_input_module(slot, raw_module, parts):
    require_part_count(raw_module, parts, 2)
    points = parse_non_negative_int(parts[1], raw_module)
    return CPXApModule(
        slot=slot,
        module_type="di",
        raw=str(raw_module),
        spec=DigitalModuleSpec(digital_inputs=points),
        input_bytes=bytes_for_bits(points),
    )


def digital_output_module(slot, raw_module, parts):
    require_part_count(raw_module, parts, 2)
    points = parse_non_negative_int(parts[1], raw_module)
    return CPXApModule(
        slot=slot,
        module_type="do",
        raw=str(raw_module),
        spec=DigitalModuleSpec(digital_outputs=points),
        output_bytes=bytes_for_bits(points),
    )


def mixed_digital_module(slot, raw_module, parts):
    require_part_count(raw_module, parts, 3)
    input_points = parse_io_count(parts[1], raw_module, "i", "in")
    output_points = parse_io_count(parts[2], raw_module, "o", "out")
    return CPXApModule(
        slot=slot,
        module_type="dio",
        raw=str(raw_module),
        spec=DigitalModuleSpec(
            digital_inputs=input_points,
            digital_outputs=output_points,
        ),
        input_bytes=bytes_for_bits(input_points),
        output_bytes=bytes_for_bits(output_points),
    )


def analog_input_module(
    slot,
    raw_module,
    parts,
    analog_bits,
    analog_bytes,
    analog_signed,
):
    require_part_count(raw_module, parts, 2)
    channels = parse_non_negative_int(parts[1], raw_module)
    return CPXApModule(
        slot=slot,
        module_type="ai",
        raw=str(raw_module),
        spec=AnalogModuleSpec(
            analog_inputs=channels,
            analog_bits=analog_bits,
            analog_signed=analog_signed,
        ),
        input_bytes=channels * analog_bytes,
    )


def analog_output_module(
    slot,
    raw_module,
    parts,
    analog_bits,
    analog_bytes,
    analog_signed,
):
    require_part_count(raw_module, parts, 2)
    channels = parse_non_negative_int(parts[1], raw_module)
    return CPXApModule(
        slot=slot,
        module_type="ao",
        raw=str(raw_module),
        spec=AnalogModuleSpec(
            analog_outputs=channels,
            analog_bits=analog_bits,
            analog_signed=analog_signed,
        ),
        output_bytes=channels * analog_bytes,
    )


def mixed_analog_module(
    slot,
    raw_module,
    parts,
    analog_bits,
    analog_bytes,
    analog_signed,
):
    require_part_count(raw_module, parts, 3)
    input_channels = parse_io_count(parts[1], raw_module, "i", "in")
    output_channels = parse_io_count(parts[2], raw_module, "o", "out")
    return CPXApModule(
        slot=slot,
        module_type="aio",
        raw=str(raw_module),
        spec=AnalogModuleSpec(
            analog_inputs=input_channels,
            analog_outputs=output_channels,
            analog_bits=analog_bits,
            analog_signed=analog_signed,
        ),
        input_bytes=input_channels * analog_bytes,
        output_bytes=output_channels * analog_bytes,
    )


def io_link_module(slot, raw_module, parts, io_link_module_sizes):
    if len(parts) == 2:
        ports = parse_non_negative_int(parts[1], raw_module)
        size = io_link_module_sizes.get(int(slot))
        if size is None:
            raise ValueError(
                f"Invalid CPX AP IO-Link module {raw_module!r}; "
                "expected iol:<ports>:in<input_bytes>:out<output_bytes> "
                "or matching MOTION_SERVER_IO_<io>_IOL_PORTS entries."
            )
        input_bytes_per_port, output_bytes_per_port = size
        input_bytes = input_bytes_per_port * ports
        output_bytes = output_bytes_per_port * ports
        return CPXApModule(
            slot=slot,
            module_type="iol",
            raw=str(raw_module),
            spec=IoLinkModuleSpec(
                ports=ports,
                input_data_bytes=input_bytes,
                output_data_bytes=output_bytes,
            ),
            input_bytes=input_bytes + ports,
            output_bytes=output_bytes,
        )

    if len(parts) < 4:
        raise ValueError(
            f"Invalid CPX AP IO-Link module {raw_module!r}; "
            "expected iol:<ports>:in<input_bytes>:out<output_bytes>"
        )

    ports = parse_non_negative_int(parts[1], raw_module)
    input_bytes = None
    output_bytes = None
    for part in parts[2:]:
        if part.startswith("in"):
            input_bytes = parse_non_negative_int(part[2:], raw_module)
        elif part.startswith("out"):
            output_bytes = parse_non_negative_int(part[3:], raw_module)
        else:
            raise ValueError(
                f"Invalid CPX AP IO-Link token {part!r} in {raw_module!r}"
            )

    if input_bytes is None or output_bytes is None:
        raise ValueError(
            f"Invalid CPX AP IO-Link module {raw_module!r}; "
            "both in<input_bytes> and out<output_bytes> are required"
        )

    return CPXApModule(
        slot=slot,
        module_type="iol",
        raw=str(raw_module),
        spec=IoLinkModuleSpec(
            ports=ports,
            input_data_bytes=input_bytes,
            output_data_bytes=output_bytes,
        ),
        input_bytes=input_bytes + ports,
        output_bytes=output_bytes,
    )


def parse_io_count(token, raw_module, *prefixes):
    token = str(token).strip().lower()
    for prefix in prefixes:
        if token.startswith(prefix):
            return parse_non_negative_int(token[len(prefix):], raw_module)
    return parse_non_negative_int(token, raw_module)


def parse_non_negative_int(value, raw_module):
    try:
        parsed = int(str(value).strip(), 0)
    except ValueError as exc:
        raise ValueError(
            f"Invalid numeric value {value!r} in CPX AP module {raw_module!r}"
        ) from exc
    if parsed < 0:
        raise ValueError(
            f"Negative numeric value {value!r} in CPX AP module {raw_module!r}"
        )
    return parsed


def require_part_count(raw_module, parts, expected):
    if len(parts) != expected:
        raise ValueError(
            f"Invalid CPX AP module {raw_module!r}; "
            f"expected {expected} ':' separated fields"
        )


def analog_byte_width(analog_bits):
    analog_bits = int(analog_bits)
    if analog_bits not in (8, 16, 32):
        raise ValueError(
            f"Unsupported CPX analog bit width {analog_bits}; "
            "expected 8, 16, or 32"
        )
    return analog_bits // 8


def common_analog_property(modules, attribute, default):
    if not modules:
        return default
    values = {getattr(module, attribute) for module in modules}
    if len(values) != 1:
        raise ValueError(
            f"Mixed CPX analog {attribute} values are not supported yet"
        )
    return values.pop()


def bytes_for_bits(bit_count):
    return (max(0, int(bit_count)) + 7) // 8


def parse_explicit_cpx_ap_module(slot, raw_module, analog_signed=True):
    info = explicit_module_info(raw_module)
    if info is None:
        return None
    return module_from_esi_info(slot, raw_module, info, analog_signed)


def explicit_module_info(raw_module):
    value = str(raw_module).strip()
    lowered = value.lower()
    for prefix in ("ident:", "module_ident:"):
        if lowered.startswith(prefix):
            return module_info_by_ident(int(value[len(prefix):], 0))
    if normalized_module_name(value).startswith("cpx-ap-i-"):
        return module_info_by_name(value)
    return None


def module_from_esi_info(slot, raw_module, info, analog_signed=True):
    name = info.type_name
    normalized_name = normalized_module_name(name)

    if "iol" in normalized_name:
        ports = parse_module_count(normalized_name, "iol", raw_module)
        input_data_bytes = info.txpdo_bytes - ports
        output_data_bytes = info.rxpdo_bytes
        if input_data_bytes < 0:
            raise ValueError(
                f"Invalid CPX AP IO-Link ESI size for {raw_module!r}"
            )
        return CPXApModule(
            slot=slot,
            module_type="iol",
            raw=str(raw_module),
            spec=IoLinkModuleSpec(
                ports=ports,
                input_data_bytes=input_data_bytes,
                output_data_bytes=output_data_bytes,
            ),
            input_bytes=info.txpdo_bytes,
            output_bytes=info.rxpdo_bytes,
        )

    digital_spec = digital_spec_from_name(normalized_name, raw_module)
    if digital_spec is not None:
        module_type = "dio"
        if digital_spec.digital_inputs and not digital_spec.digital_outputs:
            module_type = "di"
        elif digital_spec.digital_outputs and not digital_spec.digital_inputs:
            module_type = "do"
        return CPXApModule(
            slot=slot,
            module_type=module_type,
            raw=str(raw_module),
            spec=digital_spec,
            input_bytes=info.txpdo_bytes,
            output_bytes=info.rxpdo_bytes,
        )

    analog_spec = analog_spec_from_name(
        normalized_name,
        raw_module,
        info,
        analog_signed,
    )
    if analog_spec is not None:
        module_type = "aio"
        if analog_spec.analog_inputs and not analog_spec.analog_outputs:
            module_type = "ai"
        elif analog_spec.analog_outputs and not analog_spec.analog_inputs:
            module_type = "ao"
        return CPXApModule(
            slot=slot,
            module_type=module_type,
            raw=str(raw_module),
            spec=analog_spec,
            input_bytes=info.txpdo_bytes,
            output_bytes=info.rxpdo_bytes,
        )

    raise ValueError(
        f"Cannot infer CPX AP module layout from ESI name {name!r}. "
        "Use shorthand syntax such as di:8, do:8, dio:4:4, ai:4, "
        "ao:2, aio:4:4, or iol:4:in32:out32."
    )


def digital_spec_from_name(normalized_name, raw_module):
    mixed = re.search(r"(\d+)di(\d+)do", normalized_name)
    if mixed:
        return DigitalModuleSpec(
            digital_inputs=parse_non_negative_int(mixed.group(1), raw_module),
            digital_outputs=parse_non_negative_int(mixed.group(2), raw_module),
        )

    mixed = re.search(r"(\d+)dio", normalized_name)
    if mixed:
        points = parse_non_negative_int(mixed.group(1), raw_module)
        return DigitalModuleSpec(
            digital_inputs=points,
            digital_outputs=points,
        )

    inputs = re.search(r"(\d+)di", normalized_name)
    if inputs:
        return DigitalModuleSpec(
            digital_inputs=parse_non_negative_int(inputs.group(1), raw_module),
        )

    outputs = re.search(r"(\d+)do", normalized_name)
    if outputs:
        return DigitalModuleSpec(
            digital_outputs=parse_non_negative_int(outputs.group(1), raw_module),
        )

    return None


def analog_spec_from_name(normalized_name, raw_module, info, analog_signed):
    mixed = re.search(r"(\d+)ai(\d+)ao", normalized_name)
    if mixed:
        analog_inputs = parse_non_negative_int(mixed.group(1), raw_module)
        analog_outputs = parse_non_negative_int(mixed.group(2), raw_module)
    else:
        inputs = re.search(r"(\d+)ai", normalized_name)
        outputs = re.search(r"(\d+)ao", normalized_name)
        analog_inputs = (
            parse_non_negative_int(inputs.group(1), raw_module)
            if inputs
            else 0
        )
        analog_outputs = (
            parse_non_negative_int(outputs.group(1), raw_module)
            if outputs
            else 0
        )

    if not analog_inputs and not analog_outputs:
        return None

    input_bits = analog_bits_from_pdo_size(info.txpdo_bytes, analog_inputs)
    output_bits = analog_bits_from_pdo_size(info.rxpdo_bytes, analog_outputs)
    analog_bits = input_bits or output_bits or 16
    if input_bits and output_bits and input_bits != output_bits:
        raise ValueError(
            f"Mixed analog bit widths are not supported for {raw_module!r}"
        )

    return AnalogModuleSpec(
        analog_inputs=analog_inputs,
        analog_outputs=analog_outputs,
        analog_bits=analog_bits,
        analog_signed=analog_signed,
    )


def analog_bits_from_pdo_size(byte_count, channels):
    channels = int(channels)
    if channels <= 0:
        return 0
    bits = int(byte_count) * 8 // channels
    if bits not in (8, 16, 32):
        raise ValueError(
            f"Unsupported CPX AP analog channel width inferred from ESI: "
            f"{bits} bits"
        )
    return bits


def parse_module_count(normalized_name, suffix, raw_module):
    match = re.search(rf"(\d+){suffix}", normalized_name)
    if not match:
        raise ValueError(f"Cannot infer module count from {raw_module!r}")
    return parse_non_negative_int(match.group(1), raw_module)


def normalized_module_name(raw_module):
    return (
        str(raw_module)
        .strip()
        .lower()
        .replace("_", "-")
        .replace(" ", "-")
    )
