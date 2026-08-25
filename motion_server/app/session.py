from enum import Enum

from motion_server.app.initialization import InitializationStatus
from motion_server.diagnostic import DiagnosticManager


class ServerRuntimeState(str, Enum):
    NORMAL = "normal"
    INITIALIZATION_ERROR = "initialization_error"
    BUS_DISCONNECTED = "bus_disconnected"
    FAULT = "fault"


class ServerSession:
    """Owns one server lifecycle's Diagnostic and optional runtime state."""

    def __init__(
        self,
        initialization_status,
        *,
        diagnostic_manager=None,
        runtime=None,
    ):
        if not isinstance(initialization_status, InitializationStatus):
            raise TypeError("Server Session requires InitializationStatus")
        self.initialization_status = initialization_status
        self.runtime_state = (
            ServerRuntimeState.NORMAL
            if initialization_status.initialized
            else ServerRuntimeState.INITIALIZATION_ERROR
        )
        self.diagnostic_manager = diagnostic_manager or DiagnosticManager()
        self.runtime = None
        if runtime is not None:
            self.attach_runtime(runtime)

    def attach_runtime(self, runtime):
        if runtime is None:
            raise TypeError("Server Session runtime must not be None")
        runtime.diagnostic_manager = self.diagnostic_manager
        self.runtime = runtime
        return runtime

    def detach_runtime(self):
        runtime = self.runtime
        self.runtime = None
        return runtime

    def mark_ready(self):
        self.initialization_status = InitializationStatus.ready()
        self.runtime_state = ServerRuntimeState.NORMAL

    def mark_failed(self, failure):
        self.initialization_status = InitializationStatus.failed(failure)
        self.runtime_state = ServerRuntimeState.INITIALIZATION_ERROR

    def set_runtime_state(self, runtime_state):
        if not isinstance(runtime_state, ServerRuntimeState):
            raise TypeError("Server runtime state must be ServerRuntimeState")
        if (
            runtime_state is not ServerRuntimeState.INITIALIZATION_ERROR
            and self.runtime is None
        ):
            raise RuntimeError("Connected server runtime state requires a runtime")
        self.runtime_state = runtime_state


def session_from_state(state):
    session = state.get("server_session")
    if not isinstance(session, ServerSession):
        raise RuntimeError("Server state has no ServerSession")
    return session
