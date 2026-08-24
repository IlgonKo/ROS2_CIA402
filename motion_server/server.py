import json
import os
from pathlib import Path
import select
import socket
import sys
import time

PROJECT_ROOT = Path(
    os.environ.get("MOTION_SERVER_PROJECT_ROOT", Path(__file__).resolve().parents[1])
).resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from configuration import CmmtDeviceConfig
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
from motion_server.diagnostic import DiagnosticManager
from motion_server.diagnostic.startup import (
    detect_initialization_fault,
    resolve_initialization_fault,
)
from motion_server.diagnostic.runtime import RuntimeDiagnosticMonitor
from motion_server.app.startup import (
    create_axis_runtime,
    initialize_drive,
    read_startup_axis_sdo,
)
from motion_server.handlers.command.trajectory import (
    update_active as update_active_trajectory,
)
from motion_server.app.state_updates import update_derived_velocities
from motion_server.control.axis_operations import (
    actual_positions,
    hold_faulted_axes,
)
from motion_server.api import (
    require_uint32,
)
from motion_server.api.router import dispatch_message
from motion_server.app.state import (
    initial_server_state,
)
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

def run_server_loop(server, runtime, state, server_config):
    server.setblocking(False)
    clients = []
    last_feedback_update_time = 0.0
    last_status_log_time = 0.0
    cycle_stats = CycleStats()
    last_cycle_start_time = None
    last_cycle_stats_log_time = time.monotonic()
    next_cycle_time = time.monotonic()
    spin_wait_time = float(state.get("spin_wait_time", 0.0))
    dc_phase_lock_enabled = bool(state.get("dc_phase_lock", False))
    dc_absolute_shift = (
        dc_phase_lock_enabled
        and bool(state.get("dc_absolute_shift", False))
    )
    dc_phase_lock = DcPhaseLock(
        dc_phase_lock_enabled,
        runtime.cycle_time,
        state.get("dc_phase_offset_ns", 800000),
        state.get("dc_phase_kp", 0.05),
        state.get("dc_phase_ki", 0.0005),
        state.get("dc_phase_max_correction", 0.001),
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
        log_velocity_anomalies(runtime, state, cycle_stats)

        if not dc_absolute_shift:
            next_cycle_time += runtime.cycle_time + dc_phase_lock.correction()
            if cycle_start_time - next_cycle_time > runtime.cycle_time:
                next_cycle_time = cycle_start_time + runtime.cycle_time

        now = time.monotonic()
        if (
            clients
            and now - last_feedback_update_time >= server_config.feedback_period
        ):
            update_derived_velocities(runtime, state, now)
            last_feedback_update_time = now

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
            return action

        last_status_log_time = log_status_if_due(
            runtime,
            state,
            last_status_log_time,
        )


def run_degraded_server_loop(server, runtime, state, server_config):
    server.setblocking(False)
    clients = []
    next_client_id = 1
    last_status_log_time = time.monotonic()

    print(
        "Motion Server is running in initialization-error state: "
        f"{state.get('initialization_error', '')}",
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
            runtime.logger.status(
                f"Client connected: id={client['id']} addr={addr}"
            )

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
            except (ConnectionError, OSError, json.JSONDecodeError) as exc:
                print(
                    f"Client error: id={client['id']} error={exc}",
                    flush=True,
                )
                close_client(client, runtime, state)
                clients.remove(client)

        action = requested_server_action(state)
        if action is not None:
            return action

        last_status_log_time = log_status_if_due(
            runtime,
            state,
            last_status_log_time,
        )

# Main Entry

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


def run_main_once(diagnostic_manager=None, config=None):
    if config is None:
        raise TypeError("config must be a MotionServerConfig")
    if config.axis_count < 1:
        raise ValueError("MOTION_SERVER_BUS must contain at least one motion axis")

    limits = config.motion.default_limits
    motion_limits = [
        {
            "max_velocity": limits.max_velocity,
            "acceleration": limits.acceleration,
            "deceleration": limits.deceleration,
            "jerk": limits.jerk,
        }
        for _ in range(config.axis_count)
    ]
    runtime = create_axis_runtime(
        config.ethercat,
        config.motion,
        config.logging,
        config.devices,
        motion_limits,
    )
    if diagnostic_manager is not None:
        runtime.diagnostic_manager = diagnostic_manager

    cmmt_devices = [
        device.device
        for device in config.devices
        if isinstance(device.device, CmmtDeviceConfig)
    ]
    if not cmmt_devices:
        raise ValueError("Motion Server configuration contains no CMMT axis")
    csp_interpolation_mode = int(cmmt_devices[0].csp_interpolation_mode)

    try:
        drive_initialized = False
        try:
            startup_sdo = initialize_drive(
                runtime,
                config.motion.initial_motion_mode,
                csp_interpolation_mode,
                read_startup_axis_sdo,
            )
            drive_initialized = True
        except Exception as exc:
            detect_initialization_fault(runtime)
            initialization_error = str(exc)
            print(
                "Drive initialization failed; keeping Motion Server online: "
                f"{initialization_error}",
                flush=True,
            )
            runtime.close()
            runtime.last_diagnostics = default_diagnostics(
                config.axis_count,
                initialization_error,
            )
            software_position_limits = [
                [0.0, 0.0]
                for _ in range(config.axis_count)
            ]
            profile_settings = None
            read_motion_limits_state = None
            user_position_units = None
            converting_unit_exponents = None
            positions = [0.0 for _ in range(config.axis_count)]
            state = initial_server_state(
                config.server,
                config.ethercat,
                config.motion,
                config.axis_count,
                runtime.device_manager.axes,
                positions,
                software_position_limits,
                profile_settings=profile_settings,
                motion_limits=read_motion_limits_state,
                user_position_units=user_position_units,
                converting_unit_exponents=converting_unit_exponents,
                initialized=False,
                initialization_error=initialization_error,
            )
        else:
            runtime.last_diagnostics = default_diagnostics(
                config.axis_count,
                "Panel SDO read pending",
            )
            default_software_position_limits = [
                [-1000000, 1000000]
                for _ in range(config.axis_count)
            ]
            software_position_limits = startup_sdo.get(
                "software_position_limits",
                None,
            ) or default_software_position_limits
            startup_profile_settings = startup_sdo.get("profile_settings", None)
            startup_motion_limits = startup_sdo.get("motion_limits", None)
            user_position_units = startup_sdo.get("user_position_units")
            converting_unit_exponents = startup_sdo.get("converting_unit_exponents")
            unit_state = {
                "axis_devices": runtime.device_manager.axes,
            }
            runtime.device_manager.axes.configure_unit_conversion(
                user_position_units,
                converting_unit_exponents,
            )
            axis_metadata = runtime.device_manager.axes.unit_metadata()
            unit_state["axis_metadata"] = axis_metadata
            axis_position_scales = axis_position_counts_per_api_units(
                unit_state,
                config.axis_count,
            )
            for axis_index, scale in enumerate(axis_position_scales):
                runtime.set_axis_position_counts_per_api_unit(
                    axis_index,
                    scale,
                )
            default_profile_settings = [
                [
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        limits.max_velocity,
                    ),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        limits.acceleration,
                        "acceleration",
                    ),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        limits.deceleration,
                        "deceleration",
                    ),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        limits.pp_jerk,
                        "jerk",
                    ),
                ]
                for axis_index in range(config.axis_count)
            ]
            profile_settings = [
                values if values is not None else default_profile_settings[axis_index]
                for axis_index, values in enumerate(
                    startup_profile_settings or default_profile_settings
                )
            ]
            default_motion_limits_state = [
                [
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        limits.max_velocity,
                    ),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        -abs(limits.max_velocity),
                    ),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        limits.acceleration,
                        "acceleration",
                    ),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        limits.deceleration,
                        "deceleration",
                    ),
                ]
                for axis_index in range(config.axis_count)
            ]
            read_motion_limits_state = [
                values if values is not None else default_motion_limits_state[axis_index]
                for axis_index, values in enumerate(
                    startup_motion_limits or default_motion_limits_state
                )
            ]
            for axis_index, axis_profile_settings in enumerate(profile_settings):
                slave = runtime.slaves[axis_index]
                if slave.rxpdo.has_field("profile_velocity"):
                    slave.rxpdo.profile_velocity = require_uint32(
                        axis_profile_settings[0],
                        f"axis {axis_index} profile_velocity",
                    )
            for axis_index, axis_limits in enumerate(read_motion_limits_state):
                runtime.slaves[axis_index].motion_server_motion_limits = list(axis_limits)
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
                    limits.jerk,
                )
            positions = actual_positions(runtime)
            dc_summary = f"dc_enabled={config.ethercat.dc.enabled}"
            if config.ethercat.dc.enabled:
                dc_summary += (
                    f" dc_phase_lock={config.ethercat.dc.phase_lock}"
                    f" dc_absolute_shift={config.ethercat.dc.absolute_shift}"
                )
            print(
                "Drive initialized. "
                f"backend={config.ethercat.backend.value} "
                f"axes={config.axis_count} "
                f"cycle_time={config.ethercat.cycle.period} "
                f"spin_wait_time={config.ethercat.cycle.spin_wait_time} "
                f"axis_position_counts_per_api_unit={axis_position_scales} "
                f"csp_profile={config.motion.csp_profile.value} "
                f"{dc_summary} "
                f"csp_interpolation_mode={csp_interpolation_mode}",
                flush=True,
            )
            state = initial_server_state(
                config.server,
                config.ethercat,
                config.motion,
                config.axis_count,
                runtime.device_manager.axes,
                positions,
                software_position_limits,
                profile_settings=profile_settings,
                motion_limits=read_motion_limits_state,
                user_position_units=user_position_units,
                converting_unit_exponents=converting_unit_exponents,
                axis_metadata=axis_metadata,
                initialized=True,
            )
            state["axis_position_counts_per_unit"] = axis_position_scales
            state["position_counts_per_unit"] = (
                axis_position_scales[0]
                if axis_position_scales
                else 1.0
            )
            resolve_initialization_fault(runtime)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((config.server.host, config.server.port))
            server.listen(1)
            print(
                f"Motion Server listening on {config.server.host}:{config.server.port} "
                f"backend={config.ethercat.backend.value} axes={config.axis_count}",
                flush=True,
            )
            if drive_initialized:
                action = run_server_loop(server, runtime, state, config.server)
            else:
                action = run_degraded_server_loop(
                    server,
                    runtime,
                    state,
                    config.server,
                )

            if action == "restart":
                raise ServerRestartRequested
            if action == "reset":
                raise ServerResetRequested
            if action == "bus_reconnect":
                raise ServerResetRequested

    finally:
        runtime.close()


def main(config, diagnostic_manager=None):
    diagnostic_manager = diagnostic_manager or DiagnosticManager()
    while True:
        try:
            run_main_once(diagnostic_manager, config=config)
            return
        except ServerResetRequested:
            print(
                "Motion Server runtime reinitialization requested; "
                "reinitializing runtime and bus.",
                flush=True,
            )
            continue
        except ServerRestartRequested:
            print(
                "Motion Server restart requested; restarting process.",
                flush=True,
            )
            restart_current_process()


if __name__ == "__main__":
    main()
