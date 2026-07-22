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
from device import get_device_profile
from motion_server.drive import DriveBinding, DriveManager
from device.virtual_servo_drive import VirtualCiA402Servo
from ethercat.mock_master import MockMaster
from ethercat.mock_slave import MockSlave
from ethercat.pysoem_master import PySOEMMaster
from motion_server.control.axis import Axis
from motion_server.control.motion_controller import MotionController

MOCK_AXIS_TYPE_USER_UNITS = {
    "linear": 0x0100,
    "rotary": 0x4100,
}


def create_axis_runtime(args, motion_limits):
    sync_mode = parse_optional_sync_mode(args.sync_mode)
    device_profile_names = list(args.device_profile_names)
    axis_slave_indices = list(args.axis_slave_indices)
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
        mock_user_units = parse_mock_axis_user_units(args)
        for axis_index, limits in enumerate(motion_limits):
            servo = VirtualCiA402Servo(cycle_time=args.cycle_time)
            servo.od.write(0x216E, mock_user_units[axis_index], 0x01)
            servo.set_motion_limits(
                limits["max_velocity"],
                limits["acceleration"],
                limits["deceleration"],
            )
            axis = Axis(f"A{axis_index}", servo)
            slaves.append(MockSlave(axis))
            print(
                "Mock axis user position unit: "
                f"axis={axis_index} 0x216E:01=0x{mock_user_units[axis_index]:04X}",
                flush=True,
            )

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


def parse_mock_axis_user_units(args):
    raw_units = str(getattr(args, "mock_axis_user_units", "")).strip()
    if raw_units:
        return parse_axis_values(
            raw_units,
            int(args.axis_count),
            lambda value: int(value, 0),
            "--mock-axis-user-units",
        )

    raw_types = str(getattr(args, "mock_axis_types", "")).strip()
    if raw_types:
        return parse_axis_values(
            raw_types,
            int(args.axis_count),
            parse_mock_axis_type,
            "--mock-axis-types",
        )

    return [MOCK_AXIS_TYPE_USER_UNITS["linear"] for _ in range(int(args.axis_count))]


def parse_axis_values(raw_value, axis_count_value, parser, option_name):
    parts = [part.strip() for part in raw_value.split(",") if part.strip()]
    if not parts:
        raise ValueError(f"{option_name} does not contain any values")
    if len(parts) == 1:
        parts = parts * axis_count_value
    if len(parts) != axis_count_value:
        raise ValueError(f"{option_name} count must match motion axes in --bus")
    return [parser(part) for part in parts]


def parse_mock_axis_type(value):
    key = str(value).strip().lower()
    if key not in MOCK_AXIS_TYPE_USER_UNITS:
        print(
            "Unsupported mock axis type; using linear fallback. "
            f"value={value!r} expected=linear|rotary",
            flush=True,
        )
        key = "linear"
    return MOCK_AXIS_TYPE_USER_UNITS[key]


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


def read_startup_axis_sdo(runtime):
    return {
        "user_position_units": read_axis_user_position_units(runtime),
        "converting_unit_exponents": read_axis_converting_unit_exponents(runtime),
        "software_position_limits": read_axis_software_position_limits(runtime),
        "profile_settings": read_axis_profile_settings(runtime),
        "motion_limits": read_axis_motion_limits(runtime),
    }


def read_axis_software_position_limits(runtime):
    limits = []
    for axis_index in range(axis_count(runtime)):
        try:
            values = DEVICE_PROFILE.read_software_position_limits(runtime, axis_index)
        except Exception as exc:
            print(
                "Axis software position limit read failed: "
                f"axis={axis_index} object=0x607D:01-02 error={exc}",
                flush=True,
            )
            values = [-1000000, 1000000]
        limits.append(values)
    return limits


def read_axis_profile_settings(runtime):
    settings = []
    for axis_index in range(axis_count(runtime)):
        try:
            values = DEVICE_PROFILE.read_profile_settings(runtime, axis_index)
        except Exception as exc:
            print(
                "Axis profile setting read failed: "
                f"axis={axis_index} objects=0x6081/0x6083/0x6084/0x60A4 error={exc}",
                flush=True,
            )
            values = None
        settings.append(values)
    return settings


def read_axis_motion_limits(runtime):
    limits = []
    for axis_index in range(axis_count(runtime)):
        try:
            values = DEVICE_PROFILE.read_motion_limits(runtime, axis_index)
        except Exception as exc:
            print(
                "Axis motion limit read failed: "
                f"axis={axis_index} objects=0x607F/0x2183/0x60C5/0x60C6 error={exc}",
                flush=True,
            )
            values = None
        limits.append(values)
    return limits


def initialize_drive(runtime, motion_mode, csp_interpolation_mode, startup_sdo_reader=None):
    staged_startup = hasattr(runtime, "enter_operational")
    startup_sdo = None
    runtime.connect(target_state="preop" if staged_startup else None)
    require_txpdo_fields(runtime)
    if startup_sdo_reader is not None:
        startup_sdo = startup_sdo_reader(runtime)
    write_csp_interpolation_modes(runtime, csp_interpolation_mode)
    if motion_mode == "pv":
        user_position_units = (
            startup_sdo.get("user_position_units")
            if startup_sdo is not None
            else read_axis_user_position_units(runtime)
        )
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
    if staged_startup:
        configure_motion_mode_without_exchange(runtime, motion_mode)
        runtime.enter_operational()
    else:
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
    return startup_sdo


def configure_motion_mode_without_exchange(runtime, mode_name):
    require_pdo_fields_for_mode(runtime, mode_name)
    code = DEVICE_PROFILE.mode_code(mode_name)
    runtime.set_mode_of_operation_all(code)
    for axis_index in range(axis_count(runtime)):
        DEVICE_PROFILE.configure_mode_code(runtime, axis_index, code)


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
