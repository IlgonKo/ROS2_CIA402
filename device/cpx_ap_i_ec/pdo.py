class CPXRxPDO:
    """CPX output image, master to slave."""

    def __init__(self, config):
        self.config = config
        self.digital_outputs = [False for _ in range(config.digital_outputs)]
        self.analog_outputs = [0 for _ in range(config.analog_outputs)]
        self.payload = bytearray(config.output_bytes)

    def resize(self, byte_count):
        byte_count = max(0, int(byte_count))
        self.payload = bytearray(byte_count)

    def mapping_size(self):
        return len(self.payload)

    def has_field(self, field):
        return False

    def get_digital_output(self, index):
        return bool(self.digital_outputs[int(index)])

    def set_digital_output(self, index, value):
        self.digital_outputs[int(index)] = bool(value)

    def set_analog_output(self, index, value):
        self.analog_outputs[int(index)] = int(value)


class CPXTxPDO:
    """CPX input image, slave to master."""

    def __init__(self, config):
        self.config = config
        self.digital_inputs = [False for _ in range(config.digital_inputs)]
        self.analog_inputs = [0 for _ in range(config.analog_inputs)]
        self.payload = bytes(config.input_bytes)

    def resize(self, byte_count):
        byte_count = max(0, int(byte_count))
        self.payload = bytes(byte_count)

    def mapping_size(self):
        return len(self.payload)

    def has_field(self, field):
        return False

    def get_digital_input(self, index):
        return bool(self.digital_inputs[int(index)])

    def get_analog_input(self, index):
        return int(self.analog_inputs[int(index)])
