import struct
import time

from ethercat.distributed_clock import DistributedClock
from ethercat.sdo_access import SdoAccess
from ethercat.working_counter import WorkingCounter


class MockMaster:
    def __init__(
        self,
        slaves,
        cycle_time=0.001,
    ):
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
        object_key = (int(index), int(subindex))
        if object_key in self._float_sdo_objects():
            value = struct.unpack("<f", payload[:4])[0]
        else:
            signed = object_key in self._signed_sdo_objects()
            value = int.from_bytes(payload, "little", signed=signed)
        self._write_object(slave_index, index, value, subindex)

    def read_sdo(self, slave_index, index, subindex, size):
        value = self._read_object(slave_index, index, subindex)
        if isinstance(value, float):
            return struct.pack("<f", value)
        return int(value).to_bytes(
            size,
            "little",
            signed=int(value) < 0,
        )

    @staticmethod
    def _float_sdo_objects():
        return {
            (0x2183, 0x0C),
            (0x212E, 0x02),
            (0x212E, 0x09),
        }

    @staticmethod
    def _signed_sdo_objects():
        return {
            (0x6060, 0),
            (0x6098, 0),
            (0x607D, 1),
            (0x607D, 2),
        }

    def send_processdata(self):
        if not self._processdata_prepared:
            raise RuntimeError(
                "Call prepare_processdata() before send_processdata()."
            )
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

        if self._outputs_sent:
            self.wkc = self.working_counter.get_expected()
        else:
            self.wkc = 0

        self._outputs_sent = False
        self.last_rx_dc_time_ns = self.dc_time_ns
        self.last_rx_monotonic_ns = time.monotonic_ns()
        return self.wkc

    def get_dc_time_ns(self):
        return self.dc.get_time_ns()


    def _read_object(self, slave_index, index, subindex=0):
        slave = self.slaves[slave_index]
        if index == 0x6040:
            return slave.rxpdo.controlword
        if index == 0x2000 and subindex == 0x01:
            return getattr(slave, "_mock_device_reset_command", 0)
        if index == 0x2005:
            return self._read_mock_parameter_save(slave_index, subindex)
        if index == 0x6041:
            return slave.txpdo.statusword
        if index == 0x6060:
            return slave.rxpdo.mode_of_operation
        if index == 0x6061:
            return slave.txpdo.mode_of_operation_display
        if index == 0x6098:
            return slave.axis.servo.od.read(0x6098)
        if index == 0x6099:
            return slave.axis.servo.od.read(0x6099, subindex)
        if index == 0x609A:
            return slave.axis.servo.od.read(0x609A)
        if index == 0x607A:
            return slave.rxpdo.target_position
        if index == 0x6062:
            return getattr(
                slave.txpdo,
                "setpoint_position",
                slave.txpdo.actual_position,
            )
        if index == 0x607D:
            limits = slave.axis.get_software_position_limits()
            if subindex == 1:
                return limits["negative_limit"]
            if subindex == 2:
                return limits["positive_limit"]
            if subindex == 0:
                return 2
        if index == 0x1C32:
            if subindex == 1:
                return slave.axis.servo.od.read(0x1C32, 1)
            if subindex == 2:
                return slave.axis.servo.od.read(0x1C32, 2)
        if index == 0x6064:
            return slave.txpdo.actual_position
        if index == 0x606C:
            return slave.txpdo.actual_velocity
        if index == 0x60A4 and subindex == 1:
            return slave.axis.servo.od.read(0x60A4, 1)
        if index == 0x216E and subindex == 0x01:
            return slave.axis.servo.od.read(0x216E, 0x01)
        if index == 0x2194 and subindex in (0x01, 0x02, 0x03, 0x04):
            return slave.axis.servo.od.read(0x2194, subindex)
        if index == 0x2145 and subindex == 0x0C:
            return 0
        if index == 0x1001:
            return 0
        if index == 0x6081:
            if slave.rxpdo.has_field("profile_velocity"):
                return slave.rxpdo.profile_velocity
            return int(slave.axis.get_motion_limits()["max_velocity"])
        if index == 0x6083:
            return slave.axis.servo.od.read(0x6083)
        if index == 0x6084:
            return slave.axis.servo.od.read(0x6084)
        if index == 0x607F:
            return slave.axis.get_motion_limits()["max_velocity"]
        if index == 0x2183 and subindex == 0x0C:
            return slave.axis.servo.od.read(0x2183, 0x0C)
        if index == 0x60C5:
            return slave.axis.get_motion_limits()["acceleration"]
        if index == 0x60C6:
            return slave.axis.get_motion_limits()["deceleration"]
        raise KeyError(f"Unsupported mock SDO read 0x{index:04X}")

    def _write_object(self, slave_index, index, value, subindex=0):
        slave = self.slaves[slave_index]
        if index == 0x2000 and subindex == 0x01:
            slave._mock_device_reset_command = int(value)
            if int(value) == 1:
                self._restart_mock_axis(slave_index)
        elif index == 0x2005:
            self._write_mock_parameter_save(slave_index, subindex, value)
        elif index == 0x6040:
            slave.rxpdo.controlword = int(value)
        elif index == 0x6060:
            slave.rxpdo.mode_of_operation = int(value)
        elif index == 0x6098:
            slave.axis.servo.od.write(0x6098, int(value))
        elif index == 0x6099:
            if subindex not in (1, 2):
                raise KeyError(
                    f"Unsupported mock SDO write 0x{index:04X}:{subindex:02X}"
                )
            slave.axis.servo.od.write(0x6099, int(value), subindex)
        elif index == 0x609A:
            slave.axis.servo.od.write(0x609A, int(value))
        elif index == 0x607A:
            slave.rxpdo.target_position = value
        elif index == 0x6062:
            slave.txpdo.setpoint_position = value
        elif index == 0x607D:
            limits = slave.axis.get_software_position_limits()
            negative_limit = limits["negative_limit"]
            positive_limit = limits["positive_limit"]
            if subindex == 1:
                negative_limit = value
            elif subindex == 2:
                positive_limit = value
            else:
                raise KeyError(
                    f"Unsupported mock SDO write 0x{index:04X}:{subindex:02X}"
                )
            slave.axis.set_software_position_limits(
                negative_limit,
                positive_limit,
            )
        elif index == 0x1C32:
            if subindex not in (1, 2):
                raise KeyError(
                    f"Unsupported mock SDO write 0x{index:04X}:{subindex:02X}"
                )
            slave.axis.servo.od.write(0x1C32, int(value), subindex)
        elif index == 0x60A4 and subindex == 1:
            slave.axis.servo.od.write(0x60A4, int(value), 1)
        elif index == 0x216E and subindex == 0x01:
            slave.axis.servo.od.write(0x216E, int(value), 0x01)
        elif index == 0x2194 and subindex in (0x01, 0x02, 0x03, 0x04):
            slave.axis.servo.od.write(0x2194, int(value), subindex)
        elif index == 0x6081:
            if slave.rxpdo.has_field("profile_velocity"):
                slave.rxpdo.profile_velocity = int(value)
            slave.axis.servo.od.write(0x6081, int(value))
        elif index == 0x6083:
            slave.axis.servo.od.write(0x6083, int(value))
        elif index == 0x6084:
            slave.axis.servo.od.write(0x6084, int(value))
        elif index == 0x607F:
            slave.axis.servo.od.write(0x607F, value)
        elif index == 0x2183 and subindex == 0x0C:
            slave.axis.servo.od.write(0x2183, float(value), 0x0C)
        elif index == 0x60C5:
            slave.axis.servo.od.write(0x60C5, value)
        elif index == 0x60C6:
            slave.axis.servo.od.write(0x60C6, value)
        else:
            raise KeyError(f"Unsupported mock SDO write 0x{index:04X}")

    def _restart_mock_axis(self, slave_index):
        slave = self.slaves[slave_index]
        current_position = float(slave.txpdo.actual_position)
        slave.rxpdo.reset_values()
        slave.txpdo.reset_values()
        slave.rxpdo.target_position = current_position
        slave.txpdo.actual_position = current_position
        slave.txpdo.statusword = 0x0027
        slave.txpdo.mode_of_operation_display = slave.rxpdo.mode_of_operation

    def _read_mock_parameter_save(self, slave_index, subindex):
        slave = self.slaves[slave_index]
        state = getattr(slave, "_mock_parameter_save", {})
        if subindex == 0x01:
            return state.get("command", 0)
        if subindex == 0x02:
            return state.get("status", 0)
        if subindex == 0x03:
            return state.get("selection", 1)
        if subindex == 0x04:
            return state.get("return_code", 0)
        if subindex == 0x05:
            return state.get("return_value", 1)
        raise KeyError(f"Unsupported mock SDO read 0x2005:{subindex:02X}")

    def _write_mock_parameter_save(self, slave_index, subindex, value):
        slave = self.slaves[slave_index]
        state = getattr(slave, "_mock_parameter_save", None)
        if state is None:
            state = {}
            slave._mock_parameter_save = state
        if subindex == 0x01:
            state["command"] = int(value)
            if int(value) == 1:
                state["status"] = 0
                state["return_code"] = 0
                state["return_value"] = 1
            return
        if subindex == 0x03:
            state["selection"] = int(value)
            return
        raise KeyError(f"Unsupported mock SDO write 0x2005:{subindex:02X}")
