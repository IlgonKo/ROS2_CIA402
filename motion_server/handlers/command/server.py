from motion_server.app.session import ServerRuntimeState, session_from_state
from motion_server.diagnostic.models import (
    DiagnosticSource,
    DiagnosticSourceType,
)


def _refresh_global_fault_state(state):
    session = session_from_state(state)
    manager = session.diagnostic_manager
    global_fault = any(
        manager.has_active_fault(source_type=source_type)
        for source_type in (
            DiagnosticSourceType.SERVER,
            DiagnosticSourceType.BUS,
        )
    )
    if (
        not global_fault
        and session.runtime is not None
        and session.runtime_state is ServerRuntimeState.FAULT
    ):
        session.set_runtime_state(ServerRuntimeState.NORMAL)


def fault_reset_source(state, source_type):
    session = session_from_state(state)
    source = DiagnosticSource(source_type, 0)
    statuses = session.diagnostic_manager.acknowledge_faults(source=source)
    _refresh_global_fault_state(state)
    return {
        "source": source_type.value,
        "fault_count": len(statuses),
        "message": f"{source_type.value.title()} Fault Reset completed.",
    }


def fault_reset_server(message, runtime, state, client):
    return fault_reset_source(state, DiagnosticSourceType.SERVER)


def fault_reset_bus(message, runtime, state, client):
    return fault_reset_source(state, DiagnosticSourceType.BUS)


def request_server_restart(message, runtime, state, client):
    state["server_restart_requested"] = True
    return {"message": "Motion Server restart accepted. Process will restart."}
