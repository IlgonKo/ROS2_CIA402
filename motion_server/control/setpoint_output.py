from motion_server.control.pdo_contract import require_pdo_fields_for_mode
from motion_server.device_manager.profile_access import axis_device_profile
from motion_server.app.cycle import exchange
from motion_server.device_manager.axis_diagnostics import diagnostics_summary
from motion_server.control.axis_operations import (
    configure_motion_mode,
    faulted_axes,
    hold_axis_at_actual_position,
    hold_faulted_axes,
    reject_if_any_axis_disabled,
    reject_if_pv_not_allowed,
    update_motion_mode_summary,
)
from motion_server.api import require_int32
from motion_server.failure import InvalidStateException


def command_profile_positions(runtime, target_positions, axis_indices):
    for axis_index in axis_indices:
        require_pdo_fields_for_mode(runtime, "pp", axis_index)
        target_position = target_positions[axis_index]
        slave = runtime.slaves[axis_index]
        profile = axis_device_profile(runtime, axis_index)
        slave.rxpdo.mode_of_operation = profile.PROFILE_POSITION_MODE
        slave.rxpdo.target_position = require_int32(
            target_position,
            f"axis {axis_index} target_position",
        )

    pp_setpoint_handshake(runtime, axis_indices)


def command_profile_velocities(
    runtime,
    state,
    axis_indices,
    velocities,
    command,
    client=None,
):
    faults = faulted_axes(runtime)
    if faults:
        hold_faulted_axes(runtime, state)
        runtime.sync_trajectory_to_actual_positions()
        print(
            f"Ignored {command} because at least one drive is faulted. "
            f"faulted_axes={faults} "
            f"statuswords={[f'0x{slave.txpdo.statusword:04X}' for slave in runtime.slaves]}",
            flush=True,
        )
        raise InvalidStateException(command, "axis_fault")

    if reject_if_any_axis_disabled(runtime, axis_indices, client, command):
        return

    if reject_if_pv_not_allowed(state, axis_indices, client, command):
        return

    for axis_index, velocity in zip(axis_indices, velocities):
        require_pdo_fields_for_mode(runtime, "pv", axis_index)
        slave = runtime.slaves[axis_index]
        target_velocity = require_int32(
            velocity,
            f"axis {axis_index} target_velocity",
        )
        slave.rxpdo.target_velocity = target_velocity
        if state["motion_modes"][axis_index] != "pv":
            hold_axis_at_actual_position(runtime, state, axis_index)
            configure_motion_mode(runtime, "pv", axis_index)
            state["motion_modes"][axis_index] = "pv"
        profile = axis_device_profile(runtime, axis_index)
        slave.rxpdo.mode_of_operation = profile.PROFILE_VELOCITY_MODE
        slave.rxpdo.target_velocity = target_velocity
        slave.rxpdo.controlword = 0x000F
        runtime.sync_velocity_command(axis_index, velocity)

    update_motion_mode_summary(state)
    exchange(runtime, cycles=2)


def pp_setpoint_handshake(runtime, axis_indices):
    for axis_index in axis_indices:
        profile = axis_device_profile(runtime, axis_index)
        runtime.slaves[axis_index].rxpdo.controlword = profile.PP_BASE_CONTROLWORD
    ack_cleared_before = wait_pp_setpoint_ack(
        runtime,
        axis_indices,
        expected=False,
        max_cycles=max(
            axis_device_profile(runtime, index).PP_HANDSHAKE_MAX_CYCLES
            for index in axis_indices
        ),
    )

    for axis_index in axis_indices:
        profile = axis_device_profile(runtime, axis_index)
        runtime.slaves[axis_index].rxpdo.controlword = profile.PP_NEW_SETPOINT_CONTROLWORD
    ack_set = wait_pp_setpoint_ack(
        runtime,
        axis_indices,
        expected=True,
        max_cycles=max(
            axis_device_profile(runtime, index).PP_HANDSHAKE_MAX_CYCLES
            for index in axis_indices
        ),
    )

    for axis_index in axis_indices:
        profile = axis_device_profile(runtime, axis_index)
        runtime.slaves[axis_index].rxpdo.controlword = profile.PP_BASE_CONTROLWORD
    ack_cleared_after = wait_pp_setpoint_ack(
        runtime,
        axis_indices,
        expected=False,
        max_cycles=max(
            axis_device_profile(runtime, index).PP_HANDSHAKE_MAX_CYCLES
            for index in axis_indices
        ),
    )

    if not (ack_cleared_before and ack_set and ack_cleared_after):
        diagnostics = diagnostics_summary(runtime, axis_indices)
        message = (
            "PP set-point handshake did not complete cleanly. "
            f"axes={axis_indices} "
            f"ack_cleared_before={ack_cleared_before} "
            f"ack_set={ack_set} "
            f"ack_cleared_after={ack_cleared_after} "
            f"statuswords={[f'0x{runtime.slaves[index].txpdo.statusword:04X}' for index in axis_indices]} "
            f"diagnostics={diagnostics}"
        )
        print(message, flush=True)
        raise RuntimeError(message)


def wait_pp_setpoint_ack(runtime, axis_indices, expected, max_cycles):
    for _ in range(max_cycles):
        exchange(runtime)
        if all(
            bool(
                runtime.slaves[axis_index].txpdo.statusword
                & axis_device_profile(runtime, axis_index).PP_SETPOINT_ACK_MASK
            )
            == expected
            for axis_index in axis_indices
        ):
            return True

    return False


def command_csp_positions(runtime, target_positions, axis_indices):
    checked_positions = list(target_positions)
    for axis_index in axis_indices:
        checked_positions[axis_index] = require_int32(
            checked_positions[axis_index],
            f"axis {axis_index} target_position",
        )
    for axis_index in axis_indices:
        slave = runtime.slaves[axis_index]
        profile = axis_device_profile(runtime, axis_index)
        slave.rxpdo.mode_of_operation = profile.CSP_MODE
        slave.rxpdo.controlword = 0x000F

    runtime.set_target_positions(checked_positions)
