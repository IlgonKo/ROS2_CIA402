import json
import select
import socket
import time
from datetime import datetime, timezone

from configuration.models import CmmtDeviceConfig
from motion_server.handlers.command.homing import update_homing_state
from motion_server.app.cycle import CycleStats, exchange, wait_until_cycle_time
from motion_server.control.axis_units import (
    axis_motion_api_to_drive,
    axis_position_counts_per_api_units,
    motion_limits_drive_to_api,
)
from motion_server.app.cycle_diagnostics import (
    log_csp_command_step_anomalies,
    log_position_feedback_lag,
    log_status_if_due,
    log_velocity_anomalies,
    record_pre_log_snapshot,
)
from motion_server.device_manager.axis_diagnostics import default_diagnostics
from motion_server.diagnostic.startup import (
    detect_initialization_fault,
    resolve_initialization_fault,
)
from motion_server.diagnostic.runtime import RuntimeDiagnosticMonitor
from motion_server.app.startup import (
    build_device_models,
    close_initialization_resource,
    connect_bus,
    create_axis_runtime,
    initialize_drive,
    read_startup_axis_sdo,
)
from motion_server.app.initialization import (
    InitializationStage,
    initialization_failure_from_exception,
    log_initialization_failure,
)
from motion_server.handlers.command.trajectory import (
    update_active as update_active_trajectory,
)
from motion_server.control.axis_operations import (
    actual_positions,
    hold_faulted_axes,
)
from motion_server.api.router import dispatch_message
from motion_server.app.state import (
    initial_degraded_state,
    initial_server_state,
)
from motion_server.app.session import ServerSession
from motion_server.app.client_transport import (
    allocate_client_id,
    close_client,
    send_feedback_if_due,
    service_client,
)
from device import get_device_profile
from ethercat.distributed_clock import (
    DcCycleScheduler,
    DcPhaseLock,
)
from ethercat.pysoem_master import PySOEMMaster

# Server Loops


class ServerResetRequested(Exception):
    pass


class ServerRestartRequested(Exception):
    pass


class BusReconnectRequested(Exception):
    pass


def requested_server_action(state):
    if state.get("server_restart_requested"):
        return "restart"
    if state.get("bus_reconnect_requested"):
        requested_at = state.get("bus_reconnect_requested_at", None)
        if requested_at is not None and time.monotonic() < float(requested_at):
            return None
        return "bus_reconnect"
    if state.get("server_reset_requested"):
        return "reset"
    return None

