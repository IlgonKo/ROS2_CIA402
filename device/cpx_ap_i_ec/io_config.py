import os
from dataclasses import dataclass

from config_file import split_indexed_config_list
from device.cpx_ap_i_ec.module_resolver import (
    layout_with_esi_pdo_sizes,
    validate_layout_against_esi,
)
from device.cpx_ap_i_ec.module_layout import (
    CPXApLayout,
    parse_cpx_ap_modules,
)
from device.io_link.iodd_catalog import IoddDeviceInfo, iodd_device_info


IO_LINK_VARIANT_BYTES_PER_PORT = (2, 4, 8, 16, 32)
IO_LINK_NONE_DEVICE_KEYS = {"", "none", "null", "-"}


@dataclass(frozen=True)
class IoLinkDeviceBinding:
    module: int
    port: int
    device: IoddDeviceInfo

    def to_dict(self):
        input_bytes, output_bytes = self.device.process_data_size
        return {
            "module": self.module,
            "port": self.port,
            "key": self.device.key,
            "path": str(self.device.path),
            "vendor_id": self.device.vendor_id,
            "device_id": self.device.device_id,
            "vendor_name": self.device.vendor_name,
            "device_name": self.device.device_name,
            "input_bytes": input_bytes,
            "output_bytes": output_bytes,
        }


@dataclass(frozen=True)
class IoLinkModuleRef:
    ordinal: int
    slot: int
    ports: int


@dataclass(frozen=True)
class CPXIoConfig:
    io_id: str
    layout: CPXApLayout
    io_link_devices: tuple[IoLinkDeviceBinding, ...] = ()

    @property
    def digital_inputs(self):
        return self.layout.digital_inputs

    @property
    def analog_inputs(self):
        return self.layout.analog_inputs

    @property
    def digital_outputs(self):
        return self.layout.digital_outputs

    @property
    def analog_outputs(self):
        return self.layout.analog_outputs

    @property
    def input_digital_bytes(self):
        return bytes_for_bits(self.digital_inputs)

    @property
    def output_digital_bytes(self):
        return bytes_for_bits(self.digital_outputs)

    @property
    def input_bytes(self):
        return self.layout.input_bytes

    @property
    def output_bytes(self):
        return self.layout.output_bytes


def load_cpx_io_config(io_id):
    io_id = normalized_io_id(io_id)
    values = {
        key.upper(): value
        for key, value in os.environ.items()
        if key.startswith("MOTION_SERVER_IO_")
    }
    layout_key = f"MOTION_SERVER_IO_{io_id}_MODULES"
    raw_modules = env_value(values, layout_key, "")
    if not raw_modules.strip():
        raise ValueError(
            f"Missing {layout_key}. CPX-AP-I-EC I/O layouts must be declared "
            "in the common Motion Server configuration."
        )

    io_link_modules = io_link_module_refs(raw_modules)
    io_link_devices = []
    if io_link_modules:
        io_link_devices = parse_io_link_device_bindings(
            values,
            io_id,
            io_link_modules,
        )
    io_link_module_sizes = inferred_io_link_module_sizes(io_link_devices)
    layout = parse_cpx_ap_modules(
        raw_modules,
        io_link_module_sizes=io_link_module_sizes,
    )
    config = CPXIoConfig(
        io_id=io_id,
        layout=layout_with_esi_pdo_sizes(layout),
        io_link_devices=tuple(sorted(
            io_link_devices,
            key=lambda binding: (binding.module, binding.port),
        )),
    )
    validate_config(config, layout_key)
    validate_io_link_bindings(config)
    return config


def normalized_io_id(io_id):
    value = str(io_id or "").strip()
    if not value:
        raise ValueError("CPX-AP-I-EC profile requires an I/O logical id")
    return value


def env_value(values, key, default):
    return values.get(str(key).upper(), default)


def parse_io_link_device_bindings(values, io_id, io_link_modules):
    raw_ports = env_value(values, f"MOTION_SERVER_IO_{io_id}_IOL_PORTS", "")
    bindings = []
    seen = set()
    for item in split_env_list(raw_ports):
        selector, device_key = parse_io_link_port_item(item, io_link_modules)
        if selector in seen:
            raise ValueError(
                f"Duplicate IO-Link port declaration for {selector[0]}.{selector[1]}"
            )
        seen.add(selector)
        if normalized_none_key(device_key):
            continue
        bindings.append(IoLinkDeviceBinding(
            module=selector[0],
            port=selector[1],
            device=iodd_device_info(device_key),
        ))
    return bindings


