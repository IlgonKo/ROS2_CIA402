from device.cpx_ap_i_ec.esi_module_catalog import esi_module_catalog
from motion_server.failure import (
    InvalidArgumentException,
    ResourceNotFoundException,
    ServerNotReadyException,
    UnsupportedOperationException,
)


def ethercat_param_catalog(message, runtime, client):
    return ethercat_param_catalog_data(message, runtime)


def ethercat_param_catalog_data(message, runtime):
    require_no_module_selector(message)
    device = selected_io_device(runtime, message)
    return ethercat_catalog_payload(device)


def require_no_module_selector(message):
    if "module" in message or "slot" in message:
        raise InvalidArgumentException(
            "module",
            "is not used by system/io/ethercat/param_catalog",
        )


def selected_io_device(runtime, message):
    selector = message.get("io")
    try:
        return runtime.device_manager.io.selected_device(io_id=selector)
    except AttributeError as exc:
        raise ServerNotReadyException("I/O devices are unavailable") from exc
    except (TypeError, ValueError) as exc:
        raise ResourceNotFoundException("io", selector) from exc


def ethercat_catalog_payload(device):
    require_device_profile_config(device)
    catalog = esi_module_catalog()
    return {
        "io": device["id"],
        "slave_index": device["slave_index"],
        "esi": str(catalog.path),
        "scope": "station",
        "objects": [
            object_to_dict(obj)
            for obj in root_device_objects(catalog)
        ],
    }


def root_device_objects(catalog):
    return [
        obj
        for (index, subindex), obj in sorted(catalog.objects.items())
        if int(subindex) == 0
    ]


def require_device_profile_config(device):
    profile = getattr(device["slave"], "device_profile", None)
    config = getattr(profile, "config", None)
    if config is None:
        raise UnsupportedOperationException("io_ethercat_parameter_catalog")
    return config


def object_to_dict(obj):
    index = int(obj.index)
    return {
        "index": index,
        "index_hex": f"0x{index:04X}",
        "name": obj.name,
        "data_type": obj.data_type,
        "bit_size": obj.bit_size,
        "access": obj.access,
        "group": object_group(index),
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


def object_group(index):
    index = int(index)
    if index in {0x1008, 0x1009, 0x100A, 0x1018}:
        return "identity"
    if index in {0x1001, 0x10F1, 0x10F3, 0x10F8} or 0x6100 <= index <= 0x61FF:
        return "diagnosis"
    if 0x1600 <= index <= 0x17FF or 0x1A00 <= index <= 0x1BFF:
        return "pdo_mapping"
    if index in {0x1C00} or 0x1C12 <= index <= 0x1C13 or 0x1C32 <= index <= 0x1C33:
        return "sync"
    return "station"
