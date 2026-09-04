import os
from pathlib import Path
import sys
import time

from ethercat.distributed_clock import DistributedClock
from ethercat.master_pdo_runtime import MasterPdoRuntime
from ethercat.sdo_access import SdoAccess
from ethercat.working_counter import WorkingCounter
from motion_server.failure import (
    CommunicationException,
    CommunicationTimeoutException,
    DeviceRejectedException,
    MotionServerException,
    SdoObjectNotFoundException,
)


AL_STATUS_DESCRIPTIONS = {
    0x001D: "Invalid output configuration",
    0x001E: "Invalid input configuration",
    0x001F: "Invalid watchdog configuration",
}
SDO_OBJECT_NOT_FOUND_ABORT_CODES = frozenset({0x06020000, 0x06090011})
SDO_TIMEOUT_ABORT_CODES = frozenset({0x05040000})
SDO_COMMUNICATION_RETRY_COUNT = 3
SDO_COMMUNICATION_RETRY_DELAY_S = 0.02


class PySOEMMaster:
    def __init__(
        self,
        interface_name,
        *,
        device_profiles,
        cycle_time=0.001,
        sync_mode=None,
        dc_enabled=False,
        dc_sync0_shift_time=0,
    ):
        self.interface_name = interface_name
        self.device_profiles = list(device_profiles)
        if not self.device_profiles:
            raise ValueError("device_profiles requires at least one profile")
        self.slave_count = len(self.device_profiles)
        self.cycle_time = cycle_time
        self.sync_mode = sync_mode
        self.dc_enabled = bool(dc_enabled)
        if not self.dc_enabled and self.sync_mode is not None:
            self.sync_mode = 0
        self.dc_sync0_shift_time = int(dc_sync0_shift_time)
        self.sdo = SdoAccess(self)

        self.dc = DistributedClock()
        self.working_counter = WorkingCounter()
        self.wkc = 0
        self.dc_time_ns = 0
        self.last_tx_dc_time_ns = 0
        self.last_direct_tx_dc_time_ns = 0
        self.last_rx_dc_time_ns = 0
        self.last_rx_monotonic_ns = None
        self.last_tx_monotonic_ns = None
        self.last_tx_prepare_duration_ns = 0
        self.last_send_call_duration_ns = 0
        self._processdata_prepared = False
        self._processdata_sent = False
        self._pysoem = None
        self._master = None
        self._emergency_callbacks = []
        self.emergency_messages = []
        self.sdo_communication_retry_count = SDO_COMMUNICATION_RETRY_COUNT
        self.sdo_communication_retry_delay_s = SDO_COMMUNICATION_RETRY_DELAY_S

        self.slaves = [
            MasterPdoRuntime(device_profile)
            for device_profile in self.device_profiles
        ]

        for _ in self.slaves:
            self.working_counter.add_slave()

    def connect(self, target_state=None, timeout_us=50000, timeout_s=None):
        pysoem = self._load_pysoem()
        self._reset_processdata_state()
        if timeout_s is not None:
            timeout_s = float(timeout_s)
            if timeout_s <= 0.0:
                raise TimeoutError("EtherCAT connect deadline expired")
            timeout_us = max(1000, min(int(timeout_s * 1_000_000), timeout_us))

        try:
            self._master = pysoem.Master()
            self._master.open(self.interface_name)

            discovered_slaves = self._master.config_init()
            if discovered_slaves < self.slave_count:
                raise RuntimeError(
                    f"Expected {self.slave_count} EtherCAT slaves, "
                    f"found {discovered_slaves}."
                )
            self._register_emergency_callbacks()

            self._request_pre_operational(pysoem, timeout_us)
            self._prepare_device_profiles()
            self._master.config_map()
            self._configure_distributed_clocks()

            target_state = self._resolve_target_state(pysoem, target_state)

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
        except Exception:
            try:
                self.close()
            except Exception:
                pass
            raise

    def enter_operational(self, timeout_us=50000, timeout_s=None):
        self._require_connected()
        if timeout_s is not None:
            timeout_s = float(timeout_s)
            if timeout_s <= 0.0:
                raise TimeoutError("EtherCAT operational deadline expired")
            timeout_us = max(1000, min(int(timeout_s * 1_000_000), timeout_us))
        pysoem = self._load_pysoem()
        self._configure_sync_parameters()
        self._configure_dc_sync0()
        self._request_safe_operational(pysoem, timeout_us)
        self._prime_outputs()
        self._request_operational(pysoem, timeout_us)

    def _resolve_target_state(self, pysoem, target_state):
        if target_state is None:
            return pysoem.OP_STATE
        if isinstance(target_state, str):
            states = {
                "init": pysoem.INIT_STATE,
                "preop": pysoem.PREOP_STATE,
                "pre_op": pysoem.PREOP_STATE,
                "safeop": pysoem.SAFEOP_STATE,
                "safe_op": pysoem.SAFEOP_STATE,
                "op": pysoem.OP_STATE,
                "operational": pysoem.OP_STATE,
            }
            normalized = target_state.strip().lower()
            if normalized not in states:
                raise ValueError(f"Unsupported EtherCAT target state: {target_state}")
            return states[normalized]
        return int(target_state)

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
        master = self._master
        self._master = None
        self._reset_processdata_state()
        self._emergency_callbacks = []
        if master is not None:
            master.close()

    def write_sdo(self, slave_index, index, subindex, payload):
        self._require_connected()
        self._with_sdo_communication_retry(
            "sdo_write",
            index,
            subindex,
            lambda: self._master.slaves[slave_index].sdo_write(
                index,
                subindex,
                payload,
            ),
        )

    def read_sdo(self, slave_index, index, subindex, size):
        self._require_connected()
        return self._with_sdo_communication_retry(
            "sdo_read",
            index,
            subindex,
            lambda: self._master.slaves[slave_index].sdo_read(
                index,
                subindex,
                size=size,
            ),
        )

    def _with_sdo_communication_retry(self, operation, index, subindex, action):
        attempts = max(
            1,
            int(getattr(self, "sdo_communication_retry_count", 1)),
        )
        for attempt in range(1, attempts + 1):
            try:
                return action()
            except Exception as exception:
                if not self._is_sdo_communication_exception(exception):
                    self._raise_sdo_exception(exception, operation, index, subindex)
                if attempt >= attempts:
                    self._raise_sdo_exception(exception, operation, index, subindex)
                time.sleep(
                    max(
                        0.0,
                        float(getattr(
                            self,
                            "sdo_communication_retry_delay_s",
                            0.0,
                        )),
                    )
                )
        raise CommunicationException(operation)

    def _raise_sdo_exception(self, exception, operation, index, subindex):
        if isinstance(exception, MotionServerException):
            raise exception
        if isinstance(exception, TimeoutError):
            raise CommunicationTimeoutException(operation) from exception

        sdo_error_type = getattr(self._pysoem, "SdoError", ())
        if isinstance(exception, sdo_error_type):
            abort_code = int(exception.abort_code)
            if abort_code in SDO_OBJECT_NOT_FOUND_ABORT_CODES:
                raise SdoObjectNotFoundException(index, subindex) from exception
            if abort_code in SDO_TIMEOUT_ABORT_CODES:
                raise CommunicationTimeoutException(operation) from exception
            raise DeviceRejectedException(
                operation,
                device_code=abort_code,
            ) from exception

        if self._is_sdo_communication_exception(exception):
            raise CommunicationException(operation) from exception
        if isinstance(exception, (ConnectionError, OSError)):
            raise CommunicationException(operation) from exception
        raise exception

    def _is_sdo_communication_exception(self, exception):
        communication_types = tuple(
            exception_type
            for name in (
                "MailboxError",
                "PacketError",
                "WkcError",
                "NetworkInterfaceNotOpenError",
            )
            if isinstance(
                exception_type := getattr(self._pysoem, name, None),
                type,
            )
        )
        return isinstance(exception, communication_types)

    def _register_emergency_callbacks(self):
        self._emergency_callbacks = []
        self.emergency_messages = []
        for slave_index, slave in enumerate(self._master.slaves):
            if not hasattr(slave, "add_emergency_callback"):
                continue

            def emergency_callback(emergency, slave_index=slave_index):
                self.emergency_messages.append({
                    "slave": slave_index,
                    "message": str(emergency),
                    "repr": repr(emergency),
                })

            slave.add_emergency_callback(emergency_callback)
            self._emergency_callbacks.append(emergency_callback)

    def prepare_processdata(self):
        self._require_connected()
        self._require_processdata_phase("idle", "prepare_processdata")

        prepare_start_ns = time.monotonic_ns()
        try:
            candidates = self._encode_output_candidates()
        except Exception as exception:
            self._raise_processdata_exception(exception, "processdata_prepare")
        for slave, payload in zip(self.slaves, candidates):
            slave.commit_prepared_output(payload)
        self.last_tx_prepare_duration_ns = (
            time.monotonic_ns() - prepare_start_ns
        )
        self._processdata_prepared = True

    def send_processdata(self):
        self._require_connected()

        if self._processdata_sent:
            raise RuntimeError(
                "Call receive_processdata() before sending another PDO cycle."
            )
        if not self._processdata_prepared:
            raise RuntimeError(
                "Call prepare_processdata() before send_processdata()."
            )

        snapshots = [
            slave.transmitted_output_candidate()
            for slave in self.slaves
        ]

        self.last_tx_monotonic_ns = time.monotonic_ns()
        self.last_direct_tx_dc_time_ns = self.get_dc_time_ns()
        self.last_tx_dc_time_ns = self.last_direct_tx_dc_time_ns
        self.dc_time_ns = self.last_tx_dc_time_ns
        send_start_ns = time.monotonic_ns()
        try:
            self._assign_output_snapshots(snapshots)
            self._master.send_processdata()
        except Exception as exception:
            self._raise_processdata_exception(exception, "processdata_send")
        self.last_send_call_duration_ns = time.monotonic_ns() - send_start_ns
        for slave, payload in zip(self.slaves, snapshots):
            slave.commit_transmitted_output(payload)
        self._processdata_prepared = False
        self._processdata_sent = True

    def receive_processdata(self, timeout_us=2000):
        self._require_connected()
        if not self._processdata_sent:
            raise RuntimeError(
                "Call send_processdata() before receive_processdata()."
            )

        try:
            self.wkc = self._master.receive_processdata(timeout_us)
        except Exception as exception:
            self._raise_processdata_exception(exception, "processdata_receive")
        receive_monotonic_ns = time.monotonic_ns()
        self.dc_time_ns = self.get_dc_time_ns()
        self.last_rx_dc_time_ns = self.dc_time_ns
        self.last_rx_monotonic_ns = receive_monotonic_ns
        try:
            payloads = self._validate_input_payloads()
        except Exception as exception:
            self._raise_processdata_exception(exception, "processdata_receive")
        self._decode_inputs(payloads)
        self._processdata_sent = False
        return self.wkc

    def _raise_processdata_exception(self, exception, operation):
        if isinstance(exception, MotionServerException):
            raise exception
        communication_types = tuple(
            exception_type
            for name in (
                "MailboxError",
                "PacketError",
                "WkcError",
                "NetworkInterfaceNotOpenError",
            )
            if isinstance(
                exception_type := getattr(self._pysoem, name, None),
                type,
            )
        )
        if isinstance(
            exception,
            communication_types + (ConnectionError, OSError),
        ):
            raise CommunicationException(operation) from exception
        raise exception

    def get_dc_time_ns(self):
        if self._master is None:
            return self.dc.get_time_ns()
        try:
            value = self._master._get_dc_time()
        except Exception:
            value = self._master.dc_time
        return int(value)

    def expected_wkc(self):
        if self._master is not None:
            return self._master.expected_wkc

        return self.working_counter.get_expected()

    def transport_available(self):
        if self._master is None:
            return False
        try:
            self._master.read_state()
        except Exception:
            return False
        slaves = tuple(self._master.slaves)
        if len(slaves) < self.slave_count:
            return False
        none_state = int(self._load_pysoem().NONE_STATE)
        return all(
            (int(getattr(slave, "state", none_state)) & 0x0F) != none_state
            for slave in slaves[: self.slave_count]
        )

    def _encode_output_candidates(self):
        return [slave.encode_output_candidate() for slave in self.slaves]

    def _assign_output_snapshots(self, snapshots):
        for index, payload in enumerate(snapshots):
            if payload is not None:
                self._master.slaves[index].output = payload

    def _validate_input_payloads(self):
        return [
            slave.validate_input_payload(self._master.slaves[index].input)
            for index, slave in enumerate(self.slaves)
        ]

    def _decode_inputs(self, payloads):
        for slave, payload in zip(self.slaves, payloads):
            slave.decode_input(payload)

    def _request_pre_operational(self, pysoem, timeout_us):
        self._master.state = pysoem.PREOP_STATE
        self._master.write_state()
        reached_state = self._master.state_check(
            pysoem.PREOP_STATE,
            timeout_us,
        )

        if reached_state != pysoem.PREOP_STATE:
            raise RuntimeError(
                "EtherCAT network did not reach PRE_OP before process image preparation. "
                f"Reached={reached_state}. Slaves={self.describe_slaves()}"
            )

        print(
            "EtherCAT network reached PRE_OP before process image preparation",
            flush=True,
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

    def _configure_distributed_clocks(self):
        if not self.dc_enabled:
            return

        found_dc_slaves = self._master.config_dc()
        print(
            "Configured EtherCAT distributed clocks: "
            f"dc_slaves_found={found_dc_slaves}",
            flush=True,
        )

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
        assigned_pdos = self.read_assigned_pdo_indices(
            slave_index,
            assignment_index,
        )
        for pdo_index in assigned_pdos:
            entries.extend(self.read_pdo_mapping_entries(slave_index, pdo_index))
        return entries

    def read_slave_identity(self, slave_index):
        self._require_connected()
        slave = self._master.slaves[slave_index]
        identity = {
            "vendor_id": self._first_slave_attr_int(
                slave,
                ("man", "manufacturer", "manufacturer_id"),
            ),
            "product_code": self._first_slave_attr_int(
                slave,
                ("id", "product_code"),
            ),
            "revision": self._first_slave_attr_int(
                slave,
                ("rev", "revision", "revision_number"),
            ),
            "serial_number": self._first_slave_attr_int(
                slave,
                ("serial", "serial_number"),
            ),
        }

        sdo_items = [
            ("vendor_id", 0x01),
            ("product_code", 0x02),
            ("revision", 0x03),
            ("serial_number", 0x04),
        ]
        for key, subindex in sdo_items:
            if not self._identity_value_requires_sdo_fallback(key, identity[key]):
                continue
            try:
                identity[key] = self.sdo.read_uint32(
                    slave_index,
                    0x1018,
                    subindex,
                )
            except Exception:
                pass
        return identity

    @staticmethod
    def _identity_value_requires_sdo_fallback(key, value):
        if value is None:
            return True
        if key in {"vendor_id", "product_code", "revision"}:
            try:
                return int(value) == 0
            except (TypeError, ValueError):
                return True
        return False

    @staticmethod
    def _first_slave_attr_int(slave, names):
        for name in names:
            value = PySOEMMaster._slave_attr_int(slave, name)
            if value is not None:
                return value
        return None

    @staticmethod
    def _slave_attr_int(slave, name):
        value = getattr(slave, name, None)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _configure_sync_parameters(self):
        if not self.dc_enabled and self.sync_mode == 0:
            print(
                "Using EtherCAT FreeRun sync mode: "
                "DC disabled; skipped drive sync parameter writes",
                flush=True,
            )
            return

        for slave_index, slave in enumerate(self.slaves):
            configured = slave.device_profile.configure_sync_parameters(
                self,
                slave_index,
                self.sync_mode,
                self.cycle_time,
            )
            if configured:
                print(
                    f"Configured slave {slave_index} "
                    f"{slave.device_profile.name.upper()} sync parameters: "
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
        snapshots = self._encode_output_candidates()
        self._assign_output_snapshots(snapshots)

        for _ in range(10):
            self._master.send_processdata()
            self._master.receive_processdata(2000)
        for slave, payload in zip(self.slaves, snapshots):
            slave.commit_transmitted_output(payload)

    def _request_operational(self, pysoem, timeout_us):
        self._master.state = pysoem.OP_STATE
        self._master.write_state()

        reached_state = pysoem.NONE_STATE
        for _ in range(100):
            snapshots = self._encode_output_candidates()
            self._assign_output_snapshots(snapshots)
            self._master.send_processdata()
            for slave, payload in zip(self.slaves, snapshots):
                slave.commit_transmitted_output(payload)
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

    def _require_connected(self):
        if self._master is None:
            raise CommunicationException("bus_transport_disconnected")

    def _reset_processdata_state(self):
        self._processdata_prepared = False
        self._processdata_sent = False
        self.wkc = 0
        self.dc_time_ns = 0
        self.last_tx_dc_time_ns = 0
        self.last_direct_tx_dc_time_ns = 0
        self.last_rx_dc_time_ns = 0
        self.last_rx_monotonic_ns = None
        self.last_tx_monotonic_ns = None
        self.last_tx_prepare_duration_ns = 0
        self.last_send_call_duration_ns = 0
        for slave in self.slaves:
            slave.reset_processdata()

    def _require_processdata_phase(self, expected, operation):
        phase = (
            "sent" if self._processdata_sent
            else "prepared" if self._processdata_prepared
            else "idle"
        )
        if phase != expected:
            raise RuntimeError(
                f"Cannot {operation} while PDO cycle phase is {phase}. "
                "Expected prepare -> send -> receive."
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
