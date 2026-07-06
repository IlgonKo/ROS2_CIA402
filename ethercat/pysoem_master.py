from dataclasses import dataclass
import os
from pathlib import Path
import struct
import sys
import time

from axis_server.csp_trajectory_generator import CspTrajectoryGenerator
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
        csp_counts_per_unit=1.0,
        sync_mode=None,
        dc_enabled=False,
        dc_sync0_shift_time=0,
        pdo_codec=CiA402PdoCodec,
        txpdo_setpoint_feedback=False,
        configure_txpdo_setpoint_feedback=False,
        txpdo_setpoint_feedback_object="6062",
        restore_default_txpdo_mapping=True,
        csp_velocity_offset_enabled=False,
        csp_command_step_threshold=0.0,
        csp_command_step_error_threshold=0.0,
    ):
        self.interface_name = interface_name
        self.slave_count = slave_count
        self.cycle_time = cycle_time
        self.csp_counts_per_unit = float(csp_counts_per_unit)
        self.sync_mode = sync_mode
        self.dc_enabled = bool(dc_enabled)
        self.dc_sync0_shift_time = int(dc_sync0_shift_time)
        self.pdo_codec = pdo_codec
        self.txpdo_setpoint_feedback = bool(txpdo_setpoint_feedback)
        self.configure_txpdo_setpoint_feedback = bool(
            configure_txpdo_setpoint_feedback
        )
        self.txpdo_setpoint_feedback_object = str(
            txpdo_setpoint_feedback_object
        ).strip()
        self.restore_default_txpdo_mapping = bool(restore_default_txpdo_mapping)
        self.csp_velocity_offset_enabled = bool(csp_velocity_offset_enabled)
        self.csp_command_step_threshold = float(csp_command_step_threshold)
        self.csp_command_step_error_threshold = float(
            csp_command_step_error_threshold
        )
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

        if self.configure_txpdo_setpoint_feedback:
            self._request_pre_operational(pysoem, timeout_us)
            self._configure_setpoint_feedback_pdo_mapping()
        elif self.restore_default_txpdo_mapping:
            self._request_pre_operational(pysoem, timeout_us)
            self._configure_default_txpdo_mapping()
        self._master.config_map()
        self._configure_distributed_clocks()

        if target_state is None:
            target_state = pysoem.OP_STATE

        if target_state == pysoem.OP_STATE:
            self._request_safe_operational(pysoem, timeout_us)
            self._configure_sync_parameters()
            self._configure_dc_sync0()
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
        self._require_connected()
        self._master.slaves[slave_index].sdo_write(
            index,
            subindex,
            struct.pack("<b", int(value)),
        )

    def sdo_write_int32(self, slave_index, index, subindex, value):
        self._require_connected()
        self._master.slaves[slave_index].sdo_write(
            index,
            subindex,
            struct.pack("<i", int(value)),
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

    def sdo_write_float32(self, slave_index, index, subindex, value):
        self._require_connected()
        self._master.slaves[slave_index].sdo_write(
            index,
            subindex,
            struct.pack("<f", float(value)),
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
            if self.txpdo_setpoint_feedback:
                self.pdo_codec.decode_txpdo_with_setpoint(
                    payload,
                    slave.txpdo,
                    self.txpdo_setpoint_feedback_object,
                )
            else:
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

    def _configure_default_txpdo_mapping(self):
        txpdo1_mapping = [
            0x60410010,
            0x60610008,
            0x60640020,
            0x606C0020,
            0x60770010,
            0x00000008,
        ]
        self._write_txpdo1_mapping(
            txpdo1_mapping,
            "Restored TxPDO1 mapping: default CMMT feedback layout",
        )

    def _configure_setpoint_feedback_pdo_mapping(self):
        replacement_mapping = self._txpdo_setpoint_feedback_replacement_mapping()
        if replacement_mapping is not None:
            txpdo1_mapping, setpoint_label = replacement_mapping
            self._write_txpdo1_mapping(
                txpdo1_mapping,
                f"Configured TxPDO1 feedback mapping: {setpoint_label}",
            )
            return

        setpoint_mapping_entry, setpoint_label = self._txpdo_setpoint_feedback_mapping()
        txpdo1_mapping = [
            0x60410010,
            0x60610008,
            0x60640020,
            0x606C0020,
            0x60770010,
            setpoint_mapping_entry,
            0x00000008,
        ]
        self._write_txpdo1_mapping(
            txpdo1_mapping,
            f"Configured TxPDO1 feedback mapping: added {setpoint_label}",
        )

    def _txpdo_setpoint_feedback_replacement_mapping(self):
        feedback_object = self.txpdo_setpoint_feedback_object.lower()
        if feedback_object in (
            "6062_replace_6064",
            "6062-replace-6064",
            "0x6062_replace_0x6064",
        ):
            return (
                [
                    0x60410010,
                    0x60610008,
                    0x60620020,
                    0x606C0020,
                    0x60770010,
                    0x00000008,
                ],
                "replaced 0x6064:00 actual position with 0x6062:00 setpoint position",
            )

        if feedback_object not in (
            "6062_replace_606c",
            "6062-replace-606c",
            "0x6062_replace_0x606c",
        ):
            return None

        return (
            [
                0x60410010,
                0x60610008,
                0x60640020,
                0x60620020,
                0x60770010,
                0x00000008,
            ],
            "replaced 0x606C:00 actual velocity with 0x6062:00 setpoint position",
        )

    def _txpdo_setpoint_feedback_mapping(self):
        feedback_object = self.txpdo_setpoint_feedback_object.lower()
        if feedback_object in ("6062", "606200", "0x6062", "0x6062:00"):
            return 0x60620020, "0x6062:00 setpoint position"
        if feedback_object in ("217a01", "0x217a01", "0x217a:01"):
            return 0x217A0140, "0x217A:01 fine interpolator output position"
        raise ValueError(
            "Unsupported TxPDO setpoint feedback object: "
            f"{self.txpdo_setpoint_feedback_object}. "
            "Supported values: 6062, 217A01, 6062_REPLACE_6064, "
            "6062_REPLACE_606C."
        )

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

        print(log_message, flush=True)

    def _configure_sync_parameters(self):
        if self.sync_mode is None:
            return

        for axis_index in range(self.slave_count):
            self.sdo_write_uint16(axis_index, 0x212E, 0x01, self.sync_mode)
            self.sdo_write_float32(
                axis_index,
                0x212E,
                0x02,
                self.cycle_time,
            )
            self.sdo_write_float32(
                axis_index,
                0x212E,
                0x09,
                self.cycle_time,
            )

        print(
            "Configured CMMT sync parameters via 0x212E: "
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
            else:
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
