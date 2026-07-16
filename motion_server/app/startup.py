import time

from motion_server.config import (
    DEVICE_PROFILE,
    require_pdo_fields_for_mode,
    require_txpdo_fields,
)
from motion_server.app.cycle import exchange
from motion_server.control.axis_operations import (
    axis_count,
    configure_motion_mode,
    faulted_axes,
    pv_reject_message,
)
from motion_server.app.runtime import AxisRuntime
from device import available_device_names, get_device_profile
from device.cmmt.virtual_servo import VirtualCiA402Servo
from motion_server.drive import DriveBinding, DriveManager
from ethercat.mock_master import MockMaster
from ethercat.mock_slave import MockSlave
from ethercat.pysoem_master import PySOEMMaster
from motion_server.control.axis import Axis
from motion_server.control.motion_controller import MotionController


def create_axis_runtime(args, motion_limits):
    sync_mode = parse_optional_sync_mode(args.sync_mode)
    device_profile_names = parse_device_profile_names(args)
    axis_slave_indices = parse_axis_slave_indices(
        args,
        len(device_profile_names),
    )
    drive_bindings = [
        DriveBinding(axis_index=axis_index, slave_index=slave_index)
        for axis_index, slave_index in enumerate(axis_slave_indices)
    ]

    if args.backend == "mock":
        if axis_slave_indices != list(range(args.axis_count)) or (
            len(device_profile_names) != args.axis_count
        ):
            raise ValueError(
                "mock backend supports only one-to-one axis/slave mapping"
            )
        slaves = []
        for axis_index, limits in enumerate(motion_limits):
            servo = VirtualCiA402Servo(cycle_time=args.cycle_time)
            servo.set_motion_limits(
                limits["max_velocity"],
                limits["acceleration"],
                limits["deceleration"],
            )
            axis = Axis(f"A{axis_index}", servo)
            slaves.append(MockSlave(axis))

        ethercat_master = MockMaster(
            slaves,
            cycle_time=args.cycle_time,
        )
        motion_controller = MotionController(
            args.axis_count,
            args.cycle_time,
            motion_limits=motion_limits,
            csp_counts_per_unit=args.csp_counts_per_unit,
            csp_velocity_offset_enabled=args.csp_velocity_offset,
            csp_command_step_threshold=args.csp_command_step_threshold,
            csp_command_step_error_threshold=args.csp_command_step_error_threshold,
            csp_profile=args.csp_profile,
        )
        for axis_index, limits in enumerate(motion_limits):
            motion_controller.set_axis_motion_limits(
                axis_index,
                limits["max_velocity"],
                limits["acceleration"],
                limits["deceleration"],
                limits["jerk"],
            )
        drive_manager = DriveManager(ethercat_master, drive_bindings)
        runtime = AxisRuntime(drive_manager, motion_controller)
        require_pdo_fields_for_mode(runtime, args.motion_mode)
        require_txpdo_fields(runtime)
        return runtime

    ethercat_master = PySOEMMaster(
        interface_name=args.interface,
        device_profiles=[
            get_device_profile(name)
            for name in device_profile_names
        ],
        cycle_time=args.cycle_time,
        sync_mode=sync_mode,
        dc_enabled=args.dc_enabled,
        dc_sync0_shift_time=args.dc_sync0_shift_time,
        txpdo_setpoint_entry=args.txpdo_setpoint_entry,
    )
    motion_controller = MotionController(
        args.axis_count,
        args.cycle_time,
        motion_limits=motion_limits,
        csp_counts_per_unit=args.csp_counts_per_unit,
        csp_velocity_offset_enabled=args.csp_velocity_offset,
        csp_command_step_threshold=args.csp_command_step_threshold,
        csp_command_step_error_threshold=args.csp_command_step_error_threshold,
        csp_profile=args.csp_profile,
    )
    drive_manager = DriveManager(ethercat_master, drive_bindings)
    return AxisRuntime(drive_manager, motion_controller)


def parse_device_profile_names(args):
    raw_value = str(getattr(args, "device_profiles", "")).strip()
    names = (
        [part.strip().lower() for part in raw_value.split(",")]
        if raw_value
        else [str(args.device).strip().lower()] * int(args.axis_count)
    )
    if not names or any(not name for name in names):
        raise ValueError("--device-profiles contains an empty profile name")

    available = set(available_device_names())
    unsupported = [name for name in names if name not in available]
    if unsupported:
        raise ValueError(
            "Unsupported device profiles: " + ", ".join(unsupported)
        )
    return names


def parse_axis_slave_indices(args, device_count):
    raw_value = str(getattr(args, "axis_slave_indices", "")).strip()
    indices = (
        [int(part.strip(), 0) for part in raw_value.split(",")]
        if raw_value
        else list(range(int(args.axis_count)))
    )
    if len(indices) != int(args.axis_count):
        raise ValueError(
            "--axis-slave-indices count must match --axis-count"
        )
    if len(indices) != len(set(indices)):
        raise ValueError("--axis-slave-indices must be unique")
    if any(index < 0 or index >= device_count for index in indices):
        raise ValueError(
            "--axis-slave-indices contains an index outside device profiles"
        )
    return indices


