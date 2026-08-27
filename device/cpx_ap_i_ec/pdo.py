class CPXRxPDO:
    """CPX output image, master to slave."""

    def __init__(self, config, mapping_bytes=None):
        self.config = config
        self.module_outputs = {
            module.slot: create_module_output(module)
            for module in config.layout.modules
            if module.output_bytes
        }
        self.payload = bytearray(
            config.output_bytes if mapping_bytes is None else int(mapping_bytes)
        )

    def resize(self, byte_count):
        byte_count = max(0, int(byte_count))
        self.payload = bytearray(byte_count)

    def mapping_size(self):
        return len(self.payload)

    def has_field(self, field):
        return False

    def get_module_digital_output(self, slot, index):
        return bool(self.module_outputs[int(slot)]["digital"][int(index)])

    def set_module_digital_output(self, slot, index, value):
        if not isinstance(value, bool):
            raise TypeError("Digital output value must be bool.")
        values = self.module_outputs[int(slot)]["digital"]
        index = output_channel(values, index, "digital")
        values[index] = value

    def get_module_analog_output(self, slot, index):
        return int(self.module_outputs[int(slot)]["analog"][int(index)])

    def set_module_analog_output(self, slot, index, value):
        module = module_by_slot(self.config, slot)
        index = output_channel(
            self.module_outputs[int(slot)]["analog"],
            index,
            "analog",
        )
        value = validate_analog_value(module, value)
        self.module_outputs[int(slot)]["analog"][index] = value

    def get_io_link_output(self, slot):
        return bytes(self.module_outputs[int(slot)]["io_link"])

    def set_io_link_output(self, slot, payload):
        slot = int(slot)
        target = self.module_outputs[slot]["io_link"]
        source = bytes(payload)
        if len(source) != len(target):
            raise ValueError(
                f"IO-Link output for module {slot} requires "
                f"{len(target)} bytes, got {len(source)}."
            )
        target[:] = source


class CPXTxPDO:
    """CPX input image, slave to master."""

    def __init__(self, config, mapping_bytes=None):
        self.config = config
        self.module_inputs = {
            module.slot: create_module_input(module)
            for module in config.layout.modules
            if module.input_bytes
        }
        self.payload = bytes(
            config.input_bytes if mapping_bytes is None else int(mapping_bytes)
        )

    def resize(self, byte_count):
        byte_count = max(0, int(byte_count))
        self.payload = bytes(byte_count)

    def mapping_size(self):
        return len(self.payload)

    def has_field(self, field):
        return False

    def get_module_digital_input(self, slot, index):
        return bool(self.module_inputs[int(slot)]["digital"][int(index)])

    def get_module_analog_input(self, slot, index):
        return int(self.module_inputs[int(slot)]["analog"][int(index)])

    def get_io_link_input(self, slot):
        return bytes(self.module_inputs[int(slot)]["io_link"])


def create_module_output(module):
    return {
        "digital": [False for _ in range(module.digital_outputs)],
        "analog": [0 for _ in range(module.analog_outputs)],
        "io_link": bytearray(
            module.output_bytes if module.module_type == "iol" else 0
        ),
    }


def create_module_input(module):
    return {
        "digital": [False for _ in range(module.digital_inputs)],
        "analog": [0 for _ in range(module.analog_inputs)],
        "io_link": bytes(
            module.input_bytes if module.module_type == "iol" else 0
        ),
    }


def flatten_module_values(modules, module_data, count_attribute, data_key):
    values = []
    for module in modules:
        if int(getattr(module, count_attribute)) <= 0:
            continue
        values.extend(module_data[module.slot][data_key])
    return values


def module_by_slot(config, slot):
    slot = int(slot)
    for module in config.layout.modules:
        if int(module.slot) == slot:
            return module
    raise KeyError(f"Unknown CPX AP module slot: {slot}")


def validate_analog_value(module, value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("Analog value must be int.")
    bits = int(module.analog_bits)
    if module.analog_signed:
        minimum = -(1 << (bits - 1))
        maximum = (1 << (bits - 1)) - 1
    else:
        minimum = 0
        maximum = (1 << bits) - 1
    if value < minimum or value > maximum:
        raise ValueError(
            f"Analog value {value} is outside {minimum}..{maximum} "
            f"for module {module.slot}."
        )
    return value


def output_channel(values, channel, kind):
    if isinstance(channel, bool) or not isinstance(channel, int):
        raise TypeError(f"{kind.capitalize()} output channel must be int.")
    if channel < 0 or channel >= len(values):
        raise ValueError(
            f"{kind.capitalize()} output channel {channel} is outside "
            f"0..{len(values) - 1}."
        )
    return channel


def flattened_digital_outputs(rxpdo):
    return flatten_module_values(
        rxpdo.config.layout.modules,
        rxpdo.module_outputs,
        "digital_outputs",
        "digital",
    )


def flattened_analog_outputs(rxpdo):
    return flatten_module_values(
        rxpdo.config.layout.modules,
        rxpdo.module_outputs,
        "analog_outputs",
        "analog",
    )


def flattened_digital_inputs(txpdo):
    return flatten_module_values(
        txpdo.config.layout.modules,
        txpdo.module_inputs,
        "digital_inputs",
        "digital",
    )


def flattened_analog_inputs(txpdo):
    return flatten_module_values(
        txpdo.config.layout.modules,
        txpdo.module_inputs,
        "analog_inputs",
        "analog",
    )
