from types import SimpleNamespace
import unittest

from device.cmmt.profile import CMMTASDeviceProfile
from device.virtual_servo_drive.servo_model import VirtualCiA402Servo
from ethercat.master_pdo_runtime import MasterPdoRuntime
from ethercat.mock_master import MockMaster
from ethercat.mock_slave import MockSlave
from ethercat.pysoem_master import PySOEMMaster
from motion_server.failure import CommunicationException


class ByteRxPdo:
    def __init__(self):
        self.value = 0


class ByteTxPdo:
    def __init__(self):
        self.value = 0

    @staticmethod
    def mapping_size():
        return 1


class BytePdoCodec:
    @staticmethod
    def encode_rxpdo(rxpdo):
        return bytes((int(rxpdo.value),))

    @staticmethod
    def decode_txpdo(payload, txpdo):
        payload = bytes(payload)
        if len(payload) != 1:
            raise ValueError("expected one TxPDO byte")
        txpdo.value = payload[0]


class ByteProfile:
    pdo_codec = BytePdoCodec

    @staticmethod
    def create_rxpdo():
        return ByteRxPdo()

    @staticmethod
    def create_txpdo():
        return ByteTxPdo()

    @staticmethod
    def prepare_process_image(master, slave_index):
        return None


class RecordingMockEndpoint:
    def __init__(self, input_payload=b"\x00"):
        self.input_payload = bytes(input_payload)
        self.outputs = []

    def exchange_processdata(self, output_payload):
        self.outputs.append(bytes(output_payload))
        return self.input_payload

    def read_sdo(self, index, subindex, size):
        return bytes(size)

    def write_sdo(self, index, subindex, payload):
        return None


class FakePysoemSlave:
    def __init__(self, input_payload=b"\x00"):
        self.output = b""
        self.input = bytes(input_payload)


class FakePysoemTransport:
    def __init__(self, input_payloads):
        self.slaves = [FakePysoemSlave(payload) for payload in input_payloads]
        self.expected_wkc = len(self.slaves) * 3
        self.sent_outputs = []
        self.dc_time = 123
        self.send_exception = None

    def send_processdata(self):
        if self.send_exception is not None:
            raise self.send_exception
        self.sent_outputs.append(tuple(slave.output for slave in self.slaves))

    def receive_processdata(self, timeout_us):
        return self.expected_wkc

    def _get_dc_time(self):
        return self.dc_time


def connected_mock(input_payloads):
    profiles = [ByteProfile() for _ in input_payloads]
    endpoints = [RecordingMockEndpoint(payload) for payload in input_payloads]
    master = MockMaster(endpoints, device_profiles=profiles)
    master.connect(target_state="preop")
    return master, endpoints


def connected_pysoem(input_payloads):
    profiles = [ByteProfile() for _ in input_payloads]
    master = PySOEMMaster("unused", device_profiles=profiles)
    transport = FakePysoemTransport(input_payloads)
    master._master = transport
    master._pysoem = SimpleNamespace()
    return master, transport


