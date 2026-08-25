import time

from ethercat.distributed_clock import DistributedClock
from ethercat.sdo_access import SdoAccess
from ethercat.working_counter import WorkingCounter
from motion_server.failure import (
    CommunicationException,
    CommunicationTimeoutException,
    MotionServerException,
)


class MockMaster:
    """Generic in-process EtherCAT transport for virtual slaves."""

    def __init__(self, slaves, cycle_time=0.001):
        self.slaves = slaves
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
        self._outputs_sent = False
        self._processdata_prepared = False
        self._connected = False
        self._state = "closed"
        self.lifecycle_events = []
        self.last_diagnostics = []
        self.sdo = SdoAccess(self)
        for _ in self.slaves:
            self.working_counter.add_slave()

    def connect(self, target_state=None, timeout_s=None):
        normalized_state = str(target_state or "").strip().lower()
        if normalized_state not in {"preop", "pre_op"}:
            raise ValueError("MockMaster staged startup requires target_state='preop'")
        self._connected = True
        self._state = "preop"
        self.lifecycle_events.append("connect:preop")

    def enter_operational(self, timeout_s=None):
        if self._state != "preop":
            raise RuntimeError("MockMaster must connect in PRE-OP before entering OP")
        self._connected = True
        self._state = "op"
        self.lifecycle_events.append("enter_operational")

    def close(self):
        self._connected = False
        self._state = "closed"
        self.lifecycle_events.append("close")

    def expected_wkc(self):
        return self.working_counter.get_expected()

    def transport_available(self):
        return self._connected

    def write_sdo(self, slave_index, index, subindex, payload):
        try:
            self.slaves[int(slave_index)].write_sdo(index, subindex, payload)
        except Exception as exception:
            self._raise_sdo_exception(exception, "sdo_write")

    def read_sdo(self, slave_index, index, subindex, size):
        try:
            return self.slaves[int(slave_index)].read_sdo(index, subindex, size)
        except Exception as exception:
            self._raise_sdo_exception(exception, "sdo_read")

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
        if not self._processdata_prepared:
            raise RuntimeError("Call prepare_processdata() before send_processdata().")
        self.dc_time_ns = self.dc.get_time_ns()
        self.last_tx_monotonic_ns = time.monotonic_ns()
        self.last_direct_tx_dc_time_ns = self.dc_time_ns
        self.last_tx_dc_time_ns = self.dc_time_ns
        self._outputs_sent = True
        self._processdata_prepared = False

    def prepare_processdata(self):
        self._processdata_prepared = True

    def receive_processdata(self):
        try:
            for slave in self.slaves:
                slave.process()
        except (ConnectionError, OSError) as exception:
            raise CommunicationException("processdata_receive") from exception
        self.wkc = self.working_counter.get_expected() if self._outputs_sent else 0
        self._outputs_sent = False
        self.last_rx_dc_time_ns = self.dc_time_ns
        self.last_rx_monotonic_ns = time.monotonic_ns()
        return self.wkc

    def get_dc_time_ns(self):
        return self.dc.get_time_ns()
