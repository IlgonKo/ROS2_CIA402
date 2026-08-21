import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from motion_server.failure import (
    CommunicationTimeoutException,
    DeviceRejectedException,
    PermissionDeniedException,
    OperationTimeoutException,
    ResourceNotFoundException,
)
from motion_server.handlers.parameter_access.iol import (
    ISDU_STATUS_BUSY,
    _read_iol_parameter,
    _write_iol_parameter,
    read_iol_parameter,
)


class FakeSdo:
    def __init__(self, status=0, exception=None):
        self.status = status
        self.exception = exception

    def _check(self):
        if self.exception is not None:
            raise self.exception

    def write_uint8(self, *args): self._check()
    def write_uint16(self, *args): self._check()
    def read_uint8(self, *args): self._check(); return 2
    def read_uint16(self, slave, index, subindex):
        self._check()
        return self.status


class FakeMaster:
    def __init__(self, status=0, exception=None):
        self.sdo = FakeSdo(status, exception)
        self.raw_writes = []

    def read_sdo(self, slave, index, subindex, size):
        if self.sdo.exception: raise self.sdo.exception
        return b"\x2A\x00" + bytes(max(0, size - 2))

    def write_sdo(self, slave, index, subindex, payload):
        if self.sdo.exception: raise self.sdo.exception
        self.raw_writes.append(bytes(payload))


class FakeIoGroup:
    def __init__(self, access="rw", variable_index=0x10, subindices=()):
        variable = SimpleNamespace(
            index=variable_index,
            access=access,
            name="Parameter",
            subindices=[{"subindex": value} for value in subindices],
        )
        binding = SimpleNamespace(
            module=1,
            port=1,
            device=SimpleNamespace(device_name="Fake", variables=[variable]),
        )
        config = SimpleNamespace(io_link_devices=[binding])
        slave = SimpleNamespace(device_profile=SimpleNamespace(config=config))
        self.device = {"id": "io0", "slave_index": 1, "slave": slave}

    def selected_device(self, io_id=None, slave_index=None):
        if io_id == "io0" or slave_index == 1: return self.device
        raise ValueError("unknown io")

    def slave_index(self, selector):
        if selector != "io0": raise ValueError("unknown io")
        return 1


class Connection:
    def __init__(self): self.messages = []
    def sendall(self, payload): self.messages.append(json.loads(payload.decode()))


def runtime(status=0, exception=None, **io_options):
    return SimpleNamespace(
        ethercat_master=FakeMaster(status, exception),
        device_manager=SimpleNamespace(io=FakeIoGroup(**io_options)),
    )


def message(**updates):
    value = {
        "type": "system/io/iol/param_read", "io": "io0",
        "module": 1, "port": 1, "index": 0x10,
        "data_type": "uint16",
    }
    value.update(updates)
    return value


class IolParameterHandlerTest(unittest.TestCase):
    def test_isdu_read_returns_structured_data(self):
        data = _read_iol_parameter(message(), runtime())
        self.assertEqual(data["value"], 42)
        self.assertEqual(data["object_index"], "0x2011")

    def test_isdu_write_returns_payload_metadata(self):
        active = runtime()
        data = _write_iol_parameter(
            message(type="system/io/iol/param_write", value=43), active,
        )
        self.assertEqual(data["data"], "2b00")
        self.assertEqual(len(active.ethercat_master.raw_writes[0]), 238)

    def test_missing_port_binding_is_resource_not_found(self):
        with self.assertRaises(ResourceNotFoundException):
            _read_iol_parameter(message(port=2), runtime())

    def test_unknown_iodd_index_is_resource_not_found(self):
        with self.assertRaises(ResourceNotFoundException):
            _read_iol_parameter(message(index=0x11), runtime())

    def test_iodd_access_denial_is_permission_denied(self):
        with self.assertRaises(PermissionDeniedException):
            _write_iol_parameter(
                message(type="system/io/iol/param_write", value=1),
                runtime(access="r"),
            )

    def test_unknown_subindex_is_resource_not_found(self):
        with self.assertRaises(ResourceNotFoundException):
            _read_iol_parameter(message(subindex=2), runtime(subindices=(1,)))

    def test_busy_status_is_operation_timeout(self):
        with patch(
            "motion_server.handlers.parameter_access.iol.ISDU_STATUS_POLL_TIMEOUT", 0,
        ):
            with self.assertRaises(OperationTimeoutException):
                _read_iol_parameter(message(), runtime(status=ISDU_STATUS_BUSY))

    def test_nonzero_status_is_device_rejected(self):
        with self.assertRaises(DeviceRejectedException) as caught:
            _read_iol_parameter(message(), runtime(status=0x1234))
        self.assertEqual(caught.exception.device_code, 0x1234)

    def test_backend_exception_is_not_wrapped(self):
        expected = CommunicationTimeoutException("sdo_write")
        with self.assertRaises(CommunicationTimeoutException) as caught:
            _read_iol_parameter(message(), runtime(exception=expected))
        self.assertIs(caught.exception, expected)

    def test_live_handler_keeps_legacy_shape(self):
        connection = Connection()
        read_iol_parameter(message(), runtime(), {"conn": connection})
        self.assertTrue(connection.messages[0]["ok"])
        self.assertNotIn("result", connection.messages[0])


if __name__ == "__main__":
    unittest.main()
