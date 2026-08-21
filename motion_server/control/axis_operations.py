from motion_server.config import CSP_MODE, DEVICE_PROFILE, require_pdo_fields_for_mode
from motion_server.app.cycle import exchange
from motion_server.api import raise_operation_rejected


def axis_count(runtime):
    return len(runtime.slaves)


def faulted_axes(runtime):
    return [
        axis_index
        for axis_index, slave in enumerate(runtime.slaves)
        if int(slave.txpdo.statusword) & 0x0008
    ]


def actual_positions(runtime):
    return [
        float(slave.txpdo.actual_position)
        for slave in runtime.slaves
    ]


def hold_axis_at_actual_position(runtime, state, axis_index):
    state["target_positions"] = runtime.hold_axes(
        state["target_positions"],
        [axis_index],
    )


def hold_faulted_axes(runtime, state):
    axes = faulted_axes(runtime)
    if axes:
        state["target_positions"] = runtime.hold_axes(
            state["target_positions"],
            axes,
        )
        runtime.set_target_positions(state["target_positions"])


def operation_enabled_axes(runtime, axes):
    return [
        axis_index
        for axis_index in axes
        if int(runtime.slaves[axis_index].txpdo.statusword) & 0x0004
    ]


def disabled_operation_axes(runtime, axes):
    enabled = set(operation_enabled_axes(runtime, axes))
    return [
        axis_index
        for axis_index in axes
        if axis_index not in enabled
    ]


def reject_if_any_axis_disabled(runtime, axes, client, command):
    disabled_axes = disabled_operation_axes(runtime, axes)
    if not disabled_axes:
        return False

    raise_operation_rejected(client, command, "Axis operation is disabled.")


def pv_allowed_axis(state, axis_index):
    return state["axis_devices"].pv_allowed(axis_index)


def pv_reject_message(state, axis_indices):
    details = []
    for axis_index in axis_indices:
        units = state.get("user_position_units", [])
        user_position_unit = units[axis_index] if axis_index < len(units) else None
        if user_position_unit is None:
            details.append(f"axis {axis_index}: 0x216E:01 unread")
        else:
            details.append(
                f"axis {axis_index}: 0x216E:01=0x{int(user_position_unit):04X} "
                f"unit={state['axis_devices'].user_position_unit_name(user_position_unit)}"
            )
    return (
        "PV mode is allowed only for rotary user position units "
        "(rad, degree, or revolution). "
        + "; ".join(details)
    )


def reject_if_pv_not_allowed(state, axis_indices, client, command):
    blocked_axes = [
        axis_index
        for axis_index in axis_indices
        if not pv_allowed_axis(state, axis_index)
    ]
    if not blocked_axes:
        return False

    message = pv_reject_message(state, blocked_axes)
    raise_operation_rejected(client, command, message)


def mode_code(mode_name):
    return DEVICE_PROFILE.mode_code(mode_name)


def configure_motion_mode(runtime, mode_name, axis_index=None):
    require_pdo_fields_for_mode(runtime, mode_name, axis_index)
    code = mode_code(mode_name)
    configure_mode_code(runtime, code, axis_index)


def configure_mode_code(runtime, code, axis_index=None):
    axis_indices = (
        range(axis_count(runtime))
        if axis_index is None
        else [axis_index]
    )
    if axis_index is None:
        runtime.set_mode_of_operation_all(code)

    for current_axis in axis_indices:
        DEVICE_PROFILE.configure_mode_code(runtime, current_axis, code)
    exchange(runtime, cycles=5)


def update_motion_mode_summary(state):
    modes = state["motion_modes"]
    state["motion_mode"] = modes[0] if len(set(modes)) == 1 else "mixed"


def ensure_csp_mode(runtime, state, axis_indices):
    changed = False
    for axis_index in axis_indices:
        if state["motion_modes"][axis_index] != "csp":
            hold_axis_at_actual_position(runtime, state, axis_index)
            runtime.slaves[axis_index].rxpdo.mode_of_operation = CSP_MODE
            runtime.slaves[axis_index].rxpdo.controlword = 0x000F
            state["motion_modes"][axis_index] = "csp"
            changed = True

    if changed:
        update_motion_mode_summary(state)
        runtime.set_target_positions(state["target_positions"])
