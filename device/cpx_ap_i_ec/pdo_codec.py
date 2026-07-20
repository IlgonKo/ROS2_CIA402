class CPXPdoCodec:
    @staticmethod
    def encode_rxpdo(rxpdo):
        payload = bytearray(rxpdo.mapping_size())
        write_digital_bits(payload, rxpdo.digital_outputs, 0)
        write_analog_values(
            payload,
            rxpdo.analog_outputs,
            rxpdo.config.output_digital_bytes,
            rxpdo.config.analog_bytes,
            rxpdo.config.analog_signed,
        )
        rxpdo.payload = payload
        return bytes(payload)

    @staticmethod
    def decode_txpdo(payload, txpdo):
        txpdo.payload = bytes(payload)
        txpdo.digital_inputs = read_digital_bits(
            txpdo.payload,
            txpdo.config.digital_inputs,
            0,
        )
        txpdo.analog_inputs = read_analog_values(
            txpdo.payload,
            txpdo.config.analog_inputs,
            txpdo.config.input_digital_bytes,
            txpdo.config.analog_bytes,
            txpdo.config.analog_signed,
        )


def write_digital_bits(payload, values, byte_offset):
    for index, value in enumerate(values):
        if not value:
            continue
        byte_index = byte_offset + index // 8
        bit_index = index % 8
        if byte_index < len(payload):
            payload[byte_index] |= 1 << bit_index


def read_digital_bits(payload, count, byte_offset):
    result = []
    for index in range(int(count)):
        byte_index = byte_offset + index // 8
        bit_index = index % 8
        value = byte_index < len(payload) and bool(payload[byte_index] & (1 << bit_index))
        result.append(value)
    return result


def write_analog_values(payload, values, byte_offset, byte_width, signed):
    for index, value in enumerate(values):
        start = byte_offset + index * byte_width
        end = start + byte_width
        if end > len(payload):
            break
        payload[start:end] = int(value).to_bytes(
            byte_width,
            byteorder="little",
            signed=bool(signed),
        )


def read_analog_values(payload, count, byte_offset, byte_width, signed):
    result = []
    for index in range(int(count)):
        start = byte_offset + index * byte_width
        end = start + byte_width
        if end > len(payload):
            result.append(0)
            continue
        result.append(int.from_bytes(
            payload[start:end],
            byteorder="little",
            signed=bool(signed),
        ))
    return result
