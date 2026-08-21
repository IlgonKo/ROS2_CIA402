from motion_server.api import parse_int
from motion_server.api.encoder import legacy_status_request_response
from motion_server.failure import (
    InvalidArgumentException,
    ResourceNotFoundException,
    ServerNotReadyException,
    UnsupportedOperationException,
)


def axis_param_catalog(message, runtime, client):
    return legacy_status_request_response(
        message,
        client,
        lambda: axis_param_catalog_data(message, runtime),
    )


def axis_param_catalog_data(message, runtime):
    try:
        axis_index = parse_int(message.get("axis", 0), 0)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentException("axis", "must be an integer") from exc
    device = selected_axis_device(runtime, axis_index)
    profile = getattr(device, "device_profile", None)
    catalog = getattr(profile, "esi_catalog", None)
    if catalog is None:
        raise UnsupportedOperationException("axis_parameter_catalog")
    return {
        "axis": axis_index,
        "profile": getattr(profile, "name", ""),
        "slave_index": slave_index_for_axis(runtime, axis_index),
        "esi": str(catalog.path),
        "objects": [object_to_dict(obj) for obj in catalog.root_object_infos()],
    }


def selected_axis_device(runtime, axis_index):
    try:
        axes = runtime.device_manager.axes
    except AttributeError as exc:
        raise ServerNotReadyException("axis devices are unavailable") from exc
    axis_index = int(axis_index)
    if axis_index < 0 or axis_index >= len(axes.devices):
        raise ResourceNotFoundException("axis", axis_index)
    return axes.devices[axis_index]


def slave_index_for_axis(runtime, axis_index):
    bindings = runtime.device_manager.axes.axis_bindings
    return int(bindings[int(axis_index)].slave_index)


def object_to_dict(obj):
    return {
        "index": int(obj.index),
        "index_hex": f"0x{int(obj.index):04X}",
        "subindex": 0,
        "subindex_hex": "0x00",
        "name": obj.name,
        "data_type": obj.data_type,
        "bit_size": int(obj.bit_size),
        "access": obj.access,
        "subitems": [
            subitem_to_dict(subitem)
            for subitem in getattr(obj, "subitems", ())
        ],
    }


def subitem_to_dict(subitem):
    return {
        "subindex": int(subitem.subindex),
        "subindex_hex": f"0x{int(subitem.subindex):02X}",
        "name": subitem.name,
        "data_type": subitem.data_type,
        "bit_size": int(subitem.bit_size),
        "bit_offset": int(subitem.bit_offset),
        "access": subitem.access,
    }
