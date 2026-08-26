from motion_server.app.initialization import initialization_failure_data
from motion_server.app.session import ServerRuntimeState, session_from_state
from motion_server.diagnostic.serialization import diagnostic_status_snapshot


def server_health_snapshot(state):
    """Return the compact server-wide health projection used by feedback clients."""
    session = session_from_state(state)
    diagnostic_status = diagnostic_status_snapshot(session.diagnostic_manager)
    statuses = diagnostic_status["statuses"]
    fault_count = sum(
        item["definition"]["level"] == "fault" for item in statuses
    )
    alarm_count = sum(
        item["definition"]["level"] == "alarm" for item in statuses
    )
    representative = None
    if statuses:
        first = statuses[0]
        representative = {
            "code": first["definition"]["code"],
            "level": first["definition"]["level"],
            "title": first["definition"]["title"],
            "source": first["source"],
        }

    return {
        "initialized": session.initialization_status.initialized,
        "runtime_state": session.runtime_state.value,
        "diagnostic_level": diagnostic_status["level"],
        "fault_count": fault_count,
        "alarm_count": alarm_count,
        "representative_diagnostic": representative,
        "initialization_failure": initialization_failure_data(
            session.initialization_status.failure
        ),
    }


def process_data_is_valid(state):
    session = session_from_state(state)
    return (
        session.runtime is not None
        and session.runtime_state
        not in {
            ServerRuntimeState.INITIALIZATION_ERROR,
            ServerRuntimeState.BUS_DISCONNECTED,
        }
    )
