from dataclasses import dataclass
import os
from pathlib import Path
import struct
import sys

from ethercat.csp_trajectory_generator import CspTrajectoryGenerator
from ethercat.distributed_clock import DistributedClock
from ethercat.pdo_codec import CiA402PdoCodec
from ethercat.rxpdo import RxPDO
from ethercat.txpdo import TxPDO
from ethercat.working_counter import WorkingCounter


@dataclass
class AxisMotionLimits:
    max_velocity: float
    acceleration: float
    deceleration: float


class PySOEMPdoSlave:
    def __init__(self, motion_limits):
        self.rxpdo = RxPDO()
        self.txpdo = TxPDO()
        self.motion_limits = motion_limits


class PySOEMMaster:
    def __init__(
        self,
        interface_name,
        slave_count,
        cycle_time=0.001,
        motion_limits=None,
        csp_counts_per_unit=1.0,
        pdo_codec=CiA402PdoCodec,
    ):
        self.interface_name = interface_name
        self.slave_count = slave_count
        self.cycle_time = cycle_time
        self.csp_counts_per_unit = float(csp_counts_per_unit)
        self.pdo_codec = pdo_codec

        self.dc = DistributedClock()
        self.working_counter = WorkingCounter()
        self.wkc = 0
        self.dc_time_ns = 0
        self._outputs_sent = False
        self._pysoem = None
        self._master = None

        self.slaves = [
            PySOEMPdoSlave(self._motion_limits_for_index(motion_limits, index))
            for index in range(slave_count)
        ]

        self.trajectory_generators = [
            CspTrajectoryGenerator()
            for _ in self.slaves
        ]

        for _ in self.slaves:
            self.working_counter.add_slave()

    def connect(self, target_state=None, timeout_us=50000):
        pysoem = self._load_pysoem()

        self._master = pysoem.Master()
        self._master.open(self.interface_name)

        discovered_slaves = self._master.config_init()
        if discovered_slaves < self.slave_count:
            raise RuntimeError(
                f"Expected {self.slave_count} EtherCAT slaves, "
                f"found {discovered_slaves}."
            )

        self._master.config_map()

        if target_state is None:
            target_state = pysoem.OP_STATE

        if target_state == pysoem.OP_STATE:
            self._request_safe_operational(pysoem, timeout_us)
            self._prime_outputs()
            self._request_operational(pysoem, timeout_us)
            return

        self._master.state = target_state
        self._master.write_state()
        reached_state = self._master.state_check(
            target_state,
            timeout_us,
        )

        if reached_state != target_state:
            raise RuntimeError(
                "EtherCAT network did not reach requested state. "
                f"Requested={target_state}, reached={reached_state}."
            )

    def describe_slaves(self):
        if self._master is None:
            return []

        descriptions = []
        for index, slave in enumerate(self._master.slaves):
            descriptions.append(
                {
                    "index": index,
                    "name": getattr(slave, "name", ""),
                    "state": getattr(slave, "state", None),
                    "al_status": getattr(slave, "al_status", None),
                    "al_status_code": getattr(slave, "al_status_code", None),
                }
            )

        return descriptions

    def get_slave_input_bytes(self, slave_index=0):
        self._require_connected()
        return bytes(self._master.slaves[slave_index].input)

    def get_slave_output_bytes(self, slave_index=0):
        self._require_connected()
        return bytes(self._master.slaves[slave_index].output)

    def close(self):
        if self._master is None:
            return

        self._master.close()
        self._master = None

    def set_target_positions(self, target_positions):
        for generator, target_position in zip(
            self.trajectory_generators,
            target_positions,
        ):
            generator.set_target_position(target_position)

    def sync_trajectory_to_actual_positions(self):
        for generator, slave in zip(
            self.trajectory_generators,
            self.slaves,
        ):
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

    def sdo_write_int8(self, slave_index, index, subindex, value):
        self._require_connected()
        self._master.slaves[slave_index].sdo_write(
            index,
            subindex,
            struct.pack("<b", int(value)),
        )

    def sdo_write_uint16(self, slave_index, index, subindex, value):
        self._require_connected()
        self._master.slaves[slave_index].sdo_write(
            index,
            subindex,
            struct.pack("<H", int(value)),
        )

    def sdo_write_uint8(self, slave_index, index, subindex, value):
        self._require_connected()
        self._master.slaves[slave_index].sdo_write(
            index,
            subindex,
            struct.pack("<B", int(value)),
        )

    def sdo_write_uint32(self, slave_index, index, subindex, value):
        self._require_connected()
        self._master.slaves[slave_index].sdo_write(
            index,
            subindex,
            struct.pack("<I", int(value)),
        )

    def sdo_read_uint8(self, slave_index, index, subindex):
        self._require_connected()
        payload = self._master.slaves[slave_index].sdo_read(
            index,
            subindex,
            size=1,
        )
        return struct.unpack("<B", payload[:1])[0]

    def sdo_read_int8(self, slave_index, index, subindex):
        self._require_connected()
        payload = self._master.slaves[slave_index].sdo_read(
            index,
            subindex,
            size=1,
        )
        return struct.unpack("<b", payload[:1])[0]

    def sdo_read_uint16(self, slave_index, index, subindex):
        self._require_connected()
        payload = self._master.slaves[slave_index].sdo_read(
            index,
            subindex,
            size=2,
        )
        return struct.unpack("<H", payload[:2])[0]

    def sdo_read_uint32(self, slave_index, index, subindex):
        self._require_connected()
        payload = self._master.slaves[slave_index].sdo_read(
            index,
            subindex,
            size=4,
        )
        return struct.unpack("<I", payload[:4])[0]

    def set_axis_motion_limits(
        self,
        axis_index,
        max_velocity,
        acceleration,
        deceleration,
    ):
        self.slaves[axis_index].motion_limits = AxisMotionLimits(
            float(max_velocity),
            float(acceleration),
            float(deceleration),
        )

    def send_processdata(self):
        self._require_connected()

        self.dc_time_ns = self.dc.get_time_ns()
        self._update_csp_targets()
        self._write_outputs()
        self._master.send_processdata()
        self._outputs_sent = True

    def receive_processdata(self, timeout_us=2000):
        self._require_connected()

        self.wkc = self._master.receive_processdata(timeout_us)
        self._read_inputs()
        self._outputs_sent = False
        return self.wkc

    def expected_wkc(self):
        if self._master is not None:
            return self._master.expected_wkc

        return self.working_counter.get_expected()

    def _write_outputs(self):
        for index, slave in enumerate(self.slaves):
            self._master.slaves[index].output = self.pdo_codec.encode_rxpdo(
                slave.rxpdo
            )

    def _read_inputs(self):
        for index, slave in enumerate(self.slaves):
            self.pdo_codec.decode_txpdo(
                self._master.slaves[index].input,
                slave.txpdo,
            )

    def _request_safe_operational(self, pysoem, timeout_us):
        self._master.state = pysoem.SAFEOP_STATE
        self._master.write_state()
        reached_state = self._master.state_check(
            pysoem.SAFEOP_STATE,
            timeout_us,
        )

        if reached_state != pysoem.SAFEOP_STATE:
            raise RuntimeError(
                "EtherCAT network did not reach SAFE_OP. "
                f"Reached={reached_state}. Slaves={self.describe_slaves()}"
            )

    def _prime_outputs(self):
        self._update_csp_targets()
        self._write_outputs()

        for _ in range(10):
            self._master.send_processdata()
            self._master.receive_processdata(2000)

    def _request_operational(self, pysoem, timeout_us):
        self._master.state = pysoem.OP_STATE
        self._master.write_state()

        reached_state = pysoem.NONE_STATE
        for _ in range(100):
            self._update_csp_targets()
            self._write_outputs()
            self._master.send_processdata()
            self.wkc = self._master.receive_processdata(2000)
            reached_state = self._master.state_check(
                pysoem.OP_STATE,
                timeout_us,
            )

            if reached_state == pysoem.OP_STATE:
                return

        raise RuntimeError(
            "EtherCAT network did not reach OP. "
            f"Requested={pysoem.OP_STATE}, reached={reached_state}, "
            f"WKC={self.wkc}/{self.expected_wkc()}, "
            f"Slaves={self.describe_slaves()}"
        )

    def _update_csp_targets(self):
        for slave, generator in zip(
            self.slaves,
            self.trajectory_generators,
        ):
            if slave.rxpdo.mode_of_operation != 8:
                continue

            limits = slave.motion_limits
            slave.rxpdo.target_position = int(round(generator.update(
                self.cycle_time,
                limits.max_velocity * self.csp_counts_per_unit,
                limits.acceleration * self.csp_counts_per_unit,
                limits.deceleration * self.csp_counts_per_unit,
            )))

    def _require_connected(self):
        if self._master is None:
            raise RuntimeError(
                "PySOEMMaster is not connected. Call connect() first."
            )

    def _load_pysoem(self):
        if self._pysoem is not None:
            return self._pysoem

        self._add_windows_npcap_dll_paths()

        try:
            import pysoem
        except ImportError as exc:
            raise RuntimeError(
                "pysoem is not installed. Install pysoem in the ROS2 "
                "environment before using PySOEMMaster."
            ) from exc

        self._pysoem = pysoem
        return self._pysoem

    def _add_windows_npcap_dll_paths(self):
        if not sys.platform.startswith("win"):
            return

        candidates = [
            Path("C:/Windows/System32/Npcap"),
            Path("C:/Program Files/Npcap"),
            Path("C:/Program Files (x86)/Npcap"),
        ]

        for path in candidates:
            if not path.exists():
                continue

            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(path))

            os.environ["PATH"] = (
                f"{path}{os.pathsep}{os.environ.get('PATH', '')}"
            )

    def _motion_limits_for_index(self, motion_limits, index):
        if motion_limits is None:
            return AxisMotionLimits(
                max_velocity=1000.0,
                acceleration=500.0,
                deceleration=500.0,
            )

        limits = motion_limits[index]

        if isinstance(limits, AxisMotionLimits):
            return limits

        return AxisMotionLimits(
            max_velocity=float(limits["max_velocity"]),
            acceleration=float(limits["acceleration"]),
            deceleration=float(limits["deceleration"]),
        )
