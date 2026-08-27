from dataclasses import dataclass

from device.cpx_ap_i_ec.esi_module_catalog import esi_module_catalog
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

RXPDO_INDEXES = tuple(range(0x1710, 0x1717))
TXPDO_INDEXES = tuple(range(0x1B10, 0x1B17))


@dataclass(frozen=True)
class CPXPdoBlock:
    index: int
    subindex: int
    name: str
    field: str
    byte_length: int = 16
    data_type: str = "byte_array"
    default: bytes = bytes(16)

    @property
    def bit_length(self):
        return self.byte_length * 8

    def mapping_entry(self):
        return (
            (int(self.index) << 16)
            | (int(self.subindex) << 8)
            | self.bit_length
        )


@dataclass(frozen=True)
class CPXPdoConfiguration:
    name: str
    config: object

    @property
    def output_bytes(self):
        return self.rxpdo_info.byte_size

    @property
    def input_bytes(self):
        return self.txpdo_info.byte_size

    @property
    def rxpdo_info(self):
        return selected_fixed_pdo(
            esi_module_catalog().rxpdos,
            RXPDO_INDEXES,
            self.config.output_bytes,
            "RxPDO/output",
        )

    @property
    def txpdo_info(self):
        return selected_fixed_pdo(
            esi_module_catalog().txpdos,
            TXPDO_INDEXES,
            self.config.input_bytes,
            "TxPDO/input",
        )

    def rxpdo_mapping_entries(self):
        return self.rxpdo_info.mapping_entries()

    def txpdo_mapping_entries(self):
        return self.txpdo_info.mapping_entries()

    def rxpdo_objects(self):
        return pdo_blocks(self.rxpdo_info, "output")

    def txpdo_objects(self):
        return pdo_blocks(self.txpdo_info, "input")

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


def selected_fixed_pdo(catalog, indexes, required_bytes, label):
    required_bytes = max(1, int(required_bytes))
    candidates = [catalog[index] for index in indexes if index in catalog]
    for candidate in sorted(candidates, key=lambda item: item.byte_size):
        if candidate.byte_size >= required_bytes:
            return candidate
    maximum = max((item.byte_size for item in candidates), default=0)
    raise ValueError(
        f"CPX {label} requires {required_bytes} bytes; "
        f"maximum fixed process image is {maximum} bytes."
    )


def pdo_blocks(pdo_info, direction):
    blocks = []
    for entry in pdo_info.entries:
        if entry.index == 0:
            continue
        blocks.append(CPXPdoBlock(
            index=entry.index,
            subindex=entry.subindex,
            name=entry.name,
            field=f"{direction}_block_{entry.subindex}",
            byte_length=(int(entry.bit_length) + 7) // 8,
            default=bytes((int(entry.bit_length) + 7) // 8),
        ))
    return blocks


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
