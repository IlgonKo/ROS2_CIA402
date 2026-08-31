from device.cpx_ap_i_ec.esi_module_catalog import esi_module_catalog
from device.cpx_ap_i_ec.isdu_gateway import isdu_access_object_index
from device.cpx_ap_i_ec.module_resolver import module_info_for_ap_module
from motion_server.api import parse_int
from motion_server.failure import (
    InvalidArgumentException,
    ResourceNotFoundException,
    ServerNotReadyException,
    UnsupportedOperationException,
)


def iol_param_catalog(message, runtime, client):
    return iol_param_catalog_data(message, runtime)


def iol_param_catalog_data(message, runtime):
    require_iol_selector(message)
    device = selected_io_device(runtime, message)
    module_number = selected_module_number(message)
    port_number = selected_port_number(message)
    return iol_catalog_payload(device, module_number, port_number)


def require_iol_selector(message):
    if "module" not in message and "slot" not in message:
        raise InvalidArgumentException("module", "is required")
    if "port" not in message:
        raise InvalidArgumentException("port", "is required")


def selected_io_device(runtime, message):
    selector = message.get("io")
    try:
        return runtime.device_manager.io.selected_device(io_id=selector)
    except AttributeError as exc:
        raise ServerNotReadyException("I/O devices are unavailable") from exc
    except (TypeError, ValueError) as exc:
        raise ResourceNotFoundException("io", selector) from exc


def selected_module_number(message):
    return parse_catalog_int("module", message.get("module", message.get("slot")))


def selected_port_number(message):
    return parse_catalog_int("port", message.get("port"))


def parse_catalog_int(field, value):
    try:
        return parse_int(value, 0)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentException(field, "must be an integer") from exc


def iol_catalog_payload(device, module_number, port_number):
    config = io_config(device)
    try:
        info = module_info_for_ap_module(config.layout, module_number)
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        raise ResourceNotFoundException("io_module", module_number) from exc
    if not info.has_isdu_access:
        raise UnsupportedOperationException("io_link_isdu_catalog")

    bindings = [
        binding
        for binding in config.io_link_devices
        if int(binding.module) == int(module_number)
        and int(binding.port) == int(port_number)
    ]
    if not bindings:
        raise ResourceNotFoundException(
            "io_link_port_binding",
            {"io": device["id"], "module": module_number, "port": port_number},
        )

    return {
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
        raise UnsupportedOperationException("io_link_parameter_catalog")
    return config


def iodd_device_to_dict(binding):
    input_bytes, output_bytes = binding.process_data_size
    return {
        "module": binding.module,
        "port": binding.port,
        "key": binding.device.key,
        "path": str(binding.device.path),
        "vendor_id": binding.device.vendor_id,
        "device_id": binding.device.device_id,
        "vendor_name": binding.device.vendor_name,
        "device_name": binding.device.device_name,
        "process_data_profile": binding.process_data_profile.condition_value,
        "process_data_profile_id": binding.process_data_profile.profile_id,
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
