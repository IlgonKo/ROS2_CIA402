from motion_server.api import parse_int, send_client_message


def axis_param_catalog(message, runtime, client):
    response_type = "system/axis/param_catalog"
    try:
        axis_index = parse_int(message.get("axis", 0), 0)
        device = selected_axis_device(runtime, axis_index)
        profile = getattr(device, "device_profile", None)
        catalog = getattr(profile, "esi_catalog", None)
        if catalog is None:
            raise ValueError(
                f"Axis {axis_index} does not expose an ESI parameter catalog"
            )
        response = {
            "type": response_type,
            "ok": True,
            "axis": axis_index,
            "profile": getattr(profile, "name", ""),
            "slave_index": slave_index_for_axis(runtime, axis_index),
            "esi": str(catalog.path),
            "objects": [
                object_to_dict(obj)
                for obj in catalog.root_object_infos()
            ],
        }
    except Exception as exc:
        response = {
            "type": response_type,
            "ok": False,
            "axis": message.get("axis", 0),
            "error": str(exc),
        }
    send_client_message(client, response)


def selected_axis_device(runtime, axis_index):
    axes = runtime.device_manager.axes
    axis_index = int(axis_index)
    if axis_index < 0 or axis_index >= len(axes.devices):
        raise ValueError(f"Invalid axis index: {axis_index}")
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
