from motion_server.failure import InvalidRequestException, UnsupportedOperationException
from motion_server.handlers.command.homing import start_homing
from motion_server.handlers.command.io_output_write import output_write
from motion_server.handlers.command.io_ap_parameter_write import (
    write_ap_parameter,
)
from motion_server.handlers.command.io_iol_parameter_write import (
    write_iol_parameter,
)
from motion_server.handlers.command.jog import start_jog, stop_jog
from motion_server.handlers.command.motion import (
    move_absolute,
    move_relative,
    move_velocity,
)
from motion_server.handlers.command.bus import request_bus_reconnect
from motion_server.handlers.command.axis_parameter_save import save_parameters
from motion_server.handlers.command.axis_parameter_write import write_parameter
from motion_server.handlers.command.io_ethercat_parameter_write import (
    write_io_parameter,
)
from motion_server.handlers.command.server import (
    fault_reset_bus,
    fault_reset_server,
    request_server_restart,
)
from motion_server.api.specification import (
    command_names,
    status_message_types,
)
from motion_server.handlers.command.axis_settings import (
    set_mode,
    set_motion_limits,
    set_profile,
    set_software_position_limits,
)
from motion_server.handlers.command.axis_state import (
    disable,
    enable,
    fault_reset_axes,
    reset_faults,
    restart_axis,
    set_controlword,
    stop_axes,
)
from motion_server.handlers.command.trajectory import (
    move_api as move_trajectory,
    stop as stop_trajectory,
)
from motion_server.handlers.simulation_io_input import (
    reset_inputs as reset_simulation_inputs,
    write_input as write_simulation_input,
)


def reject_not_implemented(message, runtime, state, client):
    command = str(message.get("cmd", "")).strip()
    raise UnsupportedOperationException(command, "not_implemented")


def require_single_axis(command):
    def wrapper(message, runtime, state, client):
        public_command = str(message.get("cmd", "")).strip()
        if "axes" in message or "axis" not in message:
            raise InvalidRequestException(
                f"{public_command} requires axis and does not accept axes."
            )
        return command(message, runtime, state, client)

    return wrapper


def require_axes(command):
    def wrapper(message, runtime, state, client):
        public_command = str(message.get("cmd", "")).strip()
        if "axis" in message or "axes" not in message:
            raise InvalidRequestException(
                f"{public_command} requires axes and does not accept axis."
            )
        return command(message, runtime, state, client)

    return wrapper


COMMAND_HANDLERS = {
    "system/axes/trajectory": require_axes(move_trajectory),
    "system/axes/trajectory_stop": require_axes(stop_trajectory),
    "system/axes/stop": require_axes(stop_axes),
    "system/axis/enable": require_single_axis(enable),
    "system/axis/disable": require_single_axis(disable),
    "system/axis/fault_reset": require_single_axis(fault_reset_axes),
    "system/axis/restart": require_single_axis(restart_axis),
    "system/axis/home": require_single_axis(start_homing),
    "system/axis/stop": require_single_axis(stop_axes),
    "system/axis/move_abs": require_single_axis(move_absolute),
    "system/axis/move_rel": require_single_axis(move_relative),
    "system/axis/move_vel": require_single_axis(move_velocity),
    "system/axis/jog_start": require_single_axis(start_jog),
    "system/axis/jog_stop": require_single_axis(stop_jog),
    "system/axis/profile": require_single_axis(set_profile),
    "system/axis/motion_limits": require_single_axis(set_motion_limits),
    "system/axis/software_position_limits": require_single_axis(set_software_position_limits),
    "system/axis/mode": require_single_axis(set_mode),
    "system/axis/manualCW": require_single_axis(
        lambda message, runtime, state, client: set_controlword(message, runtime, state)
    ),
    "system/axis/param_write": lambda message, runtime, state, client: (
        write_parameter(message, runtime, client)
    ),
    "system/axis/param_save": lambda message, runtime, state, client: (
        save_parameters(message, runtime, client)
    ),
    "system/axes/enable": require_axes(enable),
    "system/axes/disable": require_axes(disable),
    "system/axes/fault_reset": require_axes(fault_reset_axes),
    "system/axes/move_abs": require_axes(move_absolute),
    "system/axes/move_rel": require_axes(move_relative),
    "system/axes/move_vel": require_axes(move_velocity),
    "system/server/fault_reset": fault_reset_server,
    "system/server/restart": request_server_restart,
    "system/bus/fault_reset": fault_reset_bus,
    "system/bus/reconnect": request_bus_reconnect,
    "system/bus/rescan": reject_not_implemented,
    "system/io/output_write": output_write,
    "system/simulation/io/input_write": write_simulation_input,
    "system/simulation/io/input_reset": reset_simulation_inputs,
    "system/io/reset": reject_not_implemented,
    "system/io/restart": reject_not_implemented,
    "system/io/param_write": lambda message, runtime, state, client: (
        write_io_parameter(message, runtime, client)
    ),
    "system/io/param_save": reject_not_implemented,
    "system/io/ap/param_write": lambda message, runtime, state, client: (
        write_ap_parameter(message, runtime, client)
    ),
    "system/io/iol/param_write": lambda message, runtime, state, client: (
        write_iol_parameter(message, runtime, client)
    ),
}


def validate_command_registry():
    route_names = set(COMMAND_HANDLERS)
    expected_names = command_names() - status_message_types() - {
        "system/authority/request",
        "system/authority/release",
        "system/authority/status",
    }
    missing = sorted(expected_names - route_names)
    unknown = sorted(route_names - command_names())
    if missing or unknown:
        raise RuntimeError(
            "Motion Server command registry/specification mismatch. "
            f"missing={missing} unknown={unknown}"
        )


validate_command_registry()


def handle_command(command_name, message, runtime, state, client):
    command = COMMAND_HANDLERS.get(command_name)
    if command is None:
        from motion_server.failure import UnknownCommandException
        raise UnknownCommandException(command_name)
    return command(message, runtime, state, client)
