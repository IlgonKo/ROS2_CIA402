import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

from motion_server.api.router import request_response
from motion_server.failure import (
    CommunicationTimeoutException,
    FailureCode,
    InvalidArgumentException,
    ResourceNotFoundException,
    UnsupportedOperationException,
    map_exception,
)
from motion_server.handlers.parameter_access.ethercat import (
    _read_axis_parameter,
    _read_io_parameter,
    _write_axis_parameter,
    _write_io_parameter,
    read_parameter,
    write_io_parameter,
)


class RecordingConnection:
    def __init__(self):
        self.messages = []

    def sendall(self, payload):
        self.messages.append(json.loads(payload.decode("utf-8")))


class FakeSdo:
    def __init__(self, exception=None):
        self.exception = exception
        self.value = 42

    def read_uint16(self, selector, index, subindex):
        if self.exception is not None:
            raise self.exception
        return self.value

    def write_uint16(self, selector, index, subindex, value):
        if self.exception is not None:
            raise self.exception
        self.value = value


class FakeIoGroup:
    def __init__(self, selectors):
        self.selectors = set(selectors)

    def slave_index(self, selector):
        if selector not in self.selectors:
            raise ValueError(f"Unknown I/O device: {selector}")
        return 1


def runtime(axis_sdo=None, io_sdo=None, io_selectors=("io0",)):
    axis_sdo = axis_sdo or FakeSdo()
    io_sdo = io_sdo or FakeSdo()
    axis_sdo.io = io_sdo
    return SimpleNamespace(
        slaves=[object()],
        sdo=axis_sdo,
        device_manager=SimpleNamespace(io=FakeIoGroup(io_selectors)),
    )


def failure_code(operation):
    try:
        operation()
    except Exception as exception:
        return map_exception(exception).code
    raise AssertionError("operation did not fail")


class EthercatParameterHandlerTest(unittest.TestCase):
    def test_axis_read_operation_returns_parameter_data(self):
        data = _read_axis_parameter(
            {
                "type": "system/axis/param_read",
                "axis": 0,
                "index": "0x1234",
                "subindex": 2,
                "data_type": "uint16",
            },
            runtime(),
        )

        self.assertEqual(data["axis"], 0)
        self.assertEqual(data["index"], 0x1234)
        self.assertEqual(data["value"], 42)
        self.assertIsNone(data["length"])

    def test_axis_write_operation_returns_written_value(self):
        active_runtime = runtime()

        data = _write_axis_parameter(
            {
                "type": "system/axis/param_write",
                "axis": 0,
                "index": 0x1234,
                "data_type": "uint16",
                "value": "0x002B",
            },
            active_runtime,
        )

        self.assertEqual(data["value"], 43)
        self.assertEqual(active_runtime.sdo.value, 43)

    def test_io_read_and_write_operations_use_validated_selector(self):
        active_runtime = runtime()
        read_message = {
            "type": "system/io/param_read",
            "io": "io0",
            "index": 0x1234,
            "data_type": "uint16",
        }
        write_message = {
            **read_message,
            "type": "system/io/param_write",
            "value": 44,
        }

        self.assertEqual(_read_io_parameter(read_message, active_runtime)["value"], 42)
        self.assertEqual(_write_io_parameter(write_message, active_runtime)["value"], 44)

    def test_missing_index_is_invalid_argument(self):
        code = failure_code(lambda: _read_axis_parameter(
            {"type": "system/axis/param_read", "axis": 0},
            runtime(),
        ))

        self.assertEqual(code, FailureCode.INVALID_ARGUMENT)

    def test_invalid_axis_is_resource_not_found(self):
        with self.assertRaises(ResourceNotFoundException):
            _read_axis_parameter(
                {
                    "type": "system/axis/param_read",
                    "axis": 9,
                    "index": 0x1234,
                },
                runtime(),
            )

    def test_unknown_io_is_resource_not_found(self):
        with self.assertRaises(ResourceNotFoundException):
            _read_io_parameter(
                {
                    "type": "system/io/param_read",
                    "io": "missing",
                    "index": 0x1234,
                },
                runtime(),
            )

    def test_direct_iolink_object_access_is_unsupported(self):
        with self.assertRaises(UnsupportedOperationException):
            _read_io_parameter(
                {
                    "type": "system/io/param_read",
                    "io": "io0",
                    "index": 0x2001,
                },
                runtime(),
            )

    def test_missing_write_value_is_invalid_argument(self):
        with self.assertRaises(InvalidArgumentException):
            _write_axis_parameter(
                {
                    "type": "system/axis/param_write",
                    "axis": 0,
                    "index": 0x1234,
                },
                runtime(),
            )

    def test_backend_exception_reaches_request_boundary(self):
        active_runtime = runtime(
            axis_sdo=FakeSdo(CommunicationTimeoutException("sdo_read")),
        )
        logger = Mock()

        response = request_response(
            {"type": "system/axis/param_read"},
            lambda: _read_axis_parameter(
                {
                    "type": "system/axis/param_read",
                    "axis": 0,
                    "index": 0x1234,
                    "data_type": "uint16",
                },
                active_runtime,
            ),
            logger=logger,
        )

        self.assertEqual(response["failure"]["code"], "TIMEOUT")

    def test_unexpected_backend_error_is_not_reclassified_by_handler(self):
        active_runtime = runtime(axis_sdo=FakeSdo(ValueError("defect")))

        with self.assertRaisesRegex(ValueError, "defect"):
            _read_axis_parameter(
                {
                    "type": "system/axis/param_read",
                    "axis": 0,
                    "index": 0x1234,
                    "data_type": "uint16",
                },
                active_runtime,
            )

    def test_live_handler_sends_success_envelope(self):
        connection = RecordingConnection()
        message = {
            "type": "system/axis/param_read",
            "axis": 0,
            "index": 0x1234,
            "data_type": "uint16",
        }

        read_parameter(message, runtime(), {"conn": connection})

        response = connection.messages[0]
        self.assertEqual(response["result"], "success")
        self.assertIn("data", response)
        self.assertNotIn("ok", response)
        self.assertNotIn("failure", response)

    def test_live_failure_sends_safe_fail_envelope(self):
        connection = RecordingConnection()
        message = {
            "type": "system/io/param_write",
            "io": "missing",
            "index": 0x1234,
            "value": 1,
        }

        with patch("motion_server.api.router._LOGGER", Mock()):
            write_io_parameter(message, runtime(), {"conn": connection})

        response = connection.messages[0]
        self.assertEqual(response["result"], "fail")
        self.assertEqual(response["failure"]["code"], "RESOURCE_NOT_FOUND")
        self.assertNotIn("ok", response)
        self.assertNotIn("error", response)


if __name__ == "__main__":
    unittest.main()
