from device.cpx_ap_i_ec.esi_module_catalog import esi_module_catalog
from device.cpx_ap_i_ec.module_resolver import module_info_for_ap_module
from motion_server.api import parse_int, send_client_message


def ethercat_param_catalog(message, runtime, client):
    response_type = "system/io/ethercat/param_catalog"
    try:
        device = selected_io_device(runtime, message)
        module_number = selected_module_number(message)
        response = ethercat_catalog_payload(
            response_type,
            device,
            module_number,
        )
        response["ok"] = True
    except Exception as exc:
        response = {
            "type": response_type,
            "ok": False,
            "io": message.get("io"),
            "module": message.get("module"),
            "error": str(exc),
        }
    send_client_message(client, response)


def selected_io_device(runtime, message):
    return runtime.device_manager.io.selected_device(io_id=message.get("io"))


def selected_module_number(message):
    if "module" not in message and "slot" not in message:
        return None
    return parse_int(message.get("module", message.get("slot")), 0)


def ethercat_catalog_payload(response_type, device, module_number):
    config = io_config(device)
    module_infos = selected_module_infos(config, module_number)
    return {
        "type": response_type,
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
        return [(module_number, module_info_for_ap_module(config.layout, module_number))]

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
        raise ValueError(f"I/O device {device['id']} has no CPX configuration")
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