def parse_optional_sync_mode(raw_value):
    value = str(raw_value).strip()
    if value == "":
        return None

    sync_mode = int(value, 0)
    if sync_mode not in (0, 1, 2):
        raise ValueError(
            f"Unsupported sync mode {sync_mode}; expected 0, 1, 2, or empty."
        )
    return sync_mode


def wait_status_all(runtime, expected_status, max_cycles=None, timeout_s=2.0):
    deadline = None
    if timeout_s is not None:
        deadline = time.monotonic() + float(timeout_s)

    cycles = 0
    while True:
        exchange(runtime)
        if all(
            (slave.txpdo.statusword & 0x006F) == expected_status
            for slave in runtime.slaves
        ):
            return True
        cycles += 1

        if max_cycles is not None and cycles >= max_cycles:
            return False
        if deadline is not None and time.monotonic() >= deadline:
            return False

        if max_cycles is None and deadline is None:
            return False


def read_axis_user_position_units(runtime):
    units = []
    for axis_index in range(axis_count(runtime)):
        try:
            value = int(DEVICE_PROFILE.read_user_unit_position(runtime, axis_index))
        except Exception as exc:
            print(
                "Axis user position unit read failed: "
                f"axis={axis_index} object=0x216E:01 error={exc}",
                flush=True,
            )
            units.append(None)
            continue
        units.append(value)
        print(
            "Axis user position unit: "
            f"axis={axis_index} 0x216E:01=0x{value:04X} "
            f"unit={runtime.drive_manager.user_position_unit_name(value)}",
            flush=True,
        )
    return units


def read_axis_converting_unit_exponents(runtime):
    exponents = []
    for axis_index in range(axis_count(runtime)):
        try:
            values = DEVICE_PROFILE.read_converting_unit_exponents(runtime, axis_index)
        except Exception as exc:
            print(
                "Axis converting unit read failed: "
                f"axis={axis_index} object=0x2194:01-04 error={exc}",
                flush=True,
            )
            exponents.append(None)
            continue
        exponents.append(values)
        print(
            "Axis converting unit exponents: "
            f"axis={axis_index} "
            f"position={values[0]} velocity={values[1]} "
            f"acceleration={values[2]} jerk={values[3]}",
            flush=True,
        )
    return exponents


def initialize_drive(runtime, motion_mode, csp_interpolation_mode):
    runtime.connect()
    require_txpdo_fields(runtime)
    write_csp_interpolation_modes(runtime, csp_interpolation_mode)
    if motion_mode == "pv":
        user_position_units = read_axis_user_position_units(runtime)
        blocked_axes = [
            axis_index
            for axis_index, user_position_unit in enumerate(user_position_units)
            if user_position_unit is None
            or not runtime.drive_manager.pv_allowed(axis_index)
        ]
        if blocked_axes:
            raise ValueError(
                pv_reject_message(
                    {
                        "drive_manager": runtime.drive_manager,
                        "user_position_units": user_position_units,
                    },
                    blocked_axes,
                )
            )
    configure_motion_mode(runtime, motion_mode)

    exchange(runtime, cycles=10)
    runtime.sync_trajectory_to_actual_positions()

    if faulted_axes(runtime):
        runtime.set_controlword_all(0x0080)
        wait_status_all(runtime, 0x0040, timeout_s=2.0)
        runtime.set_controlword_all(0x0000)
        exchange(runtime, cycles=10)

    for controlword, expected_status in [
        (0x0006, 0x0021),
        (0x0007, 0x0023),
        (0x000F, 0x0027),
    ]:
        runtime.set_controlword_all(controlword)
        if not wait_status_all(runtime, expected_status, timeout_s=2.0):
            statuswords = [
                f"0x{slave.txpdo.statusword:04X}"
                for slave in runtime.slaves
            ]
            print(
                f"Failed to reach CiA402 status 0x{expected_status:04X}. "
                f"Statuswords={statuswords}; continuing startup.",
                flush=True,
            )


def write_csp_interpolation_modes(runtime, csp_interpolation_mode):
    value = int(csp_interpolation_mode)
    if value <= 0:
        return

    for axis_index in range(axis_count(runtime)):
        try:
            readback = DEVICE_PROFILE.write_csp_interpolation_mode(
                runtime,
                axis_index,
                value,
            )
            print(
                "Axis "
                f"{axis_index}: CSP interpolation mode "
                f"set to {value} readback={readback}",
                flush=True,
            )
        except Exception as exc:
            print(
                "Axis "
                f"{axis_index}: failed to set CSP interpolation mode "
                f"to {value}; continuing ({exc})",
                flush=True,
            )
