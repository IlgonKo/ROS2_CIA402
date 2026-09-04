import unittest
from types import SimpleNamespace

from ethercat.mock_master import MockMaster
from ethercat.pysoem_master import PySOEMMaster
from ethercat.sdo_access import SdoAccess
from motion_server.failure import (
    CommunicationException,
    CommunicationTimeoutException,
    DeviceAccessException,
    DeviceRejectedException,
    SdoObjectNotFoundException,
)


class FailingSlave:
    def __init__(self, exception=None, payload=b"\x2A\x00"):
        self.exception = exception
        self.payload = payload
        self.written = None

    def read_sdo(self, index, subindex, size):
        if self.exception is not None:
            raise self.exception
        return self.payload[:size]

    def write_sdo(self, index, subindex, payload):
        if self.exception is not None:
            raise self.exception
        self.written = bytes(payload)



class EmptyPdo:
    pass


class EmptyPdoCodec:
    @staticmethod
    def encode_rxpdo(rxpdo):
        return b""

    @staticmethod
    def decode_txpdo(payload, txpdo):
        return None


class EmptyProfile:
    pdo_codec = EmptyPdoCodec

    @staticmethod
    def create_rxpdo():
        return EmptyPdo()

    @staticmethod
    def create_txpdo():
        return EmptyPdo()

    @staticmethod
    def prepare_process_image(master, slave_index):
        return None


class FakePysoemSlave:
    def __init__(self, exception=None, payload=b"\x2A\x00"):
        self.exception = exception
        self.payload = payload
        self.written = None

    def sdo_read(self, index, subindex, *, size):
        if self.exception is not None:
            raise self.exception
        return self.payload[:size]

    def sdo_write(self, index, subindex, payload):
        if self.exception is not None:
            raise self.exception
        self.written = bytes(payload)


class FlakyPysoemSlave:
    def __init__(self, exception, *, failures_before_success=1, payload=b"\x2A\x00"):
        self.exception = exception
        self.failures_before_success = int(failures_before_success)
        self.payload = payload
        self.read_attempts = 0
        self.write_attempts = 0
        self.written = None

    def sdo_read(self, index, subindex, *, size):
        self.read_attempts += 1
        if self.read_attempts <= self.failures_before_success:
            raise self.exception
        return self.payload[:size]

    def sdo_write(self, index, subindex, payload):
        self.write_attempts += 1
        if self.write_attempts <= self.failures_before_success:
            raise self.exception
        self.written = bytes(payload)


class FailingTransport:
    def __init__(self, exception=None, payload=b"\x2A\x00"):
        self.exception = exception
        self.payload = payload

    def read_sdo(self, slave_index, index, subindex, size):
        if self.exception is not None:
            raise self.exception
        return self.payload[:size]

    def write_sdo(self, slave_index, index, subindex, payload):
        if self.exception is not None:
            raise self.exception


class FakeSdoError(Exception):
    def __init__(self, abort_code):
        self.abort_code = abort_code
        super().__init__(f"SDO abort 0x{abort_code:08X}")


class FakeMailboxError(Exception):
    pass


def pysoem_master(slave):
    master = object.__new__(PySOEMMaster)
    master._master = SimpleNamespace(slaves=[slave])
    master._pysoem = SimpleNamespace(
        SdoError=FakeSdoError,
        MailboxError=FakeMailboxError,
        PacketError=FakeMailboxError,
    )
    master.sdo_communication_retry_count = 3
    master.sdo_communication_retry_delay_s = 0
    return master


def disconnected_pysoem_master():
    master = object.__new__(PySOEMMaster)
    master._master = None
    return master


def mock_master(slave):
    return MockMaster([slave], device_profiles=[EmptyProfile()])


def invoke_raw(master, operation):
    if operation == "read":
        return master.read_sdo(0, 0x1234, 2, 2)
    return master.write_sdo(0, 0x1234, 2, b"\x2A\x00")


