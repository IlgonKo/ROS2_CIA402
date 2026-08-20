from device.cpx_ap_i_ec.esi_module_catalog import esi_module_catalog
from device.cpx_ap_i_ec.module_resolver import module_info_for_ap_module
from motion_server.api import parse_int, send_client_message


def iol_param_catalog(message, runtime, client):
    response_type = "system/io/iol/param_catalog"
    try:
        require_iol_selector(message)
        device = selected_io_device(runtime, message)
        module_number = selected_module_number(message)
        port_number = selected_port_number(message)
        response = iol_catalog_payload(
            response_type,
            device,
            module_number,
            port_number,
        )
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


def require_iol_selector(message):
    if "module" not in message and "slot" not in message:
        raise ValueError("system/io/iol/param_catalog requires module")
    if "port" not in message:
        raise ValueError("system/io/iol/param_catalog requires port")


def selected_io_device(runtime, message):
    return runtime.device_manager.io.selected_device(io_id=message.get("io"))


def selected_module_number(message):
    return parse_int(message.get("module", message.get("slot")), 0)


def selected_port_number(message):
    return parse_int(message.get("port"), 0)


def iol_catalog_payload(response_type, device, module_number, port_number):
    config = io_config(device)
    info = module_info_for_ap_module(config.layout, module_number)
    if not info.has_isdu_access:
        raise ValueError(
            "Selected AP module does not support IO-Link ISDU access: "
            f"io={device['id']} module={module_number}"
        )

    bindings = [
        binding
        for binding in config.io_link_devices
        if int(binding.module) == int(module_number)
        and int(binding.port) == int(port_number)
    ]
    if not bindings:
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
        "module_name": info.type_name,
        "port": port_number,
        "isdu_access": True,
        "catalog_source": "iodd",
        "validation": "server_rejects_parameters_not_declared_in_iodd",
        "object_index": f"0x{isdu_access_object_index(module_number):04X}",
        "max_data_bytes": 238,
        "direction_values": {
            "read": 0,
            "write": 1,
        },
        "devices": [
            iodd_device_to_dict(binding)
            for binding in bindings
        ],
    }


def io_config(device):
    profile = getattr(device["slave"], "device_profile", None)
    config = getattr(profile, "config", None)
    if config is None:
        raise ValueError(f"I/O device {device['id']} has no CPX configuration")
    return config


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


def isdu_access_object_index(module_number):
    return 0x2001 + int(module_number) * 0x10
