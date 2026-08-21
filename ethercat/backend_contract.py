from typing import Protocol, runtime_checkable


@runtime_checkable
class StagedBackend(Protocol):
    def connect(self, target_state=None): ...
    def enter_operational(self): ...
    def close(self): ...
    def prepare_processdata(self): ...
    def send_processdata(self): ...
    def receive_processdata(self): ...
    def expected_wkc(self): ...


REQUIRED_BACKEND_METHODS = (
    "connect",
    "enter_operational",
    "close",
    "prepare_processdata",
    "send_processdata",
    "receive_processdata",
    "expected_wkc",
)


def validate_staged_backend(backend):
    missing = [
        name
        for name in REQUIRED_BACKEND_METHODS
        if not callable(getattr(backend, name, None))
    ]
    if missing:
        raise TypeError(
            f"Backend {type(backend).__name__} does not implement the staged "
            f"lifecycle contract; missing: {', '.join(missing)}"
        )
    return backend
