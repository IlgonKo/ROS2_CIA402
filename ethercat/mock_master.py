import time

from ethercat.distributed_clock import DistributedClock
from ethercat.master_pdo_runtime import MasterPdoRuntime
from ethercat.sdo_access import SdoAccess
from ethercat.working_counter import WorkingCounter
from motion_server.failure import (
    CommunicationException,
    CommunicationTimeoutException,
    MotionServerException,
)


class MockMaster:
    """Generic in-process EtherCAT transport for virtual slaves."""

    def __init__(self, slave_endpoints, *, device_profiles, cycle_time=0.001):
        self._slave_endpoints = list(slave_endpoints)
        self.device_profiles = list(device_profiles)
        if len(self._slave_endpoints) != len(self.device_profiles):
            raise ValueError(
                "MockMaster requires one device profile per raw slave endpoint."
            )
        self.slaves = [
            MasterPdoRuntime(device_profile)
            for device_profile in self.device_profiles
        ]
        self.cycle_time = cycle_time
        self.dc = DistributedClock()
        self.working_counter = WorkingCounter()
        self.wkc = 0
        self.dc_time_ns = 0
        self.last_tx_dc_time_ns = 0
        self.last_direct_tx_dc_time_ns = 0
        self.last_rx_dc_time_ns = 0
        self.last_tx_monotonic_ns = None
        self.last_rx_monotonic_ns = None
        self.last_tx_prepare_duration_ns = 0
        self.last_send_call_duration_ns = 0
        self._outputs_sent = False
        self._processdata_prepared = False
        self._connected = False
        self._state = "closed"
        self.lifecycle_events = []
        self.last_diagnostics = []
        self.sdo = SdoAccess(self)
        for _ in self._slave_endpoints:
            self.working_counter.add_slave()

    def connect(self, target_state=None, timeout_s=None):
        normalized_state = str(target_state or "").strip().lower()
        if normalized_state not in {"preop", "pre_op"}:
            raise ValueError("MockMaster staged startup requires target_state='preop'")
        self._reset_processdata_state()
        self._connected = True
        self._state = "preop"
        self.lifecycle_events.append("connect:preop")
        try:
            self._prepare_device_profiles()
        except Exception:
            self.close()
            raise

    def enter_operational(self, timeout_s=None):
        if self._state != "preop":
            raise RuntimeError("MockMaster must connect in PRE-OP before entering OP")
        self._connected = True
        self._state = "op"
        self.lifecycle_events.append("enter_operational")

    def close(self):
        self._connected = False
        self._state = "closed"
        self._reset_processdata_state()
        self.lifecycle_events.append("close")

    def expected_wkc(self):
        return self.working_counter.get_expected()

    def transport_available(self):
        return self._connected

    def get_slave_input_bytes(self, slave_index=0):
        payload = self.slaves[int(slave_index)].received_input
        return b"" if payload is None else bytes(payload)

    def get_slave_output_bytes(self, slave_index=0):
        payload = self.slaves[int(slave_index)].transmitted_output
        return b"" if payload is None else bytes(payload)

    def write_sdo(self, slave_index, index, subindex, payload):
        try:
            self._slave_endpoints[int(slave_index)].write_sdo(
                index, subindex, payload,
            )
        except Exception as exception:
            self._raise_sdo_exception(exception, "sdo_write")

    def read_sdo(self, slave_index, index, subindex, size):
        try:
            return self._slave_endpoints[int(slave_index)].read_sdo(
                index, subindex, size,
            )
        except Exception as exception:
            self._raise_sdo_exception(exception, "sdo_read")

    def _prepare_device_profiles(self):
        for slave_index, slave in enumerate(self.slaves):
            slave.device_profile.prepare_process_image(
                self,
                slave_index,
            )

    def read_assigned_pdo_indices(self, slave_index, assignment_index):
        count = self.sdo.read_uint8(slave_index, assignment_index, 0)
        return [
            self.sdo.read_uint16(slave_index, assignment_index, subindex)
            for subindex in range(1, count + 1)
        ]

    def read_pdo_mapping_entries(self, slave_index, pdo_index):
        count = self.sdo.read_uint8(slave_index, pdo_index, 0)
        return [
            self.sdo.read_uint32(slave_index, pdo_index, subindex)
            for subindex in range(1, count + 1)
        ]

    def read_assigned_pdo_mapping_entries(self, slave_index, assignment_index):
        entries = []
        for pdo_index in self.read_assigned_pdo_indices(
            slave_index,
            assignment_index,
        ):
            entries.extend(self.read_pdo_mapping_entries(slave_index, pdo_index))
        return entries

    def read_slave_identity(self, slave_index):
        self._require_connected()
        return dict(self._slave_endpoints[int(slave_index)].read_identity())

    @staticmethod
    def _raise_sdo_exception(exception, operation):
        if isinstance(exception, MotionServerException):
            raise exception
        if isinstance(exception, TimeoutError):
            raise CommunicationTimeoutException(operation) from exception
        if isinstance(exception, (ConnectionError, OSError)):
            raise CommunicationException(operation) from exception
        raise exception

    def send_processdata(self):
        self._require_connected()
        if self._outputs_sent:
            raise RuntimeError(
                "Call receive_processdata() before sending another PDO cycle."
            )
        if not self._processdata_prepared:
            raise RuntimeError("Call prepare_processdata() before send_processdata().")

        snapshots = [
            slave.transmitted_output_candidate()
            for slave in self.slaves
        ]
        self.dc_time_ns = self.dc.get_time_ns()
        self.last_tx_monotonic_ns = time.monotonic_ns()
        self.last_direct_tx_dc_time_ns = self.dc_time_ns
        self.last_tx_dc_time_ns = self.dc_time_ns
        send_start_ns = time.monotonic_ns()
        for slave, payload in zip(self.slaves, snapshots):
            slave.commit_transmitted_output(payload)
        self.last_send_call_duration_ns = time.monotonic_ns() - send_start_ns
        self._outputs_sent = True
        self._processdata_prepared = False

    def prepare_processdata(self):
        self._require_connected()
        self._require_processdata_phase("idle", "prepare_processdata")
        prepare_start_ns = time.monotonic_ns()
        candidates = [
            slave.encode_output_candidate()
            for slave in self.slaves
        ]
        for slave, payload in zip(self.slaves, candidates):
            slave.commit_prepared_output(payload)
        self.last_tx_prepare_duration_ns = (
            time.monotonic_ns() - prepare_start_ns
        )
        self._processdata_prepared = True

    def receive_processdata(self):
        self._require_connected()
        if not self._outputs_sent:
            raise RuntimeError(
                "Call send_processdata() before receive_processdata()."
            )
        try:
            payloads = [
                endpoint.exchange_processdata(slave.transmitted_output)
                for endpoint, slave in zip(self._slave_endpoints, self.slaves)
            ]
        except (ConnectionError, OSError) as exception:
            raise CommunicationException("processdata_receive") from exception
        receive_monotonic_ns = time.monotonic_ns()
        self.wkc = self.working_counter.get_expected()
        self.dc_time_ns = self.dc.get_time_ns()
        self.last_rx_dc_time_ns = self.dc_time_ns
        self.last_rx_monotonic_ns = receive_monotonic_ns
        validated_payloads = [
            slave.validate_input_payload(payload)
            for slave, payload in zip(self.slaves, payloads)
        ]
        for slave, payload in zip(self.slaves, validated_payloads):
            slave.decode_input(payload)
        self._outputs_sent = False
        return self.wkc

    def get_dc_time_ns(self):
        return self.dc.get_time_ns()

    def _require_connected(self):
        if not self._connected:
            raise RuntimeError(
                "MockMaster is not connected. Call connect() first."
            )

    def _reset_processdata_state(self):
        self._outputs_sent = False
        self._processdata_prepared = False
        self.wkc = 0
        self.dc_time_ns = 0
        self.last_tx_dc_time_ns = 0
        self.last_direct_tx_dc_time_ns = 0
        self.last_rx_dc_time_ns = 0
        self.last_tx_monotonic_ns = None
        self.last_rx_monotonic_ns = None
        self.last_tx_prepare_duration_ns = 0
        self.last_send_call_duration_ns = 0
        for slave in self.slaves:
            slave.reset_processdata()

    def _require_processdata_phase(self, expected, operation):
        phase = (
            "sent" if self._outputs_sent
            else "prepared" if self._processdata_prepared
            else "idle"
        )
        if phase != expected:
            raise RuntimeError(
                f"Cannot {operation} while PDO cycle phase is {phase}. "
                "Expected prepare -> send -> receive."
            )
