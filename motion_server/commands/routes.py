from motion_server.commands import CommandRouter
from motion_server.commands.homing import start_homing
from motion_server.commands.jog import start_jog, stop_jog
from motion_server.commands.motion import (
    move_absolute,
    move_relative,
    move_velocity,
)
from motion_server.commands.parameters import save_parameters, write_parameter
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
    set_controlword,
    stop_axes,
    stop_system,
)
from motion_server.commands.trajectory import (
    move_api as move_trajectory,
    status as trajectory_status,
    stop as stop_trajectory,
)


COMMAND_ROUTER = CommandRouter({
    "trajectory/status": trajectory_status,
    "trajectory/move": move_trajectory,
    "trajectory/stop": stop_trajectory,
    "system/stop": lambda message, runtime, state, client: (
        stop_system(message, runtime, state)
    ),
    "system/reset": lambda message, runtime, state, client: (
        reset_faults(runtime, state)
    ),
    "axis/enable": enable,
    "axis/disable": disable,
    "axis/reset": reset_axes,
    "axis/home": start_homing,
    "axis/stop": stop_axes,
    "axis/move_abs": move_absolute,
    "axis/move_rel": move_relative,
    "axis/move_vel": move_velocity,
    "axis/jog_start": start_jog,
    "axis/jog_stop": stop_jog,
    "axis/profile": set_profile,
    "axis/motion_limits": set_motion_limits,
    "axis/software_position_limits": set_software_position_limits,
    "axis/mode": set_mode,
    "axis/param_write": lambda message, runtime, state, client: (
        write_parameter(message, runtime, client)
    ),
    "axis/param_save": lambda message, runtime, state, client: (
        save_parameters(message, runtime, client)
    ),
    "debug/controlword": lambda message, runtime, state, client: (
        set_controlword(message, runtime, state)
    ),
})
