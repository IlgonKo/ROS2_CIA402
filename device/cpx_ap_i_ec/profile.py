from device.cpx_ap_i_ec.ap_module_idents import configure_ap_module_idents
from device.cpx_ap_i_ec.esi_module_catalog import esi_module_catalog
from device.cpx_ap_i_ec.io_config import load_cpx_io_config
from device.cpx_ap_i_ec.io_link_variants import configure_io_link_variants
from device.cpx_ap_i_ec.pdo import CPXRxPDO, CPXTxPDO
from device.cpx_ap_i_ec.pdo_codec import CPXPdoCodec
from device.cpx_ap_i_ec.pdo_configuration import cpx_pdo_configuration


class CPXApIEcDeviceProfile:
    """Festo CPX-AP-I-EC EtherCAT I/O station profile skeleton."""

    name = "cpx_ap_i_ec"
    is_motion_axis = False
    pdo_codec = CPXPdoCodec

    def __init__(self, io_id=None):
        self.io_id = io_id
        self.esi_catalog = esi_module_catalog()
        self.config = load_cpx_io_config(io_id)
        self.pdo_configuration = cpx_pdo_configuration(self.config)
        self.pdo_configuration.validate_catalog_support(self.esi_catalog)

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
        configure_io_link_variants(master, slave_index, self.config)
        configure_ap_module_idents(master, slave_index, self.config)
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

        self.pdo_configuration.validate_actual_process_image(
            slave_index,
            device_output_bytes,
            device_input_bytes,
        )
        rxpdo.resize(self.pdo_configuration.output_bytes)
        txpdo.resize(self.pdo_configuration.input_bytes)
        print(
            "Slave "
            f"{slave_index}: CPX-AP-I-EC process image "
            f"io_id={self.config.io_id} "
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

    def configure_sync_parameters(
        self,
        master,
        slave_index,
        sync_mode,
        cycle_time,
    ):
        return False