def run_server_loop(server, runtime, state, server_config, ethercat_config):
    server.setblocking(False)
    clients = []
    last_status_log_time = 0.0
    cycle_stats = CycleStats()
    last_cycle_start_time = None
    last_cycle_stats_log_time = time.monotonic()
    next_cycle_time = time.monotonic()
    spin_wait_time = ethercat_config.cycle.spin_wait_time
    dc_phase_lock_enabled = bool(
        ethercat_config.dc.enabled and ethercat_config.dc.phase_lock
    )
    dc_absolute_shift = (
        dc_phase_lock_enabled
        and ethercat_config.dc.absolute_shift
    )
    dc_phase_lock = DcPhaseLock(
        dc_phase_lock_enabled,
        runtime.cycle_time,
        ethercat_config.dc.phase_offset_ns,
        ethercat_config.dc.phase_kp,
        ethercat_config.dc.phase_ki,
        ethercat_config.dc.phase_max_correction,
    )
    dc_cycle_scheduler = DcCycleScheduler(dc_phase_lock)
    diagnostic_monitor = RuntimeDiagnosticMonitor(runtime.diagnostic_manager)

    while True:
        if dc_absolute_shift:
            hold_faulted_axes(runtime, state)
            update_active_trajectory(runtime, state)
            runtime.prepare_processdata()

            next_cycle_time, dc_schedule_wait = (
                dc_cycle_scheduler.absolute_cycle_deadline(runtime)
            )
            cycle_stats.add("dc_schedule_wait", dc_schedule_wait)

        wait_until_cycle_time(next_cycle_time, spin_wait_time)

        cycle_start_time = time.monotonic()
        if last_cycle_start_time is not None:
            cycle_stats.add("loop", cycle_start_time - last_cycle_start_time)
        last_cycle_start_time = cycle_start_time
        deadline_late = cycle_start_time - next_cycle_time
        if deadline_late > 0.0:
            cycle_stats.add("deadline_late", deadline_late)

        if dc_absolute_shift:
            exchange_start = time.monotonic()
            cycle_stats.add_tx_time(exchange_start)
            runtime.send_processdata()
            runtime.last_tx_dc_time_ns = (
                dc_cycle_scheduler.estimate_transmit_dc_time_ns(runtime)
            )
            runtime.receive_processdata()
            exchange_done = time.monotonic()
            cycle_stats.add("pdo_io", exchange_done - exchange_start)
            cycle_stats.add("exchange", exchange_done - exchange_start)
        else:
            hold_faulted_axes(runtime, state)
            update_active_trajectory(runtime, state)
            exchange(
                runtime,
                cycle_stats=cycle_stats,
                sleep_after=False,
                dc_cycle_scheduler=dc_cycle_scheduler,
            )

        diagnostic_monitor.update(runtime)

        direct_tx_dc_time_ns = getattr(runtime, "last_direct_tx_dc_time_ns", None)
        estimated_tx_dc_time_ns = getattr(runtime, "last_tx_dc_time_ns", None)
        if direct_tx_dc_time_ns is not None and estimated_tx_dc_time_ns is not None:
            cycle_stats.add(
                "dc_tx_estimation_delta",
                (estimated_tx_dc_time_ns - direct_tx_dc_time_ns) / 1_000_000_000.0,
            )
        tx_prepare_duration_ns = getattr(runtime, "last_tx_prepare_duration_ns", None)
        if tx_prepare_duration_ns is not None:
            cycle_stats.add("tx_prepare", tx_prepare_duration_ns / 1_000_000_000.0)
        send_call_duration_ns = getattr(runtime, "last_send_call_duration_ns", None)
        if send_call_duration_ns is not None:
            cycle_stats.add("send_call", send_call_duration_ns / 1_000_000_000.0)
        dc_phase_lock.update(getattr(runtime, "last_tx_dc_time_ns", None), cycle_stats)
        record_pre_log_snapshot(runtime, state, cycle_stats)
        update_homing_state(runtime, state)
        log_csp_command_step_anomalies(runtime, state)
        log_position_feedback_lag(runtime, state)
        log_velocity_anomalies(
            runtime,
            state,
            cycle_stats,
            ethercat_config.dc,
        )

        if not dc_absolute_shift:
            next_cycle_time += runtime.cycle_time + dc_phase_lock.correction()
            if cycle_start_time - next_cycle_time > runtime.cycle_time:
                next_cycle_time = cycle_start_time + runtime.cycle_time

        now = time.monotonic()
        if (
            runtime.logger.config.cycle_stats.enabled
            and runtime.logger.config.cycle_stats.period > 0.0
            and now - last_cycle_stats_log_time
            >= runtime.logger.config.cycle_stats.period
        ):
            report = cycle_stats.report_and_reset()
            if report:
                runtime.logger.event(f"EtherCAT cycle stats: {report}")
            last_cycle_stats_log_time = now

        while True:
            try:
                conn, addr = server.accept()
                conn.setblocking(False)
                client_id = allocate_client_id(clients)
                client = {
                    "id": client_id,
                    "addr": addr,
                    "conn": conn,
                    "buffer": "",
                    "last_feedback_time": 0.0,
                }
                clients.append(client)
                runtime.logger.status(
                    f"Client connected: id={client['id']} addr={addr}",
                )
            except BlockingIOError:
                break

        for client in list(clients):
            try:
                if not service_client(client, runtime, state, dispatch_message):
                    close_client(client, runtime, state)
                    clients.remove(client)
                    continue
                send_feedback_if_due(
                    client,
                    runtime,
                    state,
                    server_config.feedback_period,
                )
            except OSError as exc:
                print(
                    f"Client connection error: id={client['id']} error={exc}",
                    flush=True,
                )
                close_client(client, runtime, state)
                clients.remove(client)

        action = requested_server_action(state)
        if action is not None:
            for client in clients:
                close_client(client, runtime, state)
            return action

        last_status_log_time = log_status_if_due(
            runtime,
            state,
            last_status_log_time,
        )


def run_degraded_server_loop(server, state):
    server.setblocking(False)
    clients = []
    next_client_id = 1
    print(
        "Motion Server degraded server loop is active.",
        flush=True,
    )

    while True:
        readable, _, _ = select.select([server], [], [], 0.05)
        if server in readable:
            conn, addr = server.accept()
            conn.setblocking(False)
            client = {
                "id": next_client_id,
                "conn": conn,
                "addr": addr,
                "buffer": "",
                "last_feedback_time": 0.0,
            }
            clients.append(client)
            next_client_id += 1
            print(f"Client connected: id={client['id']} addr={addr}", flush=True)

        for client in list(clients):
            try:
                if not service_client(client, None, state, dispatch_message):
                    close_client(client, None, state)
                    clients.remove(client)
                    continue
            except (ConnectionError, OSError, json.JSONDecodeError) as exc:
                print(
                    f"Client error: id={client['id']} error={exc}",
                    flush=True,
                )
                close_client(client, None, state)
                clients.remove(client)

        action = requested_server_action(state)
        if action is not None:
            for client in clients:
                close_client(client, None, state)
            return action


