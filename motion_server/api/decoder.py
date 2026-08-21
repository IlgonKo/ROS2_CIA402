from motion_server.api.validator import parse_int
from motion_server.failure import InvalidArgumentException, ResourceNotFoundException


def command_name(message):
    return str(message.get("cmd", message.get("type", ""))).strip()


def public_command_name(message):
    return command_name(message)


def axis_count(runtime):
    return len(runtime.slaves)


def parse_axis_indices(message, runtime, command_name):
    try:
        if "axes" in message:
            axes = [parse_int(value) for value in message.get("axes", [])]
        elif "axis" in message:
            axes = [parse_int(message.get("axis"))]
        else:
            axes = list(range(axis_count(runtime)))
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentException("axes", "must contain integer indices") from exc

    if not axes:
        raise InvalidArgumentException("axes", "requires at least one axis")
    invalid_axes = [
        axis_index
        for axis_index in axes
        if axis_index < 0 or axis_index >= axis_count(runtime)
    ]
    if invalid_axes:
        raise ResourceNotFoundException("axis", invalid_axes[0])
    return axes


def selected_axes(message, runtime, command):
    return parse_axis_indices(message, runtime, command)


def selected_single_axis(message, runtime, command):
    axes = selected_axes(message, runtime, command)
    if len(axes) != 1:
        raise InvalidArgumentException("axis", "requires exactly one axis")
    return axes[0]


def io_devices(runtime):
    return runtime.device_manager.io.devices


def selected_io_device(runtime, io_id=None, slave_index=None):
    return runtime.device_manager.io.selected_device(io_id, slave_index)
