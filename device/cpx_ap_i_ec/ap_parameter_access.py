import time

from motion_server.failure import (
    DeviceRejectedException,
    OperationTimeoutException,
)


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
        "ap_access_module": ap_access_module_number(module),
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
    status = int(status)
    if status == AP_STATUS_BUSY:
        raise OperationTimeoutException(
            "ap_parameter_write",
            timeout_seconds=AP_STATUS_POLL_TIMEOUT,
        )
    if status != 0:
        raise DeviceRejectedException(
            "ap_parameter_write",
            device_code=status,
        )
    return status


def write_ap_header(master, slave_index, request, length):
    master.sdo.write_uint16(
        slave_index,
        AP_PARAMETER_ACCESS_INDEX,
        2,
        request["ap_access_module"],
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


def ap_access_module_number(module):
    return int(module) + 1
