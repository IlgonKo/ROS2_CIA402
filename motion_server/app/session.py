from motion_server.app.initialization import InitializationStatus
from motion_server.diagnostic import DiagnosticManager


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

    def mark_failed(self, failure):
        self.initialization_status = InitializationStatus.failed(failure)


def session_from_state(state):
    session = state.get("server_session")
    if not isinstance(session, ServerSession):
        raise RuntimeError("Server state has no ServerSession")
    return session
