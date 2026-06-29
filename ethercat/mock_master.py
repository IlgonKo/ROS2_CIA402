from ethercat.distributed_clock import DistributedClock
from ethercat.csp_trajectory_generator import CspTrajectoryGenerator
from ethercat.working_counter import WorkingCounter


class MockMaster:
    def __init__(self, slaves, cycle_time=0.001, csp_counts_per_unit=1.0):
        self.slaves = slaves
        self.cycle_time = cycle_time
        self.csp_counts_per_unit = float(csp_counts_per_unit)
        self.dc = DistributedClock()
        self.working_counter = WorkingCounter()
        self.wkc = 0
        self.dc_time_ns = 0
        self._outputs_sent = False
        self._connected = False
        self.last_diagnostics = []
        self.trajectory_generators = [
            CspTrajectoryGenerator(slave.txpdo.actual_position)
            for slave in self.slaves
        ]

        for _ in self.slaves:
            self.working_counter.add_slave()

    def connect(self):
        self._connected = True

    def close(self):
        self._connected = False

    def expected_wkc(self):
        return self.working_counter.get_expected()

    def set_target_positions(self, target_positions):
        for generator, target_position in zip(
            self.trajectory_generators,
            target_positions,
        ):
            generator.set_target_position(target_position)

    def sync_trajectory_to_actual_positions(self):
        for generator, slave in zip(self.trajectory_generators, self.slaves):
            actual_position = float(slave.txpdo.actual_position)
            generator.command_position = actual_position
            generator.target_position = actual_position
            generator.command_velocity = 0.0

    def sync_trajectory_to_actual_position(self, axis_index):
        generator = self.trajectory_generators[axis_index]
        actual_position = float(self.slaves[axis_index].txpdo.actual_position)
        generator.command_position = actual_position
        generator.target_position = actual_position
        generator.command_velocity = 0.0

    def set_controlword_all(self, controlword):
        for slave in self.slaves:
            slave.rxpdo.controlword = controlword

    def set_mode_of_operation_all(self, mode_of_operation):
        for slave in self.slaves:
            slave.rxpdo.mode_of_operation = mode_of_operation

    def set_axis_motion_limits(
        self,
        axis_index,
        max_velocity,
        acceleration,
        deceleration,
    ):
        slave = self.slaves[axis_index]
        slave.motion_limits.max_velocity = float(max_velocity)
        slave.motion_limits.acceleration = float(acceleration)
        slave.motion_limits.deceleration = float(deceleration)
        slave.axis.set_motion_limits(max_velocity, acceleration, deceleration)

    def sdo_write_int8(self, slave_index, index, subindex, value):
        self._write_object(slave_index, index, value, subindex)

    def sdo_write_int32(self, slave_index, index, subindex, value):
        self._write_object(slave_index, index, value, subindex)

    def sdo_write_uint8(self, slave_index, index, subindex, value):
        self._write_object(slave_index, index, value, subindex)

    def sdo_write_uint16(self, slave_index, index, subindex, value):
        self._write_object(slave_index, index, value, subindex)

    def sdo_write_uint32(self, slave_index, index, subindex, value):
        self._write_object(slave_index, index, value, subindex)

    def sdo_read_int8(self, slave_index, index, subindex):
        return int(self._read_object(slave_index, index, subindex))

    def sdo_read_int32(self, slave_index, index, subindex):
        return int(self._read_object(slave_index, index, subindex))

    def sdo_read_uint8(self, slave_index, index, subindex):
        return int(self._read_object(slave_index, index, subindex)) & 0xFF

    def sdo_read_uint16(self, slave_index, index, subindex):
        return int(self._read_object(slave_index, index, subindex)) & 0xFFFF

    def sdo_read_uint32(self, slave_index, index, subindex):
        return int(self._read_object(slave_index, index, subindex)) & 0xFFFFFFFF

    def send_processdata(self):
        self.dc_time_ns = self.dc.get_time_ns()
        self._update_csp_targets()
        self._outputs_sent = True

    def receive_processdata(self):
        for slave in self.slaves:
            slave.process()

        if self._outputs_sent:
            self.wkc = self.working_counter.get_expected()
        else:
            self.wkc = 0

        self._outputs_sent = False
        return self.wkc

    def _update_csp_targets(self):
        for slave, generator in zip(
            self.slaves,
            self.trajectory_generators,
        ):
            if slave.rxpdo.mode_of_operation != 8:
                continue

            limits = slave.axis.get_motion_limits()
            slave.rxpdo.target_position = generator.update(
                self.cycle_time,
                float(limits["max_velocity"]) * self.csp_counts_per_unit,
                float(limits["acceleration"]) * self.csp_counts_per_unit,
                float(limits["deceleration"]) * self.csp_counts_per_unit,
            )

    def _read_object(self, slave_index, index, subindex=0):
        slave = self.slaves[slave_index]
        if index == 0x6040:
            return slave.rxpdo.controlword
        if index == 0x6041:
            return slave.txpdo.statusword
        if index == 0x6060:
            return slave.rxpdo.mode_of_operation
        if index == 0x6061:
            return slave.txpdo.mode_of_operation_display
        if index == 0x607A:
            return slave.rxpdo.target_position
        if index == 0x607D:
            limits = slave.axis.get_software_position_limits()
            if subindex == 1:
                return limits["negative_limit"]
            if subindex == 2:
                return limits["positive_limit"]
            if subindex == 0:
                return 2
        if index == 0x6064:
            return slave.txpdo.actual_position
        if index == 0x606C:
            return slave.txpdo.actual_velocity
        if index == 0x603F:
            return 0
        if index == 0x1001:
            return 0
        if index == 0x6081:
            return slave.rxpdo.profile_velocity
        if index == 0x6083:
            return slave.motion_limits.acceleration
        if index == 0x6084:
            return slave.motion_limits.deceleration
        raise KeyError(f"Unsupported mock SDO read 0x{index:04X}")

    def _write_object(self, slave_index, index, value, subindex=0):
        slave = self.slaves[slave_index]
        if index == 0x6040:
            slave.rxpdo.controlword = int(value)
        elif index == 0x6060:
            slave.rxpdo.mode_of_operation = int(value)
        elif index == 0x607A:
            slave.rxpdo.target_position = value
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
        elif index == 0x6081:
            slave.rxpdo.profile_velocity = int(value)
            slave.motion_limits.max_velocity = float(value)
            slave.axis.set_motion_limits(
                slave.motion_limits.max_velocity,
                slave.motion_limits.acceleration,
                slave.motion_limits.deceleration,
            )
        elif index == 0x6083:
            slave.motion_limits.acceleration = float(value)
            slave.axis.set_motion_limits(
                slave.motion_limits.max_velocity,
                slave.motion_limits.acceleration,
                slave.motion_limits.deceleration,
            )
        elif index == 0x6084:
            slave.motion_limits.deceleration = float(value)
            slave.axis.set_motion_limits(
                slave.motion_limits.max_velocity,
                slave.motion_limits.acceleration,
                slave.motion_limits.deceleration,
            )
        else:
            raise KeyError(f"Unsupported mock SDO write 0x{index:04X}")