# Main Entry

MOTION_SERVER_BIND_HOST = "0.0.0.0"

def list_adapters():
    loader = PySOEMMaster(
        "unused",
        device_profiles=[get_device_profile("cmmt")],
    )
    pysoem = loader._load_pysoem()
    for adapter in pysoem.find_adapters():
        print(f"name={adapter.name}")
        print(f"desc={adapter.desc}")
        print()


def restart_current_process():
    os.execv(sys.executable, [sys.executable, *sys.argv])


def initialize_runtime_session(
    session,
    *,
    ethercat_config,
    motion_config,
    logging_config,
    devices,
):
    runtime = None
    stage = InitializationStage.DEVICE_MODEL_BUILD
    try:
        axis_count_value = sum(device.role.value == "axis" for device in devices)
        device_profiles = build_device_models(devices)
        cmmt_devices = [
            device.device
            for device in devices
            if isinstance(device.device, CmmtDeviceConfig)
        ]
        if not cmmt_devices:
            raise ValueError("Motion Server configuration contains no CMMT axis")

        stage = InitializationStage.RUNTIME_CREATION
        runtime = create_axis_runtime(
            ethercat_config,
            motion_config,
            logging_config,
            devices,
            device_profiles=device_profiles,
        )
        session.attach_runtime(runtime)

        stage = InitializationStage.BUS_CONNECTION
        connect_bus(runtime)

        stage = InitializationStage.DEVICE_INITIALIZATION
        csp_interpolation_modes = tuple(
            motion_config.csp_interpolation_mode for _device in cmmt_devices
        )
        startup_sdo = initialize_drive(
            runtime,
            motion_config.initial_motion_mode,
            csp_interpolation_modes,
            read_startup_axis_sdo,
        )
    except Exception as exc:
        fail_runtime_initialization(session, runtime, stage, exc)
        return None, None

    return runtime, startup_sdo


def fail_runtime_initialization(session, runtime, stage, exception):
    failure = initialization_failure_from_exception(
        stage,
        exception,
        occurred_at=datetime.now(timezone.utc),
    )
    session.mark_failed(failure)
    detect_initialization_fault(session, at=failure.occurred_at)
    if runtime is not None:
        close_initialization_resource(runtime)
        if session.runtime is runtime:
            session.detach_runtime()
    log_initialization_failure(failure, exception)
    return failure


def build_initialized_server_state(
    session,
    runtime,
    startup_sdo,
    *,
    server_config,
    ethercat_config,
    motion_config,
    axis_count_value,
):
    runtime.last_diagnostics = default_diagnostics(
        axis_count_value,
        "Panel SDO read pending",
    )
    default_software_position_limits = [
        [-1000000, 1000000] for _ in range(axis_count_value)
    ]
    software_position_limits = startup_sdo.get(
        "software_position_limits",
        None,
    ) or default_software_position_limits
    profile_settings = startup_sdo.get("profile_settings")
    read_motion_limits_state = startup_sdo.get("motion_limits")
    user_position_units = startup_sdo.get("user_position_units")
    converting_unit_exponents = startup_sdo.get(
        "converting_unit_exponents"
    )
    unit_state = {"axis_devices": runtime.device_manager.axes}
    runtime.device_manager.axes.configure_unit_conversion(
        user_position_units,
        converting_unit_exponents,
    )
    axis_metadata = runtime.device_manager.axes.unit_metadata()
    for axis_index in range(axis_count_value):
        runtime.axis_parameters.update_axis(
            axis_index,
            user_position_unit=user_position_units[axis_index],
            converting_unit_exponents=converting_unit_exponents[axis_index],
            software_position_limits=software_position_limits[axis_index],
            profile_settings=profile_settings[axis_index],
            motion_limits=read_motion_limits_state[axis_index],
            axis_metadata=axis_metadata[axis_index],
        )
    unit_state["axis_metadata"] = axis_metadata
    axis_position_scales = axis_position_counts_per_api_units(
        unit_state,
        axis_count_value,
    )
    for axis_index, scale in enumerate(axis_position_scales):
        runtime.set_axis_position_counts_per_api_unit(axis_index, scale)
    for axis_index, axis_limits in enumerate(read_motion_limits_state):
        runtime.slaves[axis_index].motion_server_motion_limits = list(
            axis_limits
        )
        api_axis_limits = motion_limits_drive_to_api(
            unit_state,
            axis_index,
            axis_limits,
        )
        runtime.set_axis_motion_limits(
            axis_index,
            max(abs(api_axis_limits[0]), abs(api_axis_limits[1])),
            api_axis_limits[2],
            api_axis_limits[3],
            motion_config.csp_jerk,
        )
    positions = actual_positions(runtime)
    state = initial_server_state(
        server_config,
        motion_config,
        ethercat_config.backend.value == "mock",
        axis_count_value,
        runtime.device_manager.axes,
        positions,
        software_position_limits,
        profile_settings=profile_settings,
        motion_limits=read_motion_limits_state,
        user_position_units=user_position_units,
        converting_unit_exponents=converting_unit_exponents,
        axis_metadata=axis_metadata,
        server_session=session,
    )
    state["axis_position_counts_per_unit"] = axis_position_scales
    state["position_counts_per_unit"] = (
        axis_position_scales[0] if axis_position_scales else 1.0
    )
    return state


