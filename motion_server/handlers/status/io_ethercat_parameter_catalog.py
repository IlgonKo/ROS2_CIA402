from device.cpx_ap_i_ec.esi_module_catalog import esi_module_catalog
from device.cpx_ap_i_ec.module_resolver import module_info_for_ap_module
from motion_server.api import parse_int
from motion_server.failure import (
    InvalidArgumentException,
    ResourceNotFoundException,
    ServerNotReadyException,
    UnsupportedOperationException,
)


def ethercat_param_catalog(message, runtime, client):
    return ethercat_param_catalog_data(message, runtime)


def ethercat_param_catalog_data(message, runtime):
    device = selected_io_device(runtime, message)
    module_number = selected_module_number(message)
    return ethercat_catalog_payload(device, module_number)


def selected_io_device(runtime, message):
    selector = message.get("io")
    try:
        return runtime.device_manager.io.selected_device(io_id=selector)
    except AttributeError as exc:
        raise ServerNotReadyException("I/O devices are unavailable") from exc
    except (TypeError, ValueError) as exc:
        raise ResourceNotFoundException("io", selector) from exc


def selected_module_number(message):
    if "module" not in message and "slot" not in message:
        return None
    value = message.get("module", message.get("slot"))
    try:
        return parse_int(value, 0)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentException("module", "must be an integer") from exc


def ethercat_catalog_payload(device, module_number):
    config = io_config(device)
    module_infos = selected_module_infos(config, module_number)
    return {
        "io": device["id"],
        "slave_index": device["slave_index"],
        "esi": str(esi_module_catalog().path),
        "module": module_number,
        "objects": [
            object_to_dict(obj, module_number=module_no)
            for module_no, info in module_infos
            for obj in info.objects
        ],
    }


def selected_module_infos(config, module_number):
    if module_number is not None:
        try:
            info = module_info_for_ap_module(config.layout, module_number)
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            raise ResourceNotFoundException("io_module", module_number) from exc
        return [(module_number, info)]

    infos = [(0, module_info_for_ap_module(config.layout, 0))]
    infos.extend(
        (module.slot, module_info_for_ap_module(config.layout, module.slot))
        for module in config.layout.modules
    )
    return infos


def io_config(device):
    profile = getattr(device["slave"], "device_profile", None)
    config = getattr(profile, "config", None)
    if config is None:
        raise UnsupportedOperationException("io_ethercat_parameter_catalog")
    return config


def object_to_dict(obj, module_number):
    index = resolved_object_index(obj.index, module_number, obj.depend_on_slot)
    return {
        "module": module_number,
        "index": index,
        "index_hex": f"0x{index:04X}",
        "name": obj.name,
        "data_type": obj.data_type,
        "bit_size": obj.bit_size,
        "access": obj.access,
        "depend_on_slot": obj.depend_on_slot,
        "subitems": [
            subitem_to_dict(subitem)
            for subitem in obj.subitems
        ],
    }


def subitem_to_dict(subitem):
    return {
        "subindex": subitem.subindex,
        "name": subitem.name,
        "data_type": subitem.data_type,
        "bit_size": subitem.bit_size,
        "bit_offset": subitem.bit_offset,
        "access": subitem.access,
    }


def resolved_object_index(index, module_number, depend_on_slot):
    if not depend_on_slot or module_number is None:
        return int(index)
    return int(index) + int(module_number) * 0x10
