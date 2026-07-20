import os
from pathlib import Path
import sys
import time

from ethercat.distributed_clock import DistributedClock
from ethercat.sdo_access import SdoAccess
from ethercat.working_counter import WorkingCounter


AL_STATUS_DESCRIPTIONS = {
    0x001D: "Invalid output configuration",
    0x001E: "Invalid input configuration",
    0x001F: "Invalid watchdog configuration",
}


class PySOEMPdoSlave:
    def __init__(self, device_profile):
        self.device_profile = device_profile
        self.rxpdo = device_profile.create_rxpdo()
        self.txpdo = device_profile.create_txpdo()
        self.pdo_codec = device_profile.pdo_codec


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
        self._pysoem = None
        self._master = None

        self.slaves = [
            PySOEMPdoSlave(device_profile)
            for device_profile in self.device_profiles
        ]

        for _ in self.slaves:
            self.working_counter.add_slave()

    def connect(self, target_state=None, timeout_us=50000):
        pysoem = self._load_pysoem()
        self._reset_processdata_state()

        try:
            self._master = pysoem.Master()
            self._master.open(self.interface_name)

            discovered_slaves = self._master.config_init()
            if discovered_slaves < self.slave_count:
                raise RuntimeError(
                    f"Expected {self.slave_count} EtherCAT slaves, "
                    f"found {discovered_slaves}."
                )

            self._request_pre_operational(pysoem, timeout_us)
            self._prepare_device_profiles()
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
        except Exception:
            try:
                self.close()
            except Exception:
                pass
            raise

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
        if master is not None:
            master.close()

    def write_sdo(self, slave_index, index, subindex, payload):
        self._require_connected()
        self._master.slaves[slave_index].sdo_write(index, subindex, payload)

    def read_sdo(self, slave_index, index, subindex, size):
        self._require_connected()
        return self._master.slaves[slave_index].sdo_read(
            index, subindex, size=size
        )

    def prepare_processdata(self):
        self._require_connected()

        prepare_start_ns = time.monotonic_ns()
        self._write_outputs()
        self.last_tx_prepare_duration_ns = (
            time.monotonic_ns() - prepare_start_ns
        )
        self._processdata_prepared = True

    def send_processdata(self):
        self._require_connected()

        if not self._processdata_prepared:
            raise RuntimeError(
                "Call prepare_processdata() before send_processdata()."
            )

        self.last_tx_monotonic_ns = time.monotonic_ns()
        self.last_direct_tx_dc_time_ns = self.get_dc_time_ns()
        self.last_tx_dc_time_ns = self.last_direct_tx_dc_time_ns
        self.dc_time_ns = self.last_tx_dc_time_ns
        send_start_ns = time.monotonic_ns()
        self._master.send_processdata()
        self.last_send_call_duration_ns = time.monotonic_ns() - send_start_ns
        self._processdata_prepared = False

    def receive_processdata(self, timeout_us=2000):
        self._require_connected()

        self.wkc = self._master.receive_processdata(timeout_us)
        receive_monotonic_ns = time.monotonic_ns()
        self.dc_time_ns = self.get_dc_time_ns()
        self.last_rx_dc_time_ns = self.dc_time_ns
        self.last_rx_monotonic_ns = receive_monotonic_ns
        self._read_inputs()
        return self.wkc

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

    def _write_outputs(self):
        for index, slave in enumerate(self.slaves):
            payload = slave.pdo_codec.encode_rxpdo(slave.rxpdo)
            if payload is None:
                continue
            self._master.slaves[index].output = payload

    def _read_inputs(self):
        for index, slave in enumerate(self.slaves):
            payload = self._master.slaves[index].input
            slave.pdo_codec.decode_txpdo(payload, slave.txpdo)

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
        self._write_outputs()

        for _ in range(10):
            self._master.send_processdata()
            self._master.receive_processdata(2000)

    def _request_operational(self, pysoem, timeout_us):
        self._master.state = pysoem.OP_STATE
        self._master.write_state()

        reached_state = pysoem.NONE_STATE
        for _ in range(100):
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

    def _require_connected(self):
        if self._master is None:
            raise RuntimeError(
                "PySOEMMaster is not connected. Call connect() first."
            )

    def _reset_processdata_state(self):
        self._processdata_prepared = False
        self.wkc = 0
        self.dc_time_ns = 0
        self.last_tx_dc_time_ns = 0
        self.last_direct_tx_dc_time_ns = 0
        self.last_rx_dc_time_ns = 0
        self.last_rx_monotonic_ns = None
        self.last_tx_monotonic_ns = None

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
