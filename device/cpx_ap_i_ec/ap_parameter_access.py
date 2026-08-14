import time


AP_PARAMETER_ACCESS_INDEX = 0x27F0
AP_DIRECTION_WRITE = 1
AP_MAX_DATA_BYTES = 512
AP_STATUS_BUSY = 0xFFFF
AP_STATUS_POLL_TIMEOUT = 1.0
AP_STATUS_POLL_PERIOD = 0.02


def write_ap_uint32_parameter(
    master,
    slave_index,
    module,
    parameter_id,
    instance,
    value,
):
    request = {
        "module": int(module),
        "parameter_id": int(parameter_id),
        "instance": int(instance),
    }
    write_ap_header(master, slave_index, request, length=4)
    write_ap_data(master, slave_index, int(value).to_bytes(4, "little"))
    master.sdo.write_uint8(
        slave_index,
        AP_PARAMETER_ACCESS_INDEX,
        1,
        AP_DIRECTION_WRITE,
    )
    status = poll_ap_status(master, slave_index)
    if int(status) != 0:
        raise RuntimeError(
            "AP parameter write failed: "
            f"status=0x{int(status):04X} "
            f"module={request['module']} "
            f"parameter_id=0x{request['parameter_id']:08X} "
            f"instance={request['instance']}"
        )
    return status


def write_ap_header(master, slave_index, request, length):
    master.sdo.write_uint16(
        slave_index,
        AP_PARAMETER_ACCESS_INDEX,
        2,
        request["module"],
    )
    master.sdo.write_uint32(
        slave_index,
        AP_PARAMETER_ACCESS_INDEX,
        3,
        request["parameter_id"],
    )
    master.sdo.write_uint16(
        slave_index,
        AP_PARAMETER_ACCESS_INDEX,
        4,
        request["instance"],
    )
    master.sdo.write_uint16(
        slave_index,
        AP_PARAMETER_ACCESS_INDEX,
        6,
        int(length),
    )


def write_ap_data(master, slave_index, payload):
    data = bytes(payload)
    if len(data) < AP_MAX_DATA_BYTES:
        data += bytes(AP_MAX_DATA_BYTES - len(data))
    master.write_sdo(
        slave_index,
        AP_PARAMETER_ACCESS_INDEX,
        7,
        data,
    )


def poll_ap_status(master, slave_index):
    deadline = time.monotonic() + AP_STATUS_POLL_TIMEOUT
    while True:
        status = master.sdo.read_uint16(
            slave_index,
            AP_PARAMETER_ACCESS_INDEX,
            5,
        )
        if int(status) != AP_STATUS_BUSY:
            return status
        if time.monotonic() >= deadline:
            return status
        time.sleep(AP_STATUS_POLL_PERIOD)