def run_main_once(
    session,
    *,
    server_config,
    ethercat_config,
    motion_config,
    logging_config,
    devices,
):
    if not isinstance(session, ServerSession):
        raise TypeError("run_main_once requires ServerSession")
    axis_count_value = sum(device.role.value == "axis" for device in devices)
    runtime, startup_sdo = initialize_runtime_session(
        session,
        ethercat_config=ethercat_config,
        motion_config=motion_config,
        logging_config=logging_config,
        devices=devices,
    )

    try:
        if runtime is None:
            state = initial_degraded_state(
                session,
                server_mode=server_config.mode.value,
            )
        else:
            try:
                state = build_initialized_server_state(
                    session,
                    runtime,
                    startup_sdo,
                    server_config=server_config,
                    ethercat_config=ethercat_config,
                    motion_config=motion_config,
                    axis_count_value=axis_count_value,
                )
            except Exception as exc:
                fail_runtime_initialization(
                    session,
                    runtime,
                    InitializationStage.DEVICE_INITIALIZATION,
                    exc,
                )
                runtime = None
                state = initial_degraded_state(
                    session,
                    server_mode=server_config.mode.value,
                )
            else:
                session.mark_ready()
                resolve_initialization_fault(session)
                state["initialization_status"] = session.initialization_status
                dc_summary = f"dc_enabled={ethercat_config.dc.enabled}"
                if ethercat_config.dc.enabled:
                    dc_summary += (
                        f" dc_phase_lock={ethercat_config.dc.phase_lock}"
                        f" dc_absolute_shift={ethercat_config.dc.absolute_shift}"
                    )
                print(
                    "Drive initialized. "
                    f"backend={ethercat_config.backend.value} "
                    f"axes={axis_count_value} "
                    f"cycle_time={ethercat_config.cycle.period} "
                    f"spin_wait_time={ethercat_config.cycle.spin_wait_time} "
                    "axis_position_counts_per_api_unit="
                    f"{state['axis_position_counts_per_unit']} "
                    f"csp_profile={motion_config.csp_profile.value} "
                    f"{dc_summary}",
                    flush=True,
                )

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((MOTION_SERVER_BIND_HOST, server_config.port))
            server.listen(1)
            print(
                f"Motion Server listening on {MOTION_SERVER_BIND_HOST}:{server_config.port} "
                f"backend={ethercat_config.backend.value} axes={axis_count_value}",
                flush=True,
            )
            action = (
                run_server_loop(
                    server, runtime, state, server_config, ethercat_config
                )
                if runtime is not None
                else run_degraded_server_loop(server, state)
            )
            raise_server_action(action)
    finally:
        owned_runtime = session.detach_runtime()
        if owned_runtime is not None:
            close_initialization_resource(owned_runtime)


def run_configuration_degraded_once(session, bootstrap_config):
    state = initial_degraded_state(session)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((MOTION_SERVER_BIND_HOST, bootstrap_config.port))
        server.listen(1)
        print(
            f"Motion Server listening on {MOTION_SERVER_BIND_HOST}:"
            f"{bootstrap_config.port} in configuration-error state",
            flush=True,
        )
        raise_server_action(run_degraded_server_loop(server, state))


def raise_server_action(action):
    if action == "restart":
        raise ServerRestartRequested
    if action == "reset":
        raise ServerResetRequested
    if action == "bus_reconnect":
        raise BusReconnectRequested
