from motion_server.control.pdo_contract import require_pdo_fields_for_mode
from motion_server.device_manager.profile_access import axis_device_profile
from motion_server.app.cycle import exchange
from motion_server.control.axis_operations import (
    configure_motion_mode,
    disabled_operation_axes,
    hold_axis_at_actual_position,
    reject_if_any_axis_disabled,
    update_motion_mode_summary,
)
from motion_server.api import (
    public_command_name,
    raise_operation_rejected,
    selected_single_axis,
)


def start_jog(message, runtime, state, client):
    command = public_command_name(message)
    try:
        axis_index = selected_single_axis(message, runtime, command)
        direction = str(message.get("direction", "")).strip().lower()
        speed = str(message.get("speed", "slow")).strip().lower()
        if direction not in {"positive", "negative", "+", "-"}:
            raise ValueError(
                f"{command} requires direction positive or negative"
            )
        if speed not in {"slow", "fast", "two_phase"}:
            raise ValueError(
                f"{command} speed must be slow, fast, or two_phase"
            )
    except Exception as exc:
        raise_operation_rejected(client, command, str(exc))
        return
    if reject_if_any_axis_disabled(runtime, [axis_index], client, command):
        return

    try:
        require_pdo_fields_for_mode(runtime, "jog", axis_index)
        if state["motion_modes"][axis_index] != "jog":
            state["jog_previous_modes"][axis_index] = state["motion_modes"][axis_index]
            hold_axis_at_actual_position(runtime, state, axis_index)
            configure_motion_mode(runtime, "jog", axis_index)
            state["motion_modes"][axis_index] = "jog"
            update_motion_mode_summary(state)
    except Exception as exc:
        raise_operation_rejected(client, command, str(exc))
        return

    slave = runtime.slaves[axis_index]
    slave.rxpdo.mode_of_operation = axis_device_profile(runtime, axis_index).JOG_MODE
    controlword = 0x000F
    if direction in {"positive", "+"}:
        controlword |= 1 << 4
        public_direction = "positive"
    else:
        controlword |= 1 << 5
        public_direction = "negative"
    if speed == "slow":
        controlword |= 1 << 11
    elif speed == "fast":
        controlword |= 1 << 12
    slave.rxpdo.controlword = controlword
    runtime.logger.status(
        "Received axis/jog_start: "
        f"axis={axis_index} direction={public_direction} speed={speed} "
        f"controlword=0x{controlword:04X}",
    )


def stop_jog(message, runtime, state, client):
    command = public_command_name(message)
    try:
        axis_index = selected_single_axis(message, runtime, command)
    except Exception as exc:
        raise_operation_rejected(client, command, str(exc))
        return

    slave = runtime.slaves[axis_index]
    if disabled_operation_axes(runtime, [axis_index]):
        slave.rxpdo.controlword = 0x0007
    else:
        slave.rxpdo.controlword = 0x000F
    exchange(runtime, cycles=5)

    previous_mode = state["jog_previous_modes"][axis_index] or "pp"
    try:
        hold_axis_at_actual_position(runtime, state, axis_index)
        configure_motion_mode(runtime, previous_mode, axis_index)
        state["motion_modes"][axis_index] = previous_mode
        update_motion_mode_summary(state)
    except Exception as exc:
        raise_operation_rejected(
            client,
            command,
            f"Jog stopped, but failed to restore {previous_mode.upper()}: {exc}",
        )
        return
    finally:
        state["jog_previous_modes"][axis_index] = None

    runtime.logger.status(
        "Received axis/jog_stop: "
        f"axis={axis_index} restored_mode={previous_mode.upper()}",
    )
