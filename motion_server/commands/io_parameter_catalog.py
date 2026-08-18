from device.cpx_ap_i_ec.esi_module_catalog import esi_module_catalog
from device.cpx_ap_i_ec.module_resolver import (
    module_info_for_ap_module,
)
from motion_server.api import parse_int, send_client_message


def ethercat_param_catalog(message, runtime, client):
    response_type = "system/io/ethercat/param_catalog"
    send_catalog_response(
        client,
        response_type,
        message,
        runtime,
        lambda device, module_number, _port_number: ethercat_catalog_payload(
            response_type,
            device,
            module_number,
        ),
    )


def iol_param_catalog(message, runtime, client):
    response_type = "system/io/iol/param_catalog"
    send_catalog_response(
        client,
        response_type,
        message,
        runtime,
        lambda device, module_number, port_number: iol_catalog_payload(
            response_type,
            device,
            module_number,
            port_number,
        ),
    )


def require_iol_selector(message):
    if "module" not in message and "slot" not in message:
        raise ValueError("system/io/iol/param_catalog requires module")
    if "port" not in message:
        raise ValueError("system/io/iol/param_catalog requires port")


def send_catalog_response(client, response_type, message, runtime, payload_factory):
    try:
        if response_type == "system/io/iol/param_catalog":
            require_iol_selector(message)
        device = selected_io_device(runtime, message)
        module_number = selected_module_number(message)
        port_number = selected_port_number(message)
        response = payload_factory(device, module_number, port_number)
        response["ok"] = True
    except Exception as exc:
        response = {
            "type": response_type,
            "ok": False,
            "io": message.get("io"),
            "module": message.get("module"),
            "port": message.get("port"),
            "error": str(exc),
        }
    send_client_message(client, response)


def selected_io_device(runtime, message):
    return runtime.device_manager.io.selected_device(io_id=message.get("io"))


def selected_module_number(message):
    if "module" not in message and "slot" not in message:
        return None
    return parse_int(message.get("module", message.get("slot")), 0)


def selected_port_number(message):
    if "port" not in message:
        return None
    return parse_int(message.get("port"), 0)


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


def iol_catalog_payload(response_type, device, module_number, port_number):
    config = io_config(device)
    module_infos = selected_module_infos(config, module_number)
    modules = []
    for module_no, info in module_infos:
        if not info.has_isdu_access:
            continue
        modules.append({
            "module": module_no,
            "module_name": info.type_name,
            "isdu_access": True,
            "catalog_source": "iodd",
            "validation": "server_rejects_parameters_not_declared_in_iodd",
            "object_index": f"0x{isdu_access_object_index(module_no):04X}",
            "ports": 4,
            "max_data_bytes": 238,
            "direction_values": {
                "read": 0,
                "write": 1,
            },
            "devices": [
                iodd_device_to_dict(binding)
                for binding in config.io_link_devices
                if int(binding.module) == int(module_no)
                and (
                    port_number is None
                    or int(binding.port) == int(port_number)
                )
            ],
        })
    if not any(module["devices"] for module in modules):
        raise ValueError(
            "No IODD device binding for IO-Link parameter catalog: "
            f"io={device['id']} "
            f"module={module_number} "
            f"port={port_number}. "
            "Configure MOTION_SERVER_IO_<io>_IOL_PORTS for this port."
        )
    return {
        "type": response_type,
        "io": device["id"],
        "slave_index": device["slave_index"],
        "esi": str(esi_module_catalog().path),
        "module": module_number,
        "port": port_number,
        "modules": modules,
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


def iodd_device_to_dict(binding):
    input_bytes, output_bytes = binding.device.process_data_size
    return {
        "module": binding.module,
        "port": binding.port,
        "key": binding.device.key,
        "path": str(binding.device.path),
        "vendor_id": binding.device.vendor_id,
        "device_id": binding.device.device_id,
        "vendor_name": binding.device.vendor_name,
        "device_name": binding.device.device_name,
        "input_bytes": input_bytes,
        "output_bytes": output_bytes,
        "variables": [
            iodd_variable_to_dict(variable)
            for variable in binding.device.variables
        ],
    }


def iodd_variable_to_dict(variable):
    return {
        "id": variable.variable_id,
        "index": variable.index,
        "index_hex": f"0x{variable.index:04X}",
        "access": variable.access,
        "data_type": variable.data_type,
        "bit_length": variable.bit_length,
        "name": variable.name,
        "subindices": list(variable.subindices),
    }


def resolved_object_index(index, module_number, depend_on_slot):
    if not depend_on_slot or module_number is None:
        return int(index)
    return int(index) + int(module_number) * 0x10


def isdu_access_object_index(module_number):
    return 0x2001 + int(module_number) * 0x10
