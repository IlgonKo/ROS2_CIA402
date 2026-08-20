from dataclasses import dataclass

from device.cpx_ap_i_ec.module_resolver import (
    module_info,
    validate_layout_against_esi,
)


REQUIRED_STATION_OD = (
    (0x1001, 0x00, "error_register"),
    (0x1018, 0x01, "identity_vendor_id"),
    (0x1018, 0x02, "identity_product_code"),
    (0x1018, 0x03, "identity_revision"),
    (0x1018, 0x04, "identity_serial_number"),
    (0x1C12, 0x00, "rxpdo_assignment"),
    (0x1C13, 0x00, "txpdo_assignment"),
    (0x27F0, 0x01, "ap_parameter_access_direction"),
    (0x27F0, 0x02, "ap_parameter_access_module"),
    (0x27F0, 0x03, "ap_parameter_access_parameter_id"),
    (0x27F0, 0x04, "ap_parameter_access_instance"),
    (0x27F0, 0x05, "ap_parameter_access_status"),
    (0x27F0, 0x06, "ap_parameter_access_length"),
    (0x27F0, 0x07, "ap_parameter_access_data"),
    (0xF030, 0x00, "configured_module_list"),
    (0xF050, 0x00, "detected_module_list"),
)


@dataclass(frozen=True)
class CPXPdoConfiguration:
    name: str
    config: object

    @property
    def output_bytes(self):
        return int(self.config.output_bytes)

    @property
    def input_bytes(self):
        return int(self.config.input_bytes)

    def validate_catalog_support(self, esi_catalog):
        validate_required_station_od(esi_catalog)
        validate_layout_against_esi(self.config.layout)
        validate_io_link_required_od(self.config.layout)

    def validate_actual_process_image(self, slave_index, output_bytes, input_bytes):
        validate_process_image_size(
            "RxPDO/output",
            slave_index,
            configured_bytes=self.output_bytes,
            device_bytes=output_bytes,
            io_id=self.config.io_id,
        )
        validate_process_image_size(
            "TxPDO/input",
            slave_index,
            configured_bytes=self.input_bytes,
            device_bytes=input_bytes,
            io_id=self.config.io_id,
        )


def cpx_pdo_configuration(config):
    return CPXPdoConfiguration("cpx_ap_i_ec_fixed_process_image", config)


def validate_required_station_od(esi_catalog):
    for index, subindex, role in REQUIRED_STATION_OD:
        try:
            esi_catalog.object_info(index, subindex)
        except KeyError as exc:
            raise RuntimeError(
                "CPX-AP-I-EC required OD missing from ESI. "
                f"role={role} object=0x{index:04X}:{subindex:02X} "
                f"esi={esi_catalog.path.name}"
            ) from exc


def validate_io_link_required_od(layout):
    for module in layout.modules:
        if module.module_type != "iol":
            continue
        if module_object_info(module, 0x2001, 0x01) is None:
            raise RuntimeError(
                "CPX-AP-I-EC IO-Link module has no ISDU access object in ESI. "
                f"slot={module.slot} module={module.raw!r}"
            )


def module_object_info(module, index, subindex):
    catalog = module_info(module)
    for obj in catalog.objects:
        if int(obj.index) != int(index):
            continue
        if int(subindex) == 0:
            return obj
        for subitem in obj.subitems:
            if int(subitem.subindex) == int(subindex):
                return subitem
    return None


def validate_process_image_size(
    label,
    slave_index,
    configured_bytes,
    device_bytes,
    io_id,
):
    configured_bytes = int(configured_bytes)
    device_bytes = int(device_bytes)
    if configured_bytes != device_bytes:
        raise RuntimeError(
            f"CPX {label} size mismatch on slave {slave_index}. "
            f"Configured={configured_bytes} bytes, "
            f"device PDO={device_bytes} bytes. "
            f"Check MOTION_SERVER_IO_{io_id}_MODULES."
        )
