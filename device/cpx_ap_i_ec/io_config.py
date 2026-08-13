import os
from dataclasses import dataclass

from device.cpx_ap_i_ec.module_layout import (
    CPXApLayout,
    parse_cpx_ap_modules,
)


@dataclass(frozen=True)
class CPXIoConfig:
    io_id: str
    layout: CPXApLayout

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

    config = CPXIoConfig(
        io_id=io_id,
        layout=parse_cpx_ap_modules(raw_modules),
    )
    validate_config(config, layout_key)
    return config


def normalized_io_id(io_id):
    value = str(io_id or "").strip()
    if not value:
        raise ValueError("CPX-AP-I-EC profile requires an I/O logical id")
    return value


def env_value(values, key, default):
    return values.get(str(key).upper(), default)


def validate_config(config, layout_key):
    if not config.layout.modules:
        raise ValueError(f"{layout_key} does not contain any AP modules")


def bytes_for_bits(bit_count):
    return (max(0, int(bit_count)) + 7) // 8
