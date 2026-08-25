from motion_server.diagnostic.serialization import diagnostic_status_snapshot
from motion_server.app.initialization import initialization_failure_data
from motion_server.app.session import session_from_state


def server_status_message(runtime, state):
    initialization_status = state["initialization_status"]
    runtime_state = session_from_state(state).runtime_state
    return {
        "type": "system/server/status",
        "ok": True,
        "server_mode": state.get("server_mode", "basic"),
        "initialized": initialization_status.initialized,
        "runtime_state": runtime_state.value,
        "initialization_failure": initialization_failure_data(
            initialization_status.failure
        ),
        "cycle_time": (
            None if runtime is None else float(runtime.cycle_time)
        ),
        "feedback_type": (
            None if runtime is None else "system/feedback"
        ),
        "diagnostic_status": diagnostic_status_snapshot(
            state["diagnostic_manager"]
        ),
    }
