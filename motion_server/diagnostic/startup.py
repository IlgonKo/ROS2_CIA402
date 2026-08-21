from motion_server.diagnostic.definitions import (
    SERVER_INITIALIZATION_FAILED,
    SERVER_SOURCE,
)


def detect_initialization_fault(runtime, *, at=None):
    return runtime.diagnostic_manager.detect(
        SERVER_INITIALIZATION_FAILED,
        SERVER_SOURCE,
        at=at,
    )


def resolve_initialization_fault(runtime, *, at=None):
    try:
        return runtime.diagnostic_manager.resolve(
            SERVER_INITIALIZATION_FAILED.code,
            SERVER_SOURCE,
            at=at,
        )
    except KeyError:
        return None
