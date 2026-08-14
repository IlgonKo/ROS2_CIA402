from device.cpx_ap_i_ec.ap_parameter_access import write_ap_uint32_parameter
from device.cpx_ap_i_ec.module_catalog import (
    module_display_name,
    module_ident,
)
from device.cpx_ap_i_ec.module_layout import IoLinkModuleSpec


VARIANT_SWITCHING_PARAMETER_ID = 20090
VARIANT_SWITCHING_INSTANCE = 0


def configure_io_link_variants(master, slave_index, config):
    for module in config.layout.modules:
        if not isinstance(module.spec, IoLinkModuleSpec):
            continue
        ident = module_ident(module)
        write_ap_uint32_parameter(
            master,
            slave_index,
            module=module.slot,
            parameter_id=VARIANT_SWITCHING_PARAMETER_ID,
            instance=VARIANT_SWITCHING_INSTANCE,
            value=ident,
        )
        print(
            "Slave "
            f"{slave_index}: CPX-AP-I-EC IO-Link variant configured "
            f"io_id={config.io_id} module={module.slot} "
            f"name={module_display_name(module)} "
            f"variant=0x{ident:08X}/{ident}",
            flush=True,
        )
