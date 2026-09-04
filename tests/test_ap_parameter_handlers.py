import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from device.cpx_ap_i_ec.ap_parameter_access import write_ap_uint32_parameter
from motion_server.app.runtime_parameters import RuntimeParameterCache
from motion_server.failure import (
    CommunicationTimeoutException,
    DeviceRejectedException,
    InvalidArgumentException,
    OperationTimeoutException,
    ResourceNotFoundException,
)
from motion_server.handlers.parameter_access.ap import (
    AP_STATUS_BUSY,
    _read_ap_parameter,
    _write_ap_parameter,
    read_ap_parameter,
)


class FakeApSdo:
    def __init__(self, status=0, exception=None):
        self.status = status
        self.exception = exception
        self.writes = []

    def _raise(self):
        if self.exception is not None:
            raise self.exception

    def write_uint8(self, *args):
        self._raise()
        self.writes.append(("uint8", args))

    def write_uint16(self, *args):
        self._raise()
        self.writes.append(("uint16", args))

    def write_uint32(self, *args):
        self._raise()
        self.writes.append(("uint32", args))

    def read_uint16(self, slave_index, index, subindex):
        self._raise()
        if subindex == 5:
            return self.status
        if subindex == 6:
            return 4
        raise AssertionError(f"unexpected AP subindex {subindex}")


class FakeApMaster:
    def __init__(self, status=0, exception=None):
        self.sdo = FakeApSdo(status=status, exception=exception)
        self.raw_writes = []

    def read_sdo(self, slave_index, index, subindex, size):
        if self.sdo.exception is not None:
            raise self.sdo.exception
        return (42).to_bytes(4, "little") + bytes(max(0, size - 4))

    def write_sdo(self, slave_index, index, subindex, payload):
        if self.sdo.exception is not None:
            raise self.sdo.exception
        self.raw_writes.append(bytes(payload))


class FakeIoGroup:
    def __init__(self, modules=(1,), io_id="io0"):
        layout = SimpleNamespace(
            modules=[SimpleNamespace(slot=slot) for slot in modules],
        )
        slave = SimpleNamespace(
            rxpdo=SimpleNamespace(config=SimpleNamespace(layout=layout)),
        )
        self.device = {"id": io_id, "slave_index": 1, "slave": slave}

    def slave_index(self, selector):
        if selector != self.device["id"]:
            raise ValueError("unknown io")
        return self.device["slave_index"]

    def selected_device(self, *, slave_index=None, io_id=None):
        if slave_index == self.device["slave_index"] or io_id == self.device["id"]:
            return self.device
        raise ValueError("unknown io")


class RecordingConnection:
    def __init__(self):
        self.messages = []

    def sendall(self, payload):
        self.messages.append(json.loads(payload.decode("utf-8")))


def runtime(status=0, exception=None, modules=(1,), parameter_cache=None):
    master = FakeApMaster(status=status, exception=exception)
    return SimpleNamespace(
        ethercat_master=master,
        device_manager=SimpleNamespace(io=FakeIoGroup(modules=modules)),
        parameter_cache=parameter_cache,
    )


def read_message(**updates):
    message = {
        "type": "system/io/ap/param_read",
        "io": "io0",
        "module": 1,
        "parameter_id": 0x1234,
        "data_type": "uint32",
    }
    message.update(updates)
    return message


class ApParameterHandlerTest(unittest.TestCase):
    def test_ap_read_returns_structured_data(self):
        cache = RuntimeParameterCache()
        data = _read_ap_parameter(read_message(), runtime(parameter_cache=cache))

        self.assertEqual(data["module"], 1)
        self.assertEqual(data["parameter_id"], 0x1234)
        self.assertEqual(data["value"], 42)
        self.assertEqual(data["status"], 0)
        cached = cache.get("io.0.ap_parameter.module1.parameter0x00001234.instance0")
        self.assertEqual(cached.value, 42)
        self.assertEqual(cached.raw_value, "2a000000")

    def test_ap_write_returns_payload_metadata(self):
        cache = RuntimeParameterCache()
        active_runtime = runtime(parameter_cache=cache)
        message = read_message(
            type="system/io/ap/param_write",
            value=43,
        )

        data = _write_ap_parameter(message, active_runtime)

        self.assertEqual(data["length"], 4)
        self.assertEqual(data["data"], "2b000000")
        self.assertEqual(len(active_runtime.ethercat_master.raw_writes[0]), 512)
        cached = cache.get("io.0.ap_parameter.module1.parameter0x00001234.instance0")
        self.assertEqual(cached.value, 43)
        self.assertEqual(cached.source, "device_write")

    def test_unknown_io_is_resource_not_found(self):
        with self.assertRaises(ResourceNotFoundException):
            _read_ap_parameter(read_message(io="missing"), runtime())

    def test_unknown_module_is_resource_not_found(self):
        with self.assertRaises(ResourceNotFoundException):
            _read_ap_parameter(read_message(module=9), runtime())

    def test_interface_module_zero_is_valid(self):
        data = _read_ap_parameter(read_message(module=0), runtime(modules=()))

        self.assertEqual(data["module"], 0)

    def test_invalid_parameter_id_is_invalid_argument(self):
        with self.assertRaises(InvalidArgumentException):
            _read_ap_parameter(read_message(parameter_id="invalid"), runtime())

    def test_invalid_payload_is_invalid_argument(self):
        with self.assertRaises(InvalidArgumentException):
            _write_ap_parameter(
                read_message(type="system/io/ap/param_write", value="invalid"),
                runtime(),
            )

    def test_busy_status_is_operation_timeout(self):
        with patch(
            "motion_server.handlers.parameter_access.ap.AP_STATUS_POLL_TIMEOUT",
            0,
        ):
            with self.assertRaises(OperationTimeoutException):
                _read_ap_parameter(read_message(), runtime(status=AP_STATUS_BUSY))

    def test_nonzero_status_is_device_rejected(self):
        with self.assertRaises(DeviceRejectedException) as caught:
            _read_ap_parameter(read_message(), runtime(status=0x1234))

        self.assertEqual(caught.exception.device_code, 0x1234)

    def test_backend_exception_is_not_wrapped(self):
        expected = CommunicationTimeoutException("sdo_write")

        with self.assertRaises(CommunicationTimeoutException) as caught:
            _read_ap_parameter(read_message(), runtime(exception=expected))

        self.assertIs(caught.exception, expected)

    def test_handler_returns_operation_data(self):
        data = read_ap_parameter(read_message(), runtime(), {})
        self.assertEqual(data["io"], "io0")
        self.assertNotIn("result", data)

    def test_startup_ap_write_uses_common_status_exceptions(self):
        timeout_master = FakeApMaster(status=AP_STATUS_BUSY)
        rejected_master = FakeApMaster(status=0x4321)

        with patch(
            "device.cpx_ap_i_ec.ap_parameter_access.AP_STATUS_POLL_TIMEOUT",
            0,
        ):
            with self.assertRaises(OperationTimeoutException):
                write_ap_uint32_parameter(timeout_master, 1, 1, 2, 0, 3)
        with self.assertRaises(DeviceRejectedException) as caught:
            write_ap_uint32_parameter(rejected_master, 1, 1, 2, 0, 3)
        self.assertEqual(caught.exception.device_code, 0x4321)


if __name__ == "__main__":
    unittest.main()
