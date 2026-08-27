import time

from motion_server.app.cycle import exchange
from motion_server.app.session import ServerRuntimeState, session_from_state
from motion_server.app.startup import (
    clear_axis_restart_commands,
    write_csp_interpolation_modes,
)
from motion_server.app.recovery_refresh import (
    RecoveryType,
    refresh_after_recovery,
)
from motion_server.diagnostic import (
    BUS_CONNECTION_LOST,
    BUS_PROCESS_DATA_INCOMPLETE,
    BUS_RECONNECT_FAILED,
    AXIS_RESTART_FAILED,
    DiagnosticSource,
    DiagnosticSourceType,
)
from motion_server.diagnostic.runtime import BUS_SOURCE
from motion_server.device_manager.profile_access import axis_device_profile
from motion_server.failure import CommunicationException


class RecoveryRefreshException(Exception):
    pass


RECOVERY_WKC_STABLE_CYCLES = 3


def _resolve_if_active(manager, definition):
    if manager.status_for(definition.code, BUS_SOURCE) is not None:
        manager.resolve(definition.code, BUS_SOURCE)


def mark_bus_disconnected(state, exception):
    session = session_from_state(state)
    runtime = session.runtime
    if runtime is None:
        raise RuntimeError("Operational Bus disconnect requires a runtime")
    try:
        runtime.close()
    except Exception:
        pass
    session.diagnostic_manager.detect(
        BUS_CONNECTION_LOST,
        BUS_SOURCE,
        detail=str(exception),
    )
    session.set_runtime_state(ServerRuntimeState.BUS_DISCONNECTED)


def reconnect_runtime(runtime, state):
    session = session_from_state(state)
    if runtime is None or session.runtime is not runtime:
        raise CommunicationException("bus_reconnect")
    if state.get("recovery_in_progress"):
        raise CommunicationException("bus_reconnect_in_progress")

    state["recovery_in_progress"] = "bus_reconnect"
    timeout = float(state["bus_reconnect_timeout"])
    started_at = time.monotonic()
    manager = session.diagnostic_manager
    try:
        runtime.close()
        _connect_until(runtime, started_at + timeout)
        if state.get("simulation_api_enabled", False):
            reset_virtual_inputs = getattr(
                runtime.ethercat_master,
                "reset_virtual_io_inputs",
                None,
            )
            if callable(reset_virtual_inputs):
                reset_virtual_inputs()
        _restore_process_image(
            runtime,
            state,
            recovery_type=RecoveryType.BUS_RECONNECT,
            refresh_axes=range(len(runtime.slaves)),
            deadline=started_at + timeout,
        )
        if time.monotonic() > started_at + timeout:
            raise TimeoutError(
                f"Bus reconnect exceeded {timeout:.3f} seconds"
            )
    except Exception as exception:
        try:
            runtime.close()
        except Exception:
            pass
        record_bus_reconnect_failure(session, exception)
        session.set_runtime_state(ServerRuntimeState.BUS_DISCONNECTED)
        raise CommunicationException("bus_reconnect") from exception
    finally:
        state["recovery_in_progress"] = None

    complete_bus_reconnect_diagnostics(session)
    global_fault = any(
        manager.has_active_fault(source_type=source_type)
        for source_type in (
            DiagnosticSourceType.SERVER,
            DiagnosticSourceType.BUS,
        )
    )
    session.set_runtime_state(
        ServerRuntimeState.FAULT
        if global_fault
        else ServerRuntimeState.NORMAL
    )
    return {
        "connected": True,
        "elapsed": time.monotonic() - started_at,
        "message": "EtherCAT Bus reconnect completed.",
    }


def record_bus_reconnect_failure(session, exception):
    return session.diagnostic_manager.detect(
        BUS_RECONNECT_FAILED,
        BUS_SOURCE,
        detail=str(exception),
    )


def complete_bus_reconnect_diagnostics(session):
    manager = session.diagnostic_manager
    _resolve_if_active(manager, BUS_CONNECTION_LOST)
    _resolve_if_active(manager, BUS_RECONNECT_FAILED)
    _resolve_if_active(manager, BUS_PROCESS_DATA_INCOMPLETE)
    for status in tuple(manager.active_statuses()):
        if status.definition.code == AXIS_RESTART_FAILED.code:
            manager.resolve(AXIS_RESTART_FAILED.code, status.source)
    manager.acknowledge_faults(source=BUS_SOURCE)


