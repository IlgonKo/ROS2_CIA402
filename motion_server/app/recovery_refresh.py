from enum import Enum

from motion_server.app.startup import refresh_axis_parameter_cache
from motion_server.diagnostic import (
    DiagnosticSource,
    DiagnosticSourceType,
    PARAMETER_REFRESH_FAILED,
)
from motion_server.failure import MotionServerException


PARAMETER_REFRESH_ERRORS = (
    MotionServerException,
    OSError,
    AttributeError,
    TypeError,
    ValueError,
    OverflowError,
    RuntimeError,
)


class RecoveryType(str, Enum):
    BUS_RECONNECT = "bus_reconnect"
    AXIS_RESTART = "axis_restart"


def refresh_after_recovery(runtime, recovery_type, affected_axes):
    """TD-025 integration boundary backed by the current Axis cache adapter."""
    if not isinstance(recovery_type, RecoveryType):
        raise TypeError("Recovery refresh type must be RecoveryType")
    axes = tuple(int(axis_index) for axis_index in affected_axes)
    if not axes:
        raise ValueError("Recovery refresh requires at least one Axis")
    if len(set(axes)) != len(axes):
        raise ValueError("Recovery refresh Axis indices must be unique")
    axis_count = len(runtime.slaves)
    if any(axis_index < 0 or axis_index >= axis_count for axis_index in axes):
        raise ValueError("Recovery refresh Axis index is out of range")
    if (
        recovery_type is RecoveryType.BUS_RECONNECT
        and set(axes) != set(range(axis_count))
    ):
        raise ValueError("Bus reconnect must refresh every Axis")
    if recovery_type is RecoveryType.AXIS_RESTART and len(axes) != 1:
        raise ValueError("Axis restart must refresh exactly one Axis")

    refreshed = []
    for axis_index in axes:
        source = DiagnosticSource(DiagnosticSourceType.AXIS, axis_index)
        try:
            refreshed.append(refresh_axis_parameter_cache(runtime, axis_index))
        except PARAMETER_REFRESH_ERRORS as exception:
            invalidate_axis = getattr(runtime.axis_parameters, "invalidate_axis", None)
            if callable(invalidate_axis):
                invalidate_axis(axis_index, exception)
            manager = getattr(runtime, "diagnostic_manager", None)
            if manager is not None:
                manager.detect(
                    PARAMETER_REFRESH_FAILED,
                    source,
                    detail=str(exception),
                    context={
                        "recovery_type": recovery_type.value,
                        "axis": axis_index,
                    },
                )
            raise
        manager = getattr(runtime, "diagnostic_manager", None)
        if (
            manager is not None
            and manager.status_for(PARAMETER_REFRESH_FAILED.code, source) is not None
        ):
            manager.resolve(PARAMETER_REFRESH_FAILED.code, source)
    return tuple(refreshed)
