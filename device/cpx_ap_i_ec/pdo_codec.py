class CPXPdoCodec:
    @staticmethod
    def encode_rxpdo(rxpdo):
        payload = bytearray(rxpdo.mapping_size())
        for module in rxpdo.config.layout.modules:
            encode_output_module(payload, rxpdo, module)
        rxpdo.payload = payload
        return bytes(payload)

    @staticmethod
    def decode_txpdo(payload, txpdo):
        txpdo.payload = bytes(payload)
        for module in txpdo.config.layout.modules:
            decode_input_module(txpdo.payload, txpdo, module)


def encode_output_module(payload, rxpdo, module):
    if module.output_offset is None:
        return

    if module.digital_outputs:
        write_digital_bits(
            payload,
            rxpdo.module_outputs[module.slot]["digital"],
            module.output_offset,
            module.digital_outputs,
        )
    if module.analog_outputs:
        write_analog_values(
            payload,
            rxpdo.module_outputs[module.slot]["analog"],
            module.output_offset,
            module.analog_outputs,
            module.analog_bytes,
            module.analog_signed,
        )
    if module.module_type == "iol":
        write_bytes(
            payload,
            rxpdo.module_outputs.get(module.slot, {}).get("io_link", b""),
            module.output_offset,
            module.output_bytes,
        )


def decode_input_module(payload, txpdo, module):
    if module.input_offset is None:
        return

    if module.digital_inputs:
        values = read_digital_bits(
            payload,
            module.digital_inputs,
            module.input_offset,
        )
        txpdo.module_inputs[module.slot]["digital"] = values
    if module.analog_inputs:
        values = read_analog_values(
            payload,
            module.analog_inputs,
            module.input_offset,
            module.analog_bytes,
            module.analog_signed,
        )
        txpdo.module_inputs[module.slot]["analog"] = values
    if module.module_type == "iol":
        txpdo.module_inputs[module.slot]["io_link"] = read_bytes(
            payload,
            module.input_offset,
            module.input_bytes,
        )


def write_digital_bits(payload, values, byte_offset, count=None):
    if count is None:
        count = len(values)
    for index in range(int(count)):
        value = index < len(values) and values[index]
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


def write_analog_values(
    payload,
    values,
    byte_offset,
    count,
    byte_width,
    signed,
):
    for index in range(int(count)):
        value = values[index] if index < len(values) else 0
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


def read_bytes(payload, byte_offset, byte_count):
    byte_offset = int(byte_offset)
    byte_count = int(byte_count)
    end = byte_offset + byte_count
    if byte_offset >= len(payload):
        return bytes(byte_count)
    data = payload[byte_offset:min(end, len(payload))]
    if len(data) < byte_count:
        data += bytes(byte_count - len(data))
    return bytes(data)


def write_bytes(payload, values, byte_offset, byte_count):
    byte_offset = int(byte_offset)
    byte_count = int(byte_count)
    source = bytes(values)[:byte_count]
    if len(source) < byte_count:
        source += bytes(byte_count - len(source))
    end = byte_offset + byte_count
    if byte_offset >= len(payload):
        return
    write_end = min(end, len(payload))
    payload[byte_offset:write_end] = source[:write_end - byte_offset]
