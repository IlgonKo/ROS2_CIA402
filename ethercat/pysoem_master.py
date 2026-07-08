from dataclasses import dataclass
import os
from pathlib import Path
import struct
import sys
import time

from motion.csp_trajectory_generator import CspTrajectoryGenerator
from device import get_device_profile
from device.cmmt.pdo_codec import CiA402PdoCodec
from device.cmmt.rxpdo import RxPDO
from device.cmmt.txpdo import TxPDO
from ethercat.distributed_clock import DistributedClock
from ethercat.working_counter import WorkingCounter


AL_STATUS_DESCRIPTIONS = {
    0x001D: "Invalid output configuration",
    0x001E: "Invalid input configuration",
    0x001F: "Invalid watchdog configuration",
}


@dataclass
class AxisMotionLimits:
    max_velocity: float
    acceleration: float
    deceleration: float
    jerk: float = 0.0


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
        device_profile=None,
        csp_counts_per_unit=1.0,
        sync_mode=None,
        dc_enabled=False,
        dc_sync0_shift_time=0,
        pdo_codec=CiA402PdoCodec,
        txpdo_setpoint_entry=False,
        csp_velocity_offset_enabled=False,
        csp_command_step_threshold=0.0,
        csp_command_step_error_threshold=0.0,
        csp_profile="quintic",
    ):
        self.interface_name = interface_name
        self.slave_count = slave_count
        self.cycle_time = cycle_time
        self.device_profile = device_profile or get_device_profile("cmmt")
        self.csp_counts_per_unit = float(csp_counts_per_unit)
        self.sync_mode = sync_mode
        self.dc_enabled = bool(dc_enabled)
        if not self.dc_enabled and self.sync_mode is not None:
            self.sync_mode = 0
        self.dc_sync0_shift_time = int(dc_sync0_shift_time)
        self.pdo_codec = pdo_codec
        self.txpdo_setpoint_entry = bool(txpdo_setpoint_entry)
        self.csp_velocity_offset_enabled = bool(csp_velocity_offset_enabled)
        self.csp_command_step_threshold = float(csp_command_step_threshold)
        self.csp_command_step_error_threshold = float(
            csp_command_step_error_threshold
        )
        self.csp_profile = str(csp_profile).strip().lower()
        self.last_csp_command_steps = []
        self.last_csp_output_steps = []

        self.dc = DistributedClock()
        self.working_counter = WorkingCounter()
        self.wkc = 0
        self.dc_time_ns = 0
        self.last_tx_dc_time_ns = 0
        self.last_direct_tx_dc_time_ns = 0
        self.last_rx_dc_time_ns = 0
        self._last_rx_monotonic_ns = None
        self._last_tx_monotonic_ns = None
        self.last_tx_prepare_duration_ns = 0
        self.last_send_call_duration_ns = 0
        self._last_output_target_positions = [None for _ in range(slave_count)]
        self._outputs_sent = False
        self._processdata_prepared = False
        self._pysoem = None
        self._master = None

        self.slaves = [
            PySOEMPdoSlave(self._motion_limits_for_index(motion_limits, index))
            for index in range(slave_count)
        ]

        self.trajectory_generators = [
            CspTrajectoryGenerator(
                csp_profile=self.csp_profile,
            )
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

        self._request_pre_operational(pysoem, timeout_us)
        self._configure_rxpdo_mapping()
        self._configure_txpdo_mapping()
        self._master.config_map()
        self._configure_distributed_clocks()

        if target_state is None:
            target_state = pysoem.OP_STATE

        if target_state in (pysoem.SAFEOP_STATE, pysoem.OP_STATE):
            self._configure_sync_parameters()
            self._configure_dc_sync0()

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

        try:
            self._master.read_state()
        except Exception:
            pass

        descriptions = []
        for index, slave in enumerate(self._master.slaves):
            al_status = getattr(slave, "al_status", None)
            descriptions.append(
                {
                    "index": index,
                    "name": getattr(slave, "name", ""),
                    "state": getattr(slave, "state", None),
                    "state_description": self._state_description(
                        getattr(slave, "state", None)
                    ),
                    "al_status": al_status,
                    "al_status_description": (
                        AL_STATUS_DESCRIPTIONS.get(al_status)
                    ),
                    "al_status_code": getattr(slave, "al_status_code", None),
                }
            )

        return descriptions

    def _state_description(self, state):
        if state is None:
            return None

        state = int(state)
        base_state = state & 0x0F
        labels = {
            0x01: "INIT",
            0x02: "PRE_OP",
            0x03: "BOOT",
            0x04: "SAFE_OP",
            0x08: "OP",
        }
        label = labels.get(base_state, f"UNKNOWN_{base_state}")
        if state & 0x10:
            return f"{label} + ERROR"
        return label

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
            generator.reset(actual_position)

    def sync_trajectory_to_actual_position(self, axis_index):
        generator = self.trajectory_generators[axis_index]
        actual_position = float(self.slaves[axis_index].txpdo.actual_position)
        generator.reset(actual_position)

    def set_controlword_all(self, controlword):
        for slave in self.slaves:
            slave.rxpdo.controlword = controlword

    def set_mode_of_operation_all(self, mode_of_operation):
        for slave in self.slaves:
            slave.rxpdo.mode_of_operation = mode_of_operation

    def sdo_write_int8(self, slave_index, index, subindex, value):
        self._sdo_write(
            slave_index,
            index,
            subindex,
            struct.pack("<b", int(value)),
            value,
        )

    def sdo_write_int32(self, slave_index, index, subindex, value):
        self._sdo_write(
            slave_index,
            index,
            subindex,
            struct.pack("<i", int(value)),
            value,
        )

    def sdo_write_uint16(self, slave_index, index, subindex, value):
        self._sdo_write(
            slave_index,
            index,
            subindex,
            struct.pack("<H", int(value)),
            value,
        )

    def sdo_write_uint8(self, slave_index, index, subindex, value):
        self._sdo_write(
            slave_index,
            index,
            subindex,
            struct.pack("<B", int(value)),
            value,
        )

    def sdo_write_uint32(self, slave_index, index, subindex, value):
        self._sdo_write(
            slave_index,
            index,
            subindex,
            struct.pack("<I", int(value)),
            value,
        )

    def sdo_write_float32(self, slave_index, index, subindex, value):
        self._sdo_write(
            slave_index,
            index,
            subindex,
            struct.pack("<f", float(value)),
            value,
        )

    def _sdo_write(self, slave_index, index, subindex, payload, value):
        self._require_connected()
        try:
            self._master.slaves[slave_index].sdo_write(index, subindex, payload)
        except Exception as exc:
            raise RuntimeError(
                "SDO write failed: "
                f"slave={slave_index} object=0x{index:04X}:{subindex:02X} "
                f"value={value!r} payload={payload.hex()} error={exc}"
            ) from exc

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

    def sdo_read_int32(self, slave_index, index, subindex):
        self._require_connected()
        payload = self._master.slaves[slave_index].sdo_read(
            index,
            subindex,
            size=4,
        )
        return struct.unpack("<i", payload[:4])[0]

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

    def sdo_read_float32(self, slave_index, index, subindex):
        self._require_connected()
        payload = self._master.slaves[slave_index].sdo_read(
            index,
            subindex,
            size=4,
        )
        return struct.unpack("<f", payload[:4])[0]

    def set_axis_motion_limits(
        self,
        axis_index,
        max_velocity,
        acceleration,
        deceleration,
        jerk=0.0,
    ):
        self.slaves[axis_index].motion_limits = AxisMotionLimits(
            float(max_velocity),
            float(acceleration),
            float(deceleration),
            float(jerk),
        )

    def send_processdata(self):
        self.prepare_processdata()
        self.send_prepared_processdata()

    def prepare_processdata(self):
        self._require_connected()

        prepare_start_ns = time.monotonic_ns()
        self._update_csp_targets()
        self._write_outputs()
        self.last_tx_prepare_duration_ns = (
            time.monotonic_ns() - prepare_start_ns
        )
        self._processdata_prepared = True

    def send_prepared_processdata(self):
        self._require_connected()

        if not self._processdata_prepared:
            self.prepare_processdata()

        self._last_tx_monotonic_ns = time.monotonic_ns()
        self.last_direct_tx_dc_time_ns = self.get_dc_time_ns()
        if self._last_rx_monotonic_ns is not None and self.last_rx_dc_time_ns:
            elapsed_since_rx_ns = self._last_tx_monotonic_ns - self._last_rx_monotonic_ns
            self.last_tx_dc_time_ns = self.last_rx_dc_time_ns + elapsed_since_rx_ns
        else:
            self.last_tx_dc_time_ns = self.last_direct_tx_dc_time_ns
        self.dc_time_ns = self.last_tx_dc_time_ns
        send_start_ns = time.monotonic_ns()
        self._master.send_processdata()
        self.last_send_call_duration_ns = time.monotonic_ns() - send_start_ns
        self._outputs_sent = True
        self._processdata_prepared = False

    def receive_processdata(self, timeout_us=2000):
        self._require_connected()

        self.wkc = self._master.receive_processdata(timeout_us)
        receive_monotonic_ns = time.monotonic_ns()
        self.dc_time_ns = self.get_dc_time_ns()
        self.last_rx_dc_time_ns = self.dc_time_ns
        self._last_rx_monotonic_ns = receive_monotonic_ns
        self._read_inputs()
        self._outputs_sent = False
        return self.wkc

    def get_dc_time_ns(self):
        if self._master is None:
            return self.dc.get_time_ns()
        try:
            value = self._master._get_dc_time()
        except Exception:
            value = self._master.dc_time
        return int(value)

    def estimate_dc_time_ns(self, monotonic_ns=None):
        if self._last_rx_monotonic_ns is None or not self.last_rx_dc_time_ns:
            return self.get_dc_time_ns()

        if monotonic_ns is None:
            monotonic_ns = time.monotonic_ns()
        return int(self.last_rx_dc_time_ns + monotonic_ns - self._last_rx_monotonic_ns)

    def expected_wkc(self):
        if self._master is not None:
            return self._master.expected_wkc

        return self.working_counter.get_expected()

    def _write_outputs(self):
        self.last_csp_output_steps = []
        for index, slave in enumerate(self.slaves):
            payload = self.pdo_codec.encode_rxpdo(slave.rxpdo)
            self._master.slaves[index].output = payload
            if slave.rxpdo.mode_of_operation == 8:
                self._track_output_target_step(index, payload)

    def _track_output_target_step(self, axis_index, encoded_payload):
        decoded = RxPDO()
        self.pdo_codec.decode_rxpdo(encoded_payload, decoded)
        output_target = int(decoded.target_position)
        previous_output_target = self._last_output_target_positions[axis_index]
        self._last_output_target_positions[axis_index] = output_target
        if previous_output_target is None:
            return

        output_step = output_target - previous_output_target
        generator = self.trajectory_generators[axis_index]
        expected_step = float(generator.command_velocity) * self.cycle_time
        step_error = output_step - expected_step
        if (
            (
                self.csp_command_step_threshold > 0.0
                and abs(output_step) >= self.csp_command_step_threshold
            )
            or (
                self.csp_command_step_error_threshold > 0.0
                and abs(step_error) >= self.csp_command_step_error_threshold
            )
        ):
            self.last_csp_output_steps.append(
                {
                    "axis": axis_index,
                    "previous_output_target": previous_output_target,
                    "output_target": output_target,
                    "output_step": output_step,
                    "rxpdo_target": int(self.slaves[axis_index].rxpdo.target_position),
                    "expected_step": expected_step,
                    "step_error": step_error,
                    "command_position": float(generator.command_position),
                    "command_velocity": float(generator.command_velocity),
                    "target_position": float(generator.target_position),
                }
            )

    def _read_inputs(self):
        for index, slave in enumerate(self.slaves):
            payload = self._master.slaves[index].input
            self.pdo_codec.decode_txpdo(payload, slave.txpdo)

    def _request_pre_operational(self, pysoem, timeout_us):
        self._master.state = pysoem.PREOP_STATE
        self._master.write_state()
        reached_state = self._master.state_check(
            pysoem.PREOP_STATE,
            timeout_us,
        )

        if reached_state != pysoem.PREOP_STATE:
            raise RuntimeError(
                "EtherCAT network did not reach PRE_OP before PDO remap. "
                f"Reached={reached_state}. Slaves={self.describe_slaves()}"
            )

        print("EtherCAT network reached PRE_OP before PDO remap", flush=True)

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

    def _configure_distributed_clocks(self):
        if not self.dc_enabled:
            return

        found_dc_slaves = self._master.config_dc()
        print(
            "Configured EtherCAT distributed clocks: "
            f"dc_slaves_found={found_dc_slaves}",
            flush=True,
        )

    def _configure_rxpdo_mapping(self):
        self._write_rxpdo1_mapping(
            RxPDO.MAPPING_ENTRIES,
            "Configured RxPDO1 mapping from Axis Server RxPDO layout",
        )

    def _write_rxpdo1_mapping(self, rxpdo1_mapping, log_message):
        for axis_index in range(self.slave_count):
            self.sdo_write_uint8(axis_index, 0x1600, 0x00, 0)
            for subindex, mapping_entry in enumerate(rxpdo1_mapping, start=1):
                self.sdo_write_uint32(
                    axis_index,
                    0x1600,
                    subindex,
                    mapping_entry,
                )
            self.sdo_write_uint8(
                axis_index,
                0x1600,
                0x00,
                len(rxpdo1_mapping),
            )
            self.slaves[axis_index].rxpdo.select_mapping(rxpdo1_mapping)

        print(log_message, flush=True)

    def _configure_txpdo_mapping(self):
        txpdo1_mapping, log_message = (
            self.device_profile.txpdo_setpoint_mapping()
            if self.txpdo_setpoint_entry
            else self.device_profile.default_txpdo1_mapping()
        )
        self._write_txpdo1_mapping(txpdo1_mapping, log_message)

    def _write_txpdo1_mapping(self, txpdo1_mapping, log_message):
        for axis_index in range(self.slave_count):
            self.sdo_write_uint8(axis_index, 0x1A00, 0x00, 0)
            for subindex, mapping_entry in enumerate(txpdo1_mapping, start=1):
                self.sdo_write_uint32(
                    axis_index,
                    0x1A00,
                    subindex,
                    mapping_entry,
                )
            self.sdo_write_uint8(
                axis_index,
                0x1A00,
                0x00,
                len(txpdo1_mapping),
            )
            self.slaves[axis_index].txpdo.select_mapping(txpdo1_mapping)

        print(log_message, flush=True)

    def _configure_sync_parameters(self):
        if not self.dc_enabled and self.sync_mode == 0:
            print(
                "Using EtherCAT FreeRun sync mode: "
                "DC disabled; skipped drive sync parameter writes",
                flush=True,
            )
            return

        configured = self.device_profile.configure_sync_parameters(
            self,
            self.slave_count,
            self.sync_mode,
            self.cycle_time,
        )
        if not configured:
            return

        print(
            f"Configured {self.device_profile.name.upper()} sync parameters: "
            f"mode={self.sync_mode} cycle_time={self.cycle_time}",
            flush=True,
        )

    def _configure_dc_sync0(self):
        if not self.dc_enabled:
            return

        sync0_cycle_time_ns = int(round(self.cycle_time * 1_000_000_000.0))
        for axis_index in range(self.slave_count):
            self._master.slaves[axis_index].dc_sync(
                True,
                sync0_cycle_time_ns,
                self.dc_sync0_shift_time,
            )

        print(
            "Enabled EtherCAT DC Sync0: "
            f"cycle_time_ns={sync0_cycle_time_ns} "
            f"shift_time_ns={self.dc_sync0_shift_time}",
            flush=True,
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
        self.last_csp_command_steps = []
        for axis_index, (slave, generator) in enumerate(zip(
            self.slaves,
            self.trajectory_generators,
        )):
            if slave.rxpdo.mode_of_operation != 8:
                continue

            limits = slave.motion_limits
            previous_command_position = float(generator.command_position)
            previous_sent_position = int(slave.rxpdo.target_position)
            command_position = float(generator.update(
                self.cycle_time,
                limits.max_velocity * self.csp_counts_per_unit,
                limits.acceleration * self.csp_counts_per_unit,
                limits.deceleration * self.csp_counts_per_unit,
                limits.jerk * self.csp_counts_per_unit,
            ))
            sent_position = int(round(command_position))
            slave.rxpdo.target_position = sent_position
            if self.csp_velocity_offset_enabled:
                velocity_scale = max(self.csp_counts_per_unit, 1e-9)
                slave.rxpdo.velocity_offset = int(round(
                    float(generator.command_velocity) / velocity_scale
                ))
            elif slave.rxpdo.has_field("velocity_offset"):
                slave.rxpdo.velocity_offset = 0
            command_step = command_position - previous_command_position
            sent_step = sent_position - previous_sent_position
            expected_step = float(generator.command_velocity) * self.cycle_time
            step_error = sent_step - expected_step
            if (
                (
                    self.csp_command_step_threshold > 0.0
                    and abs(sent_step) >= self.csp_command_step_threshold
                )
                or (
                    self.csp_command_step_error_threshold > 0.0
                    and abs(step_error) >= self.csp_command_step_error_threshold
                )
            ):
                self.last_csp_command_steps.append(
                    {
                        "axis": axis_index,
                        "previous_command_position": previous_command_position,
                        "command_position": command_position,
                        "command_step": command_step,
                        "previous_sent_position": previous_sent_position,
                        "sent_position": sent_position,
                        "sent_step": sent_step,
                        "expected_step": expected_step,
                        "step_error": step_error,
                        "command_velocity": float(generator.command_velocity),
                        "target_position": float(generator.target_position),
                    }
                )

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
                jerk=0.0,
            )

        limits = motion_limits[index]

        if isinstance(limits, AxisMotionLimits):
            return limits

        return AxisMotionLimits(
            max_velocity=float(limits["max_velocity"]),
            acceleration=float(limits["acceleration"]),
            deceleration=float(limits["deceleration"]),
            jerk=float(limits.get("jerk", 0.0)),
        )
