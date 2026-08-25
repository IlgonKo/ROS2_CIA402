INT32_MIN = -(2 ** 31)
INT32_MAX = 2 ** 31 - 1
UINT32_MAX = 2 ** 32 - 1


def parse_int(value, base=0):
    if isinstance(value, int):
        return value
    return int(str(value), base)


def require_int32(value, field_name):
    result = int(round(float(value)))
    if result < INT32_MIN or result > INT32_MAX:
        raise ValueError(
            f"{field_name}={result} is outside int32 PDO range "
            f"[{INT32_MIN}, {INT32_MAX}]"
        )
    return result


def require_uint32(value, field_name):
    result = int(round(float(value)))
    if result < 0 or result > UINT32_MAX:
        raise ValueError(
            f"{field_name}={result} is outside uint32 PDO range "
            f"[0, {UINT32_MAX}]"
        )
    return result


def is_advanced_mode(state):
    return state.get("server_mode") == "advanced"


def command_allowed_by_mode(spec, state):
    return not spec.advanced_only or is_advanced_mode(state)


def initialization_status(state):
    status = state.get("initialization_status")
    if not isinstance(status, InitializationStatus):
        raise RuntimeError("Server state has no InitializationStatus")
    return status


def command_allowed_during_degraded_state(spec, state):
    status = initialization_status(state)
    return status.initialized or spec.degraded_allowed


def recovery_scope_allowed(spec, state):
    status = initialization_status(state)
    if status.initialized or spec.name not in RECOVERY_COMMAND_SCOPES:
        return True
    return recovery_action_allowed(
        status.failure.stage,
        RECOVERY_COMMAND_SCOPES[spec.name],
    )


def command_requires_authority(spec):
    return spec.is_command and spec.authority_required


GLOBAL_FAULT_ALLOWED_COMMANDS = {
    "system/server/fault_reset",
    "system/server/restart",
    "system/bus/fault_reset",
    "system/bus/reconnect",
    "system/axis/disable",
    "system/axis/fault_reset",
    "system/axis/stop",
    "system/axes/disable",
    "system/axes/fault_reset",
    "system/axes/stop",
}

AXIS_FAULT_ALLOWED_COMMANDS = {
    "system/axis/disable",
    "system/axis/fault_reset",
    "system/axis/stop",
    "system/axes/disable",
    "system/axes/fault_reset",
    "system/axes/stop",
}


def _selected_axis_indices(message):
    if not isinstance(message, dict):
        return ()
    values = message.get("axes")
    if values is None and "axis" in message:
        values = (message["axis"],)
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        values = (values,)
    try:
        return tuple(int(value) for value in values)
    except (TypeError, ValueError):
        return ()


def command_allowed_by_runtime_state(spec, state, message):
    if not spec.is_command:
        return True
    session = state.get("server_session")
    if session is None:
        return True

    from motion_server.app.session import ServerRuntimeState

    if (
        spec.name == "system/bus/reconnect"
        and session.runtime_state is ServerRuntimeState.NORMAL
    ):
        return False

    if session.runtime_state in {
        ServerRuntimeState.FAULT,
        ServerRuntimeState.BUS_DISCONNECTED,
    } and spec.name not in GLOBAL_FAULT_ALLOWED_COMMANDS:
        return False

    if not spec.name.startswith(("system/axis/", "system/axes/")):
        return True
    if spec.name in AXIS_FAULT_ALLOWED_COMMANDS:
        return True

    from motion_server.diagnostic.models import (
        DiagnosticSource,
        DiagnosticSourceType,
    )

    manager = session.diagnostic_manager
    return not any(
        manager.has_active_fault(
            source=DiagnosticSource(DiagnosticSourceType.AXIS, axis_index),
        )
        for axis_index in _selected_axis_indices(message)
        if axis_index >= 0
    )


def validate_command(spec, client, state, has_authority, *, message=None):
    if spec is None:
        return "unknown"
    if not command_allowed_by_mode(spec, state):
        return "advanced_only"
    if not command_allowed_during_degraded_state(spec, state):
        return "not_initialized"
    if not recovery_scope_allowed(spec, state):
        return "invalid_recovery_scope"
    if command_requires_authority(spec) and not has_authority:
        return "authority_required"
    if not command_allowed_by_runtime_state(spec, state, message):
        return "runtime_fault"
    return None
from motion_server.app.initialization import (
    InitializationRecoveryScope,
    InitializationStatus,
    recovery_action_allowed,
)


RECOVERY_COMMAND_SCOPES = {
    "system/bus/reconnect": InitializationRecoveryScope.BUS_RECONNECT,
    "system/server/restart": InitializationRecoveryScope.SERVER_RESTART,
}
