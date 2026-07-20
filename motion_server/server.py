import os
from pathlib import Path
import select
import socket
import sys
import time

PROJECT_ROOT = Path(
    os.environ.get("AXIS_SERVER_PROJECT_ROOT", Path(__file__).resolve().parents[1])
).resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from motion_server.config import (
    CYCLE_STATS_LOGS,
    CYCLE_STATS_PERIOD,
    FEEDBACK_PERIOD,
    parse_args,
)
from motion_server.commands.homing import update_homing_state
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
    record_tx_history,
)
from motion_server.drive.diagnostics import default_diagnostics
from motion_server.app.startup import (
    create_axis_runtime,
    initialize_drive,
    read_axis_converting_unit_exponents,
    read_axis_user_position_units,
)
from motion_server.commands.trajectory import (
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
from motion_server.api.dispatcher import dispatch_message
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

def run_server_loop(server, runtime, state):
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
        record_tx_history(runtime, state, cycle_stats)
        update_homing_state(runtime, state)
        log_csp_command_step_anomalies(runtime, state)
        log_position_feedback_lag(runtime, state)
        log_velocity_anomalies(runtime, state, cycle_stats)

        if not dc_absolute_shift:
            next_cycle_time += runtime.cycle_time + dc_phase_lock.correction()
            if cycle_start_time - next_cycle_time > runtime.cycle_time:
                next_cycle_time = cycle_start_time + runtime.cycle_time

        now = time.monotonic()
        if clients and now - last_feedback_update_time >= FEEDBACK_PERIOD:
            update_derived_velocities(runtime, state, now)
            last_feedback_update_time = now

        if (
            CYCLE_STATS_LOGS
            and CYCLE_STATS_PERIOD > 0.0
            and now - last_cycle_stats_log_time >= CYCLE_STATS_PERIOD
        ):
            report = cycle_stats.report_and_reset()
            if report:
                print(f"EtherCAT cycle stats: {report}", flush=True)
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
                print(
                    f"Client connected: id={client['id']} addr={addr}",
                    flush=True,
                )
            except BlockingIOError:
                break

        for client in list(clients):
            try:
                if not service_client(client, runtime, state, dispatch_message):
                    close_client(client, state)
                    clients.remove(client)
                    continue
                send_feedback_if_due(client, runtime, state)
            except OSError as exc:
                print(
                    f"Client connection error: id={client['id']} error={exc}",
                    flush=True,
                )
                close_client(client, state)
                clients.remove(client)

        last_status_log_time = log_status_if_due(
            runtime,
            state,
            last_status_log_time,
        )


def run_degraded_server_loop(server, runtime, state):
    server.setblocking(False)
    clients = []
    next_client_id = 1
    last_status_log_time = time.monotonic()

    print(
        "Axis server is running in initialization-error state: "
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
            print(f"Client connected: id={client['id']} addr={addr}", flush=True)

        for client in list(clients):
            try:
                if not service_client(client, runtime, state, dispatch_message):
                    close_client(client, state)
                    clients.remove(client)
                    continue
                send_feedback_if_due(client, runtime, state)
            except (ConnectionError, OSError, json.JSONDecodeError) as exc:
                print(
                    f"Client error: id={client['id']} error={exc}",
                    flush=True,
                )
                close_client(client, state)
                clients.remove(client)

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


def main():
    args = parse_args()
    if args.list_adapters:
        list_adapters()
        return

    if args.axis_count < 1:
        raise ValueError("PYSOEM_BUS must contain at least one motion axis")

    motion_limits = [
        {
            "max_velocity": args.max_velocity,
            "acceleration": args.acceleration,
            "deceleration": args.deceleration,
            "jerk": args.jerk,
        }
        for _ in range(args.axis_count)
    ]
    runtime = create_axis_runtime(args, motion_limits)

    try:
        drive_initialized = False
        try:
            initialize_drive(
                runtime,
                args.motion_mode,
                args.csp_interpolation_mode,
            )
            drive_initialized = True
        except Exception as exc:
            initialization_error = str(exc)
            print(
                "Drive initialization failed; keeping Axis Server online: "
                f"{initialization_error}",
                flush=True,
            )
            runtime.close()
            runtime.last_diagnostics = default_diagnostics(
                args.axis_count,
                initialization_error,
            )
            software_position_limits = [
                [0.0, 0.0]
                for _ in range(args.axis_count)
            ]
            profile_settings = None
            read_motion_limits_state = None
            user_position_units = None
            converting_unit_exponents = None
            positions = [0.0 for _ in range(args.axis_count)]
            state = initial_server_state(
                args,
                runtime.drive_manager,
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
                args.axis_count,
                "Panel SDO read pending",
            )
            software_position_limits = [
                [-1000000, 1000000]
                for _ in range(args.axis_count)
            ]
            profile_settings = [
                [
                    args.max_velocity,
                    args.acceleration,
                    args.deceleration,
                    args.pp_jerk,
                ]
                for _ in range(args.axis_count)
            ]
            read_motion_limits_state = [
                [
                    args.max_velocity,
                    -abs(args.max_velocity),
                    args.acceleration,
                    args.deceleration,
                ]
                for _ in range(args.axis_count)
            ]
            user_position_units = read_axis_user_position_units(runtime)
            converting_unit_exponents = read_axis_converting_unit_exponents(runtime)
            unit_state = {
                "drive_manager": runtime.drive_manager,
                "position_counts_per_unit": (
                    args.csp_counts_per_unit
                    if args.backend == "pysoem"
                    else 1.0
                ),
            }
            runtime.drive_manager.configure_unit_conversion(
                user_position_units,
                converting_unit_exponents,
                unit_state["position_counts_per_unit"],
            )
            axis_metadata = runtime.drive_manager.unit_metadata()
            unit_state["axis_metadata"] = axis_metadata
            axis_position_scales = axis_position_counts_per_api_units(
                unit_state,
                args.axis_count,
            )
            for axis_index, scale in enumerate(axis_position_scales):
                if hasattr(runtime, "set_axis_csp_counts_per_unit"):
                    runtime.set_axis_csp_counts_per_unit(axis_index, scale)
            profile_settings = [
                [
                    axis_motion_api_to_drive(unit_state, axis_index, args.max_velocity),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        args.acceleration,
                        "acceleration",
                    ),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        args.deceleration,
                        "deceleration",
                    ),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        args.pp_jerk,
                        "jerk",
                    ),
                ]
                for axis_index in range(args.axis_count)
            ]
            read_motion_limits_state = [
                [
                    axis_motion_api_to_drive(unit_state, axis_index, args.max_velocity),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        -abs(args.max_velocity),
                    ),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        args.acceleration,
                        "acceleration",
                    ),
                    axis_motion_api_to_drive(
                        unit_state,
                        axis_index,
                        args.deceleration,
                        "deceleration",
                    ),
                ]
                for axis_index in range(args.axis_count)
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
                    args.jerk,
                )
            positions = actual_positions(runtime)
            print(
                "Drive initialized. "
                f"backend={args.backend} "
                f"axes={args.axis_count} "
                f"cycle_time={args.cycle_time} "
                f"spin_wait_time={args.spin_wait_time} "
                f"csp_counts_per_unit={args.csp_counts_per_unit} "
                f"csp_profile={args.csp_profile} "
                f"dc_phase_lock={args.dc_phase_lock} "
                f"dc_absolute_shift={args.dc_absolute_shift} "
                f"dc_phase_offset_ns={args.dc_phase_offset} "
                f"dc_phase_kp={args.dc_phase_kp} "
                f"dc_phase_ki={args.dc_phase_ki} "
                f"csp_interpolation_mode={args.csp_interpolation_mode} "
                f"csp_velocity_offset={args.csp_velocity_offset} "
                f"derived_velocity_alpha={args.derived_velocity_alpha} "
                f"statuswords={[f'0x{slave.txpdo.statusword:04X}' for slave in runtime.slaves]} "
                f"software_position_limits={software_position_limits} "
                f"AP={positions}",
                flush=True,
            )
            state = initial_server_state(
                args,
                runtime.drive_manager,
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
                else args.csp_counts_per_unit
            )

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((args.host, args.port))
            server.listen(1)
            print(
                f"Axis server listening on {args.host}:{args.port} "
                f"backend={args.backend} axes={args.axis_count}",
                flush=True,
            )
            if drive_initialized:
                run_server_loop(server, runtime, state)
            else:
                run_degraded_server_loop(server, runtime, state)

    finally:
        runtime.close()


if __name__ == "__main__":
    main()