def restart_axis_runtime(runtime, state, axis_index):
    session = session_from_state(state)
    if runtime is None or session.runtime is not runtime:
        raise CommunicationException("axis_restart")
    if state.get("recovery_in_progress"):
        raise CommunicationException("recovery_in_progress")

    axis_index = int(axis_index)
    source = DiagnosticSource(DiagnosticSourceType.AXIS, axis_index)
    timeout = float(state["axis_restart_timeout"])
    deadline = time.monotonic() + timeout
    manager = session.diagnostic_manager
    state["recovery_in_progress"] = "axis_restart"
    session.set_runtime_state(ServerRuntimeState.FAULT)
    operational = False
    try:
        runtime.close()
        _connect_until(runtime, deadline)
        _restore_process_image(
            runtime,
            state,
            recovery_type=RecoveryType.AXIS_RESTART,
            refresh_axes=(axis_index,),
            deadline=deadline,
        )
        operational = True
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Axis restart exceeded {timeout:.3f} seconds"
            )
    except Exception as exception:
        if not operational:
            try:
                runtime.close()
            except Exception:
                pass
        manager.detect(
            AXIS_RESTART_FAILED,
            source,
            detail=str(exception),
        )
        session.set_runtime_state(
            ServerRuntimeState.FAULT
            if operational
            else ServerRuntimeState.BUS_DISCONNECTED
        )
        raise CommunicationException("axis_restart") from exception
    finally:
        state["recovery_in_progress"] = None

    if manager.status_for(AXIS_RESTART_FAILED.code, source) is not None:
        status = manager.resolve(AXIS_RESTART_FAILED.code, source)
        manager.acknowledge(status.diagnostic_id)
    session.set_runtime_state(ServerRuntimeState.NORMAL)
    return {
        "axis": axis_index,
        "elapsed": max(0.0, time.monotonic() - (deadline - timeout)),
        "message": "Axis restart completed.",
    }


def _connect_until(runtime, deadline):
    last_exception = None
    while True:
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                raise TimeoutError("EtherCAT device rediscovery timed out")
            runtime.connect(target_state="preop", timeout_s=remaining)
            return
        except Exception as exception:
            last_exception = exception
            try:
                runtime.close()
            except Exception:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError("EtherCAT device rediscovery timed out") from last_exception
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))


def _restore_process_image(
    runtime,
    state,
    *,
    recovery_type,
    refresh_axes,
    deadline,
):
    clear_axis_restart_commands(runtime)
    write_csp_interpolation_modes(
        runtime,
        state["csp_interpolation_modes"],
    )
    for axis_index, mode_name in enumerate(state["motion_modes"]):
        profile = axis_device_profile(runtime, axis_index)
        mode_code = profile.mode_code(mode_name)
        runtime.slaves[axis_index].rxpdo.mode_of_operation = mode_code
        profile.configure_mode_code(runtime, axis_index, mode_code)
    try:
        # SDO refresh must finish in PRE-OP. Performing these blocking reads
        # after OP would pause cyclic PDO long enough to trip slave watchdogs.
        refresh_after_recovery(runtime, recovery_type, refresh_axes)
    except Exception as exception:
        raise RecoveryRefreshException from exception
    remaining = deadline - time.monotonic()
    if remaining <= 0.0:
        raise TimeoutError("EtherCAT operational transition timed out")
    runtime.enter_operational(timeout_s=remaining)
    _wait_for_stable_processdata(runtime, deadline)
    runtime.sync_trajectory_to_actual_positions()


def _wait_for_stable_processdata(
    runtime,
    deadline,
    stable_cycles=RECOVERY_WKC_STABLE_CYCLES,
):
    required_cycles = max(1, int(stable_cycles))
    consecutive_cycles = 0
    actual_wkc = int(getattr(runtime, "wkc", 0))
    expected_wkc = int(runtime.expected_wkc())

    while time.monotonic() < deadline:
        exchange(runtime, cycles=1)
        actual_wkc = int(runtime.wkc)
        expected_wkc = int(runtime.expected_wkc())
        if expected_wkc > 0 and actual_wkc == expected_wkc:
            consecutive_cycles += 1
            if consecutive_cycles >= required_cycles:
                return
        else:
            consecutive_cycles = 0

    raise TimeoutError(
        "EtherCAT process data did not stabilize before recovery timeout. "
        f"WKC={actual_wkc}/{expected_wkc} "
        f"required_cycles={required_cycles}"
    )