class SdoExceptionParityTest(unittest.TestCase):
    def test_mock_and_pysoem_normal_read_write_match(self):
        mock_slave = FailingSlave()
        real_slave = FakePysoemSlave()
        mock = mock_master(mock_slave)
        real = pysoem_master(real_slave)

        for master in (mock, real):
            with self.subTest(backend=type(master).__name__, operation="read"):
                self.assertEqual(invoke_raw(master, "read"), b"\x2A\x00")
            with self.subTest(backend=type(master).__name__, operation="write"):
                invoke_raw(master, "write")

        self.assertEqual(mock_slave.written, b"\x2A\x00")
        self.assertEqual(real_slave.written, b"\x2A\x00")

    def test_object_not_found_parity_for_read_and_write(self):
        for operation in ("read", "write"):
            cases = (
                mock_master(
                    FailingSlave(SdoObjectNotFoundException(0x1234, 2)),
                ),
                pysoem_master(FakePysoemSlave(FakeSdoError(0x06020000))),
            )
            for master in cases:
                with self.subTest(operation=operation, backend=type(master).__name__):
                    with self.assertRaises(SdoObjectNotFoundException) as caught:
                        invoke_raw(master, operation)
                    self.assertEqual(caught.exception.index, 0x1234)
                    self.assertEqual(caught.exception.subindex, 2)
                    if isinstance(master, PySOEMMaster):
                        self.assertIsNotNone(caught.exception.__cause__)

    def test_device_rejected_parity_for_read_and_write(self):
        for operation in ("read", "write"):
            cases = (
                mock_master(FailingSlave(DeviceRejectedException("sdo"))),
                pysoem_master(FakePysoemSlave(FakeSdoError(0x06010002))),
            )
            for master in cases:
                with self.subTest(operation=operation, backend=type(master).__name__):
                    with self.assertRaises(DeviceRejectedException) as caught:
                        invoke_raw(master, operation)
                    if isinstance(master, PySOEMMaster):
                        self.assertEqual(
                            caught.exception.operation,
                            f"sdo_{operation}",
                        )

    def test_timeout_parity_for_read_and_write(self):
        for operation in ("read", "write"):
            cases = (
                mock_master(FailingSlave(TimeoutError("timeout"))),
                pysoem_master(FakePysoemSlave(FakeSdoError(0x05040000))),
            )
            for master in cases:
                with self.subTest(operation=operation, backend=type(master).__name__):
                    with self.assertRaises(CommunicationTimeoutException) as caught:
                        invoke_raw(master, operation)
                    self.assertEqual(caught.exception.operation, f"sdo_{operation}")

    def test_communication_failure_parity_for_read_and_write(self):
        for operation in ("read", "write"):
            cases = (
                mock_master(FailingSlave(OSError("disconnected"))),
                pysoem_master(FakePysoemSlave(FakeMailboxError("mailbox"))),
            )
            for master in cases:
                with self.subTest(operation=operation, backend=type(master).__name__):
                    with self.assertRaises(CommunicationException) as caught:
                        invoke_raw(master, operation)
                    self.assertNotIsInstance(
                        caught.exception,
                        CommunicationTimeoutException,
                    )

    def test_pysoem_retries_transient_sdo_communication_failures(self):
        for operation in ("read", "write"):
            slave = FlakyPysoemSlave(
                FakeMailboxError("transient mailbox"),
                failures_before_success=2,
            )
            master = pysoem_master(slave)

            self.assertEqual(invoke_raw(master, operation), None if operation == "write" else b"\x2A\x00")
            self.assertEqual(slave.read_attempts if operation == "read" else slave.write_attempts, 3)

    def test_pysoem_still_fails_after_sdo_retry_budget(self):
        slave = FlakyPysoemSlave(
            FakeMailboxError("persistent mailbox"),
            failures_before_success=3,
        )
        master = pysoem_master(slave)

        with self.assertRaises(CommunicationException):
            invoke_raw(master, "read")
        self.assertEqual(slave.read_attempts, 3)

    def test_disconnected_pysoem_transport_is_expected_communication_failure(self):
        master = disconnected_pysoem_master()

        for operation in ("read", "write"):
            with self.subTest(operation=operation):
                with self.assertRaises(CommunicationException) as caught:
                    invoke_raw(master, operation)
                self.assertEqual(
                    caught.exception.operation,
                    "bus_transport_disconnected",
                )

    def test_unexpected_exception_is_not_hidden(self):
        for operation in ("read", "write"):
            for master in (
                mock_master(FailingSlave(ValueError("programming defect"))),
                pysoem_master(FakePysoemSlave(ValueError("programming defect"))),
            ):
                with self.subTest(operation=operation, backend=type(master).__name__):
                    with self.assertRaisesRegex(ValueError, "programming defect"):
                        invoke_raw(master, operation)

    def test_mock_master_does_not_interpret_device_key_error(self):
        master = mock_master(FailingSlave(KeyError("programming defect")))

        with self.assertRaises(KeyError):
            master.read_sdo(0, 0x1234, 2, 2)

    def test_typed_sdo_access_preserves_normalized_exception(self):
        expected = CommunicationTimeoutException("sdo_read")
        access = SdoAccess(FailingTransport(expected))

        with self.assertRaises(CommunicationTimeoutException) as caught:
            access.read_uint16(0, 0x1234, 2)

        self.assertIs(caught.exception, expected)

    def test_typed_sdo_access_does_not_hide_unexpected_exception(self):
        access = SdoAccess(FailingTransport(ValueError("programming defect")))

        with self.assertRaisesRegex(ValueError, "programming defect"):
            access.read_uint16(0, 0x1234, 2)

    def test_short_typed_payload_is_device_access_failure(self):
        access = SdoAccess(FailingTransport(payload=b"\x2A"))

        with self.assertRaises(DeviceAccessException) as caught:
            access.read_uint16(0, 0x1234, 2)

        self.assertEqual(caught.exception.operation, "sdo_read_short_payload")


if __name__ == "__main__":
    unittest.main()
