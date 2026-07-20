from device.cpx_ap_i_ec.config import load_cpx_config
from device.cpx_ap_i_ec.pdo import CPXRxPDO, CPXTxPDO
from device.cpx_ap_i_ec.pdo_codec import CPXPdoCodec


class CPXApIEcDeviceProfile:
    """Festo CPX-AP-I-EC EtherCAT I/O station profile skeleton."""

    name = "cpx_ap_i_ec"
    is_motion_axis = False
    pdo_codec = CPXPdoCodec

    def __init__(self):
        self.config = load_cpx_config()

    def create_rxpdo(self):
        return CPXRxPDO(self.config)

    def create_txpdo(self):
        return CPXTxPDO(self.config)

    def prepare_process_image(
        self,
        master,
        slave_index,
    ):
        rxpdo = master.slaves[slave_index].rxpdo
        txpdo = master.slaves[slave_index].txpdo
        device_output_bytes = self.process_image_bytes(
            master,
            slave_index,
            0x1C12,
        )
        device_input_bytes = self.process_image_bytes(
            master,
            slave_index,
            0x1C13,
        )

        self.validate_or_resize(
            "RxPDO/output",
            slave_index,
            configured_bytes=self.config.output_bytes,
            device_bytes=device_output_bytes,
            resize=rxpdo.resize,
        )
        self.validate_or_resize(
            "TxPDO/input",
            slave_index,
            configured_bytes=self.config.input_bytes,
            device_bytes=device_input_bytes,
            resize=txpdo.resize,
        )
        print(
            "Slave "
            f"{slave_index}: CPX-AP-I-EC process image "
            f"outputs={rxpdo.mapping_size()} bytes "
            f"inputs={txpdo.mapping_size()} bytes "
            f"DI={self.config.digital_inputs} AI={self.config.analog_inputs} "
            f"DO={self.config.digital_outputs} AO={self.config.analog_outputs}",
            flush=True,
        )

    def process_image_bytes(self, master, slave_index, assignment_index):
        entries = master.read_assigned_pdo_mapping_entries(
            slave_index,
            assignment_index,
        )
        total_bits = sum(int(entry) & 0xFF for entry in entries)
        return (total_bits + 7) // 8

    def validate_or_resize(
        self,
        label,
        slave_index,
        configured_bytes,
        device_bytes,
        resize,
    ):
        configured_bytes = int(configured_bytes)
        device_bytes = int(device_bytes)
        if configured_bytes == 0:
            resize(device_bytes)
            return
        if configured_bytes != device_bytes:
            raise RuntimeError(
                f"CPX {label} size mismatch on slave {slave_index}. "
                f"Configured={configured_bytes} bytes, "
                f"device PDO={device_bytes} bytes. "
                "Check device/cpx_ap_i_ec/.env I/O counts."
            )
        resize(configured_bytes)

    def configure_sync_parameters(
        self,
        master,
        slave_index,
        sync_mode,
        cycle_time,
    ):
        return False
