import time

from ethercat.distributed_clock import DistributedClock
from ethercat.sdo_access import SdoAccess
from ethercat.working_counter import WorkingCounter


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
        self.last_diagnostics = []
        self.sdo = SdoAccess(self)
        for _ in self.slaves:
            self.working_counter.add_slave()

    def connect(self, target_state=None):
        self._connected = True

    def enter_operational(self):
        self._connected = True

    def close(self):
        self._connected = False

    def expected_wkc(self):
        return self.working_counter.get_expected()

    def write_sdo(self, slave_index, index, subindex, payload):
        self.slaves[int(slave_index)].write_sdo(index, subindex, payload)

    def read_sdo(self, slave_index, index, subindex, size):
        return self.slaves[int(slave_index)].read_sdo(index, subindex, size)

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
        for slave in self.slaves:
            slave.process()
        self.wkc = self.working_counter.get_expected() if self._outputs_sent else 0
        self._outputs_sent = False
        self.last_rx_dc_time_ns = self.dc_time_ns
        self.last_rx_monotonic_ns = time.monotonic_ns()
        return self.wkc

    def get_dc_time_ns(self):
        return self.dc.get_time_ns()
