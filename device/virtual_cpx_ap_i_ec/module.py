from device.cpx_ap_i_ec.pdo_codec import (
    read_analog_values,
    read_bytes,
    read_digital_bits,
    write_analog_values,
    write_bytes,
    write_digital_bits,
)
from device.cpx_ap_i_ec.pdo import validate_analog_value


class VirtualApModule:
    """Metadata-driven runtime state for one configured CPX AP module."""

    def __init__(self, module):
        self.module = module
        self.digital_inputs = [False] * module.digital_inputs
        self.digital_outputs = [False] * module.digital_outputs
        self.analog_inputs = [0] * module.analog_inputs
        self.analog_outputs = [0] * module.analog_outputs
        self.io_link_input = bytearray(
            module.input_bytes if module.module_type == "iol" else 0
        )
        self.io_link_output = bytearray(
            module.output_bytes if module.module_type == "iol" else 0
        )

    @property
    def slot(self):
        return int(self.module.slot)

    def consume_output_image(self, payload):
        if self.module.output_offset is None:
            return
        if self.module.digital_outputs:
            self.digital_outputs = read_digital_bits(
                payload,
                self.module.digital_outputs,
                self.module.output_offset,
            )
        if self.module.analog_outputs:
            self.analog_outputs = read_analog_values(
                payload,
                self.module.analog_outputs,
                self.module.output_offset,
                self.module.analog_bytes,
                self.module.analog_signed,
            )
        if self.module.module_type == "iol":
            self.io_link_output[:] = read_bytes(
                payload,
                self.module.output_offset,
                self.module.output_bytes,
            )

    def publish_input_image(self, payload):
        if self.module.input_offset is None:
            return
        if self.module.digital_inputs:
            write_digital_bits(
                payload,
                self.digital_inputs,
                self.module.input_offset,
                self.module.digital_inputs,
            )
        if self.module.analog_inputs:
            write_analog_values(
                payload,
                self.analog_inputs,
                self.module.input_offset,
                self.module.analog_inputs,
                self.module.analog_bytes,
                self.module.analog_signed,
            )
        if self.module.module_type == "iol":
            write_bytes(
                payload,
                self.io_link_input,
                self.module.input_offset,
                self.module.input_bytes,
            )

    def set_digital_input(self, channel, value):
        if not isinstance(value, bool):
            raise TypeError("Digital input value must be bool.")
        channel = input_channel(self.digital_inputs, channel, "digital")
        self.digital_inputs[channel] = value

    def set_analog_input(self, channel, value):
        channel = input_channel(self.analog_inputs, channel, "analog")
        self.analog_inputs[channel] = validate_analog_value(
            self.module,
            value,
        )

    def set_io_link_input(self, payload):
        payload = bytes(payload)
        if len(payload) != len(self.io_link_input):
            raise ValueError(
                f"IO-Link input for module {self.slot} requires "
                f"{len(self.io_link_input)} bytes, got {len(payload)}."
            )
        self.io_link_input[:] = payload

    def reset_inputs(self):
        self.digital_inputs[:] = [False] * len(self.digital_inputs)
        self.analog_inputs[:] = [0] * len(self.analog_inputs)
        self.io_link_input[:] = bytes(len(self.io_link_input))

    def input_snapshot(self):
        values = {}
        if self.digital_inputs:
            values["digital"] = list(self.digital_inputs)
        if self.analog_inputs:
            values["analog"] = list(self.analog_inputs)
        if self.module.module_type == "iol":
            values["io_link"] = bytes(self.io_link_input).hex()
        return {
            "slot": self.slot,
            "type": self.module.module_type,
            "inputs": values,
        }


def input_channel(values, channel, kind):
    if isinstance(channel, bool) or not isinstance(channel, int):
        raise TypeError(f"{kind.capitalize()} input channel must be int.")
    if channel < 0 or channel >= len(values):
        raise ValueError(
            f"{kind.capitalize()} input channel {channel} is outside "
            f"0..{len(values) - 1}."
        )
    return channel
