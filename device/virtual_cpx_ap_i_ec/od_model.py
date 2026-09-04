from device.cpx_ap_i_ec.ap_module_idents import (
    CONFIGURED_MODULE_LIST_INDEX,
    DETECTED_MODULE_LIST_INDEX,
)
from device.cpx_ap_i_ec.isdu_gateway import (
    ISDU_ACCESS_BASE_INDEX,
    resolved_isdu_access_index,
)
from device.cpx_ap_i_ec.module_resolver import (
    expected_module_idents,
    module_display_name,
    module_ident,
    module_info,
)
from device.virtual_device import VirtualOdModel


class VirtualCpxOdModel(VirtualOdModel):
    """ESI/configuration-derived Object Dictionary for a Virtual CPX station."""

    def __init__(self, device_profile):
        super().__init__()
        self.device_profile = device_profile
        self._load_station_catalog(device_profile.esi_catalog.objects)
        self._load_configured_module_catalog(device_profile.config.layout.modules)
        self._load_process_image(device_profile.pdo_configuration)
        self._initialize_identity(device_profile.esi_catalog)
        self._initialize_module_lists(device_profile.config.layout)
        self._initialize_module_identity(device_profile.config.layout.modules)
        self._initialize_normal_status()
        self.last_write_key = None
        self.write_generation = 0

    def _load_station_catalog(self, entries):
        for (index, subindex), entry in entries.items():
            if is_process_image_configuration_object(index):
                continue
            self._define_esi_entry(index, subindex, entry)

    def _load_configured_module_catalog(self, modules):
        for module in modules:
            for obj in module_info(module).objects:
                index = resolved_module_index(
                    obj.index,
                    module.slot,
                    obj.depend_on_slot,
                    module_pdo_index_stride=(
                        self.device_profile.config.module_pdo_index_stride
                    ),
                )
                if obj.subitems:
                    for subitem in obj.subitems:
                        self._define_esi_entry(
                            index,
                            subitem.subindex,
                            subitem,
                        )
                else:
                    self._define_esi_entry(index, 0, obj)

    def _define_esi_entry(self, index, subindex, entry):
        default = (
            entry.default
            if entry.default is not None
            else self.default_value(entry.data_type, entry.bit_size)
        )
        self.define(
            index,
            subindex,
            name=entry.name,
            data_type=entry.data_type,
            bit_size=entry.bit_size,
            access=entry.access,
            default=default,
        )

    def _load_process_image(self, configuration):
        self._define_pdo_direction(
            assignment_index=0x1C12,
            pdo_info=configuration.rxpdo_info,
            objects=configuration.rxpdo_objects(),
            direction="rxpdo",
        )
        self._define_pdo_direction(
            assignment_index=0x1C13,
            pdo_info=configuration.txpdo_info,
            objects=configuration.txpdo_objects(),
            direction="txpdo",
        )

    def _define_pdo_direction(
        self,
        *,
        assignment_index,
        pdo_info,
        objects,
        direction,
    ):
        self.overlay(
            assignment_index,
            0,
            name=f"{direction} assignment count",
            data_type="USINT",
            bit_size=8,
            access="ro",
            default=1,
        )
        self.define(
            assignment_index,
            1,
            name=f"{direction} assigned PDO",
            data_type="UINT",
            bit_size=16,
            access="ro",
            default=pdo_info.index,
        )
        self.define(
            pdo_info.index,
            0,
            name=f"{pdo_info.name} mapping count",
            data_type="USINT",
            bit_size=8,
            access="ro",
            default=len(pdo_info.entries),
        )
        for subindex, mapping_entry in enumerate(
            pdo_info.mapping_entries(),
            start=1,
        ):
            self.define(
                pdo_info.index,
                subindex,
                name=f"{pdo_info.name} mapping {subindex}",
                data_type="UDINT",
                bit_size=32,
                access="ro",
                default=mapping_entry,
            )
        for obj in objects:
            self.define(
                obj.index,
                obj.subindex,
                name=obj.name,
                data_type=obj.data_type,
                bit_size=obj.bit_length,
                access="rw" if direction == "rxpdo" else "ro",
                default=obj.default,
                role=obj.field,
                **{direction: True},
            )

    def _initialize_identity(self, catalog):
        values = {
            0: 4,
            1: catalog.vendor_id,
            2: catalog.product_code,
            3: catalog.revision,
            4: 0,
        }
        for subindex, value in values.items():
            if self.has_entry(0x1018, subindex):
                self.write_internal(0x1018, value, subindex)

    def _initialize_module_lists(self, layout):
        idents = expected_module_idents(layout)
        for index, access in (
            (CONFIGURED_MODULE_LIST_INDEX, "rw"),
            (DETECTED_MODULE_LIST_INDEX, "ro"),
        ):
            self.overlay(
                index,
                0,
                name="Module list count",
                data_type="USINT",
                bit_size=8,
                access=access,
                default=len(idents),
            )
            for subindex, ident in enumerate(idents, start=1):
                self.define(
                    index,
                    subindex,
                    name=f"Module ident {subindex - 1}",
                    data_type="UDINT",
                    bit_size=32,
                    access=access,
                    default=ident,
                )

    def _initialize_module_identity(self, modules):
        for module in modules:
            index = 0x9000 + int(module.slot) * 0x10
            values = {
                1: int(module.slot),
                3: module_display_name(module),
                5: int(self.device_profile.esi_catalog.vendor_id),
                10: module_ident(module),
            }
            for subindex, value in values.items():
                if self.has_entry(index, subindex):
                    self.write_internal(index, value, subindex)

    def _initialize_normal_status(self):
        if self.has_entry(0x1001, 0):
            self.write_internal(0x1001, 0, 0)
        for index in (0x27F0,):
            if self.has_entry(index, 5):
                self.write_internal(index, 0, 5)


def resolved_module_index(
    index,
    slot,
    depend_on_slot,
    *,
    module_pdo_index_stride=0x10,
):
    if not depend_on_slot:
        return int(index)
    if int(index) == ISDU_ACCESS_BASE_INDEX:
        return resolved_isdu_access_index(
            index,
            slot,
            index_stride=module_pdo_index_stride,
        )
    return int(index) + int(slot) * 0x10


def is_process_image_configuration_object(index):
    index = int(index)
    return (
        index in {0x1C12, 0x1C13, 0x6F00, 0x7F00}
        or 0x1710 <= index <= 0x1716
        or 0x1B10 <= index <= 0x1B16
    )
