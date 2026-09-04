from device.cpx_ap_i_ec.ap_module_idents import configure_ap_module_idents
from device.cpx_ap_i_ec.esi_module_catalog import esi_module_catalog
from device.cpx_ap_i_ec.io_config import build_cpx_io_config
from device.cpx_ap_i_ec.io_link_variants import configure_io_link_variants
from device.cpx_ap_i_ec.pdo import CPXRxPDO, CPXTxPDO
from device.cpx_ap_i_ec.pdo_codec import CPXPdoCodec
from device.cpx_ap_i_ec.pdo_configuration import cpx_pdo_configuration
from device.exceptions import (
    DeviceIdentityMismatchException,
    DeviceLayoutInvalidException,
    PdoCatalogMismatchException,
)


class CPXApIEcDeviceProfile:
    """Festo CPX-AP-I-EC EtherCAT I/O station profile skeleton."""

    name = "cpx_ap_i_ec"
    is_motion_axis = False
    pdo_codec = CPXPdoCodec
    capabilities = frozenset()

    def __init__(self, io_id=None, device_config=None):
        if device_config is not None:
            io_id = device_config.logical_id
        self.io_id = io_id
        self.esi_catalog = esi_module_catalog()
        if device_config is None:
            raise TypeError("CPX-AP-I-EC profile requires typed device_config")
        raw_modules = ",".join(
            f"{module.slot}:{module.module_type}"
            for module in device_config.modules
        )
        raw_ports = ",".join(
            port.to_declaration()
            for port in device_config.io_link_ports
        )
        try:
            self.config = build_cpx_io_config(
                io_id,
                raw_modules,
                raw_ports,
                module_pdo_index_stride=(
                    getattr(device_config, "module_pdo_index_stride", 1)
                ),
            )
        except (TypeError, ValueError) as exc:
            raise DeviceLayoutInvalidException() from exc
        self.pdo_configuration = cpx_pdo_configuration(self.config)
        try:
            self.pdo_configuration.validate_catalog_support(self.esi_catalog)
        except (KeyError, RuntimeError, TypeError, ValueError) as exc:
            raise PdoCatalogMismatchException() from exc

    def create_rxpdo(self):
        return CPXRxPDO(
            self.config,
            mapping_bytes=self.pdo_configuration.output_bytes,
        )

    def create_txpdo(self):
        return CPXTxPDO(
            self.config,
            mapping_bytes=self.pdo_configuration.input_bytes,
        )

    def prepare_process_image(
        self,
        master,
        slave_index,
    ):
        self.validate_identity(master, slave_index)
        rxpdo = master.slaves[slave_index].rxpdo
        txpdo = master.slaves[slave_index].txpdo
        configure_io_link_variants(master, slave_index, self.config)
        configure_ap_module_idents(master, slave_index, self.config)
        output_entries = master.read_assigned_pdo_mapping_entries(
            slave_index,
            0x1C12,
        )
        input_entries = master.read_assigned_pdo_mapping_entries(
            slave_index,
            0x1C13,
        )

        device_output_bytes, device_input_bytes = (
            self.pdo_configuration.validate_actual_process_image(
                slave_index,
                output_entries,
                input_entries,
            )
        )
        rxpdo.resize(device_output_bytes)
        txpdo.resize(device_input_bytes)
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

    def validate_identity(self, master, slave_index):
        identity = master.read_slave_identity(slave_index)
        actual_vendor_id = identity.get("vendor_id")
        actual_product_code = identity.get("product_code")
        expected_vendor_id = int(self.esi_catalog.vendor_id)
        expected_product_code = int(self.esi_catalog.product_code)
        if actual_vendor_id is None or actual_product_code is None:
            raise DeviceIdentityMismatchException(
                "CPX-AP-I-EC identity read failed on slave "
                f"{slave_index}. Could not read vendor/product code from "
                "EtherCAT identity object."
            )
        if (
            int(actual_vendor_id) != expected_vendor_id
            or int(actual_product_code) != expected_product_code
        ):
            raise DeviceIdentityMismatchException(
                f"CPX-AP-I-EC profile mismatch on slave {slave_index}. "
                f"Configured={self.name} "
                f"(vendor_id={expected_vendor_id}/0x{expected_vendor_id:08X}, "
                f"product_code={expected_product_code}/"
                f"0x{expected_product_code:08X}) "
                f"Actual vendor_id={int(actual_vendor_id)}/"
                f"0x{int(actual_vendor_id):08X}, "
                f"product_code={int(actual_product_code)}/"
                f"0x{int(actual_product_code):08X}. "
                "Check MOTION_SERVER_BUS and the connected EtherCAT slave."
            )

    def configure_sync_parameters(
        self,
        master,
        slave_index,
        sync_mode,
        cycle_time,
    ):
        return False
