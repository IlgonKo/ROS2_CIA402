from motion_server.commands import CommandRouter
from motion_server.api import reject_command_message
from motion_server.commands.homing import start_homing
from motion_server.commands.jog import start_jog, stop_jog
from motion_server.commands.motion import (
    move_absolute,
    move_relative,
    move_velocity,
)
from motion_server.commands.parameters import save_parameters, write_parameter
from motion_server.commands.server import (
    request_bus_reconnect,
    request_server_reset,
    request_server_restart,
)
from motion_server.commands.settings import (
    set_mode,
    set_motion_limits,
    set_profile,
    set_software_position_limits,
)
from motion_server.commands.system import (
    disable,
    enable,
    reset_axes,
    reset_faults,
    restart_axis,
    set_controlword,
    stop_axes,
)
from motion_server.commands.trajectory import (
    move_api as move_trajectory,
    stop as stop_trajectory,
)


def reject_not_implemented(message, runtime, state, client):
    command = str(message.get("cmd", "")).strip()
    reject_command_message(client, command, f"{command} is not implemented yet.")


def require_single_axis(command):
    def wrapper(message, runtime, state, client):
        public_command = str(message.get("cmd", "")).strip()
        if "axes" in message or "axis" not in message:
            reject_command_message(
                client,
                public_command,
                f"{public_command} requires axis and does not accept axes.",
            )
            return
        command(message, runtime, state, client)

    return wrapper


def require_axes(command):
    def wrapper(message, runtime, state, client):
        public_command = str(message.get("cmd", "")).strip()
        if "axis" in message or "axes" not in message:
            reject_command_message(
                client,
                public_command,
                f"{public_command} requires axes and does not accept axis.",
            )
            return
        command(message, runtime, state, client)

    return wrapper


COMMAND_ROUTER = CommandRouter({
    "system/axes/trajectory": require_axes(move_trajectory),
    "system/axes/trajectory_stop": require_axes(stop_trajectory),
    "system/axes/stop": require_axes(stop_axes),
    "system/axis/enable": require_single_axis(enable),
    "system/axis/disable": require_single_axis(disable),
    "system/axis/reset": require_single_axis(reset_axes),
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
    "system/axes/reset": require_axes(reset_axes),
    "system/axes/move_abs": require_axes(move_absolute),
    "system/axes/move_rel": require_axes(move_relative),
    "system/axes/move_vel": require_axes(move_velocity),
    "system/server/reset": request_server_reset,
    "system/server/restart": request_server_restart,
    "system/bus/reconnect": request_bus_reconnect,
    "system/bus/rescan": reject_not_implemented,
    "system/io/read": reject_not_implemented,
    "system/io/write": reject_not_implemented,
    "system/io/set_output": reject_not_implemented,
    "system/io/reset": reject_not_implemented,
    "system/io/restart": reject_not_implemented,
    "system/io/param_read": reject_not_implemented,
    "system/io/param_write": reject_not_implemented,
    "system/io/param_save": reject_not_implemented,
})