def parse_io_link_port_item(item, io_link_modules):
    if ":" not in item:
        raise ValueError(
            f"Invalid IO-Link port declaration {item!r}; "
            "expected <port>:<iodd_key>"
        )
    selector_text, device_key = item.split(":", 1)
    module, port_text = parse_io_link_selector(selector_text, item, io_link_modules)
    port = parse_non_negative_int(port_text, item)
    if module < 1:
        raise ValueError(
            f"Invalid IO-Link module {module}; CPX AP module numbering starts at 1"
        )
    return (module, port), device_key.strip()


def parse_io_link_selector(selector_text, item, io_link_modules):
    selector_text = str(selector_text).strip().lower()
    if "." not in selector_text:
        if len(io_link_modules) != 1:
            raise ValueError(
                f"Invalid IO-Link port selector {selector_text!r}; "
                "port-only syntax requires exactly one iol module. "
                "Use iol<index>.<port>:<iodd_key> when multiple iol modules exist."
            )
        return io_link_modules[0].slot, selector_text

    module_text, port_text = selector_text.split(".", 1)
    if module_text.startswith("iol"):
        ordinal_text = module_text[3:] or "0"
        ordinal = parse_non_negative_int(ordinal_text, item)
        try:
            return io_link_modules[ordinal].slot, port_text
        except IndexError as exc:
            raise ValueError(
                f"Invalid IO-Link module ordinal {module_text!r}; "
                f"configured iol module count={len(io_link_modules)}"
            ) from exc

    return parse_non_negative_int(module_text, item), port_text


def io_link_module_refs(raw_modules):
    refs = []
    for slot, raw_module in split_indexed_config_list(raw_modules, default_start=1):
        parts = [
            part.strip().lower()
            for part in str(raw_module).split(":")
            if part.strip()
        ]
        if not parts or parts[0] != "iol":
            continue
        if len(parts) < 2:
            raise ValueError(
                f"Invalid CPX AP IO-Link module {raw_module!r}; "
                "expected iol:<ports>"
            )
        refs.append(IoLinkModuleRef(
            ordinal=len(refs),
            slot=slot,
            ports=parse_non_negative_int(parts[1], raw_module),
        ))
    return tuple(refs)


def inferred_io_link_module_sizes(bindings):
    sizes = {}
    required_bytes_by_module = {}
    for binding in bindings:
        input_bytes, output_bytes = binding.device.process_data_size
        required = max(input_bytes, output_bytes)
        current = required_bytes_by_module.get(binding.module, 0)
        required_bytes_by_module[binding.module] = max(current, required)

    for module, required_bytes in required_bytes_by_module.items():
        bytes_per_port = selected_io_link_variant_bytes(required_bytes)
        sizes[module] = (
            bytes_per_port,
            bytes_per_port,
        )
    return sizes


def selected_io_link_variant_bytes(required_bytes):
    for candidate in IO_LINK_VARIANT_BYTES_PER_PORT:
        if int(required_bytes) <= candidate:
            return candidate
    raise ValueError(
        f"IO-Link device process data requires {required_bytes} bytes per port; "
        "supported CPX-AP-I-4IOL-M12 variants are 2, 4, 8, 16, and 32 bytes."
    )


def validate_config(config, layout_key):
    if not config.layout.modules:
        raise ValueError(f"{layout_key} does not contain any AP modules")
    validate_layout_against_esi(config.layout)


def validate_io_link_bindings(config):
    modules_by_slot = {module.slot: module for module in config.layout.modules}
    for binding in config.io_link_devices:
        module = modules_by_slot.get(binding.module)
        if module is None:
            raise ValueError(
                f"IO-Link device binding references unknown module {binding.module}"
            )
        if module.module_type != "iol":
            raise ValueError(
                f"IO-Link device binding references non-IOL module {binding.module}"
            )
        if binding.port >= module.io_link_ports:
            raise ValueError(
                f"IO-Link port {binding.port} is outside module {binding.module} "
                f"port range 0..{module.io_link_ports - 1}"
            )


def split_env_list(value):
    return [
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    ]


def parse_non_negative_int(value, context):
    try:
        parsed = int(str(value).strip(), 0)
    except ValueError as exc:
        raise ValueError(
            f"Invalid numeric value {value!r} in {context!r}"
        ) from exc
    if parsed < 0:
        raise ValueError(f"Negative numeric value {value!r} in {context!r}")
    return parsed


def normalized_none_key(value):
    return str(value or "").strip().lower() in IO_LINK_NONE_DEVICE_KEYS


def bytes_for_bits(bit_count):
    return (max(0, int(bit_count)) + 7) // 8
