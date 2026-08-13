class CPXRxPDO:
    """CPX output image, master to slave."""

    def __init__(self, config):
        self.config = config
        self.module_outputs = {
            module.slot: create_module_output(module)
            for module in config.layout.modules
            if module.output_bytes
        }
        self.payload = bytearray(config.output_bytes)

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
        self.module_outputs[int(slot)]["digital"][int(index)] = bool(value)

    def get_module_analog_output(self, slot, index):
        return int(self.module_outputs[int(slot)]["analog"][int(index)])

    def set_module_analog_output(self, slot, index, value):
        self.module_outputs[int(slot)]["analog"][int(index)] = int(value)

    def get_io_link_output(self, slot):
        return bytes(self.module_outputs[int(slot)]["io_link"])

    def set_io_link_output(self, slot, payload):
        slot = int(slot)
        target = self.module_outputs[slot]["io_link"]
        source = bytes(payload)
        target[:] = b"\x00" * len(target)
        target[:min(len(target), len(source))] = source[:len(target)]


class CPXTxPDO:
    """CPX input image, slave to master."""

    def __init__(self, config):
        self.config = config
        self.module_inputs = {
            module.slot: create_module_input(module)
            for module in config.layout.modules
            if module.input_bytes
        }
        self.payload = bytes(config.input_bytes)

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