class PdoTransportParityTest(unittest.TestCase):
    def backends(self, input_payloads=(b"\x07",)):
        mock, mock_transport = connected_mock(input_payloads)
        real, real_transport = connected_pysoem(input_payloads)
        return (
            (mock, mock_transport),
            (real, real_transport),
        )

    def test_both_backends_enforce_prepare_send_receive_order(self):
        for master, _transport in self.backends():
            with self.subTest(backend=type(master).__name__, operation="send"):
                with self.assertRaisesRegex(RuntimeError, "prepare_processdata"):
                    master.send_processdata()
            with self.subTest(backend=type(master).__name__, operation="receive"):
                with self.assertRaisesRegex(RuntimeError, "send_processdata"):
                    master.receive_processdata()

            master.prepare_processdata()
            with self.subTest(backend=type(master).__name__, operation="prepare"):
                with self.assertRaisesRegex(RuntimeError, "phase is prepared"):
                    master.prepare_processdata()
            master.send_processdata()
            with self.subTest(backend=type(master).__name__, operation="second send"):
                with self.assertRaisesRegex(RuntimeError, "receive_processdata"):
                    master.send_processdata()
            master.receive_processdata()

    def test_prepare_freezes_output_until_the_next_cycle(self):
        for master, transport in self.backends():
            runtime = master.slaves[0]
            txpdo_identity = runtime.txpdo
            runtime.rxpdo.value = 11
            master.prepare_processdata()
            self.assertEqual(runtime.prepared_output, b"\x0B")

            runtime.rxpdo.value = 22
            master.send_processdata()
            self.assertEqual(runtime.transmitted_output, b"\x0B")
            master.receive_processdata()

            if isinstance(master, MockMaster):
                self.assertEqual(transport[0].outputs, [b"\x0B"])
            else:
                self.assertEqual(transport.sent_outputs, [(b"\x0B",)])
            self.assertEqual(runtime.txpdo.value, 7)
            self.assertIs(runtime.txpdo, txpdo_identity)
            self.assertEqual(runtime.received_input, b"\x07")
            self.assertEqual(master.get_slave_output_bytes(0), b"\x0B")
            self.assertEqual(master.get_slave_input_bytes(0), b"\x07")

            master.prepare_processdata()
            master.send_processdata()
            master.receive_processdata()
            if isinstance(master, MockMaster):
                self.assertEqual(transport[0].outputs[-1], b"\x16")
            else:
                self.assertEqual(transport.sent_outputs[-1], (b"\x16",))

    def test_multi_slave_decode_failure_does_not_partially_commit_txpdo(self):
        for master, _transport in self.backends((b"\x2A", b"")):
            master.prepare_processdata()
            master.send_processdata()

            with self.subTest(backend=type(master).__name__):
                with self.assertRaisesRegex(ValueError, "TxPDO payload"):
                    master.receive_processdata()

            self.assertEqual([slave.txpdo.value for slave in master.slaves], [0, 0])
            self.assertEqual(
                [slave.received_input for slave in master.slaves],
                [None, None],
            )

    def test_successful_cycle_updates_common_wkc_and_timing_fields(self):
        for master, _transport in self.backends():
            master.prepare_processdata()
            master.send_processdata()
            wkc = master.receive_processdata()

            self.assertEqual(wkc, master.expected_wkc())
            self.assertIsNotNone(master.last_tx_monotonic_ns)
            self.assertIsNotNone(master.last_rx_monotonic_ns)
            self.assertGreaterEqual(master.last_tx_prepare_duration_ns, 0)
            self.assertGreaterEqual(master.last_send_call_duration_ns, 0)

    def test_failed_real_send_does_not_commit_the_transmitted_snapshot(self):
        master, transport = connected_pysoem((b"\x07",))
        runtime = master.slaves[0]
        runtime.rxpdo.value = 11
        master.prepare_processdata()
        transport.send_exception = OSError("send failed")

        with self.assertRaises(CommunicationException):
            master.send_processdata()

        self.assertEqual(runtime.prepared_output, b"\x0B")
        self.assertIsNone(runtime.transmitted_output)
        self.assertTrue(master._processdata_prepared)
        self.assertFalse(master._processdata_sent)

        transport.send_exception = None
        master.send_processdata()
        master.receive_processdata()
        self.assertEqual(runtime.transmitted_output, b"\x0B")

    def test_mock_slave_is_a_raw_endpoint_only(self):
        profile = CMMTASDeviceProfile(axis_index=0, slave_index=0)
        servo = VirtualCiA402Servo(device_profile=profile)
        endpoint = MockSlave(servo, profile.pdo_configuration)
        master = MockMaster([endpoint], device_profiles=[profile])

        self.assertIsInstance(master.slaves[0], MasterPdoRuntime)
        for attribute in ("rxpdo", "txpdo", "pdo_codec"):
            self.assertFalse(hasattr(endpoint, attribute))
            self.assertTrue(hasattr(master.slaves[0], attribute))


if __name__ == "__main__":
    unittest.main()
