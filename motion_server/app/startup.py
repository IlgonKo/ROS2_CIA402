import time

from device.capabilities import DeviceCapability

from motion_server.control.pdo_contract import (
    require_pdo_fields_for_mode,
    require_txpdo_fields,
)
from motion_server.device_manager.profile_access import axis_device_profile
from motion_server.app.cycle import exchange
from motion_server.control.axis_operations import (
    axis_count,
    faulted_axes,
    pv_reject_message,
)
from motion_server.app.runtime import AxisRuntime
from device import get_device_profile
from motion_server.device_manager import AxisBinding, DeviceManager
from device.virtual_servo_drive import VirtualCiA402Servo
from ethercat.mock_master import MockMaster
from ethercat.mock_slave import MockSlave
from ethercat.pysoem_master import PySOEMMaster
from motion_server.control.motion_controller import MotionController
from motion_server.runtime_logging import RuntimeLogger

def create_axis_runtime(ethercat, motion, logging, devices, motion_limits):
    runtime_logger = RuntimeLogger(logging)
    sync_mode = ethercat.sync_mode
    device_profile_names = [device.profile_name for device in devices]
    device_profiles = [
        get_device_profile_for_device(device)
        for device in devices
    ]
    axis_slave_indices = [
        device.slave_index
        for device in devices
        if device.role.value == "axis"
    ]
    io_devices = [
        {
            "id": device.logical_id,
            "profile": device.profile_name,
            "slave_index": device.slave_index,
        }
        for device in devices
        if device.role.value == "io"
    ]
    axis_count_value = len(axis_slave_indices)
    axis_bindings = [
        AxisBinding(axis_index=axis_index, slave_index=slave_index)
        for axis_index, slave_index in enumerate(axis_slave_indices)
    ]

    if ethercat.backend.value == "mock":
        if axis_slave_indices != list(range(axis_count_value)) or (
            len(device_profile_names) != axis_count_value
        ):
            raise ValueError(
                "mock backend supports only one-to-one axis/slave mapping"
            )
        slaves = []
        for axis_index, limits in enumerate(motion_limits):
            device_profile = device_profiles[axis_index]
            servo = VirtualCiA402Servo(
                cycle_time=ethercat.cycle.period,
                device_profile=device_profile,
            )
            servo.set_motion_limits(
                limits["max_velocity"],
                limits["acceleration"],
                limits["deceleration"],
            )
            slaves.append(MockSlave(
                servo,
                device_profile,
            ))

        ethercat_master = MockMaster(
            slaves,
            cycle_time=ethercat.cycle.period,
        )
        motion_controller = MotionController(
            axis_count_value,
            ethercat.cycle.period,
            motion_limits=motion_limits,
            csp_velocity_offset_enabled=tuple(
                getattr(device.device, "csp_velocity_offset", False)
                for device in devices
                if device.role.value == "axis"
            ),
            csp_command_step_threshold=logging.csp_command_step.step_threshold,
            csp_command_step_error_threshold=logging.csp_command_step.error_threshold,
            csp_profile=motion.csp_profile.value,
        )
        for axis_index, limits in enumerate(motion_limits):
            motion_controller.set_axis_motion_limits(
                axis_index,
                limits["max_velocity"],
                limits["acceleration"],
                limits["deceleration"],
                limits["jerk"],
            )
        device_manager = DeviceManager(ethercat_master, axis_bindings)
        runtime = AxisRuntime(
            device_manager,
            motion_controller,
            runtime_logger=runtime_logger,
        )
        require_pdo_fields_for_mode(runtime, motion.initial_motion_mode)
        require_txpdo_fields(runtime)
        return runtime

    ethercat_master = PySOEMMaster(
        interface_name=ethercat.interface,
        device_profiles=device_profiles,
        cycle_time=ethercat.cycle.period,
        sync_mode=sync_mode,
        dc_enabled=ethercat.dc.enabled,
        dc_sync0_shift_time=ethercat.dc.sync0_shift_time_ns,
    )
    motion_controller = MotionController(
        axis_count_value,
        ethercat.cycle.period,
        motion_limits=motion_limits,
        csp_velocity_offset_enabled=tuple(
            getattr(device.device, "csp_velocity_offset", False)
            for device in devices
            if device.role.value == "axis"
        ),
        csp_command_step_threshold=logging.csp_command_step.step_threshold,
        csp_command_step_error_threshold=logging.csp_command_step.error_threshold,
        csp_profile=motion.csp_profile.value,
    )
    device_manager = DeviceManager(ethercat_master, axis_bindings)
    return AxisRuntime(
        device_manager,
        motion_controller,
        runtime_logger=runtime_logger,
    )


def get_device_profile_for_slave(
    profile_name,
    slave_index,
    io_devices,
    axis_slave_indices=None,
):
    for io_device in io_devices:
        if int(io_device["slave_index"]) == int(slave_index):
            return get_device_profile(profile_name, io_id=io_device["id"])

    axis_index = None
    if axis_slave_indices is not None:
        axis_indices = [
            index
            for index, current_slave_index in enumerate(axis_slave_indices)
            if int(current_slave_index) == int(slave_index)
        ]
        if axis_indices:
            axis_index = axis_indices[0]
    return get_device_profile(
        profile_name,
        axis_index=axis_index,
        slave_index=slave_index,
    )


def get_device_profile_for_device(device):
    kwargs = {
        "device_config": device.device,
    }
    if device.role.value == "axis":
        kwargs.update(
            axis_index=device.device.axis_index,
            slave_index=device.slave_index,
        )
    else:
        kwargs["io_id"] = device.logical_id
    return get_device_profile(device.profile_name, **kwargs)


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
            profile = axis_device_profile(runtime, axis_index)
            value = int(profile.read_user_unit_position(runtime, axis_index))
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
            f"unit={runtime.device_manager.axes.user_position_unit_name(value)}",
            flush=True,
        )
    return units


def read_axis_converting_unit_exponents(runtime):
    exponents = []
    for axis_index in range(axis_count(runtime)):
        try:
            profile = axis_device_profile(runtime, axis_index)
            values = profile.read_converting_unit_exponents(runtime, axis_index)
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
            profile = axis_device_profile(runtime, axis_index)
            values = profile.read_software_position_limits(runtime, axis_index)
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
            profile = axis_device_profile(runtime, axis_index)
            values = profile.read_profile_settings(runtime, axis_index)
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
            profile = axis_device_profile(runtime, axis_index)
            values = profile.read_motion_limits(runtime, axis_index)
        except Exception as exc:
            print(
                "Axis motion limit read failed: "
                f"axis={axis_index} objects=0x607F/0x2183/0x60C5/0x60C6 error={exc}",
                flush=True,
            )
            values = None
        limits.append(values)
    return limits


def initialize_drive(runtime, motion_mode, csp_interpolation_modes, startup_sdo_reader=None):
    startup_sdo = None
    runtime.connect(target_state="preop")
    require_txpdo_fields(runtime)
    clear_axis_restart_commands(runtime)
    if startup_sdo_reader is not None:
        startup_sdo = startup_sdo_reader(runtime)
    write_csp_interpolation_modes(runtime, csp_interpolation_modes)
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
            or not runtime.device_manager.axes.pv_allowed(axis_index)
        ]
        if blocked_axes:
            raise ValueError(
                pv_reject_message(
                    {
                        "axis_devices": runtime.device_manager.axes,
                        "user_position_units": user_position_units,
                    },
                    blocked_axes,
                )
            )
    configure_motion_mode_without_exchange(runtime, motion_mode)
    runtime.enter_operational()

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


def clear_axis_restart_commands(runtime):
    for axis_index in range(axis_count(runtime)):
        profile = axis_device_profile(runtime, axis_index)
        if DeviceCapability.AXIS_RESTART not in profile.capabilities:
            continue
        try:
            result = profile.clear_axis_restart_request(runtime, axis_index)
            print(
                "Axis restart command cleared: "
                f"axis={axis_index} result={result}",
                flush=True,
            )
        except Exception as exc:
            print(
                "Axis restart command clear failed; continuing. "
                f"axis={axis_index} error={exc}",
                flush=True,
            )


def configure_motion_mode_without_exchange(runtime, mode_name):
    require_pdo_fields_for_mode(runtime, mode_name)
    for axis_index in range(axis_count(runtime)):
        profile = axis_device_profile(runtime, axis_index)
        code = profile.mode_code(mode_name)
        runtime.slaves[axis_index].rxpdo.mode_of_operation = code
        profile.configure_mode_code(runtime, axis_index, code)


def write_csp_interpolation_modes(runtime, csp_interpolation_modes):
    values = tuple(int(value) for value in csp_interpolation_modes)
    if len(values) != axis_count(runtime):
        raise ValueError("CSP interpolation mode must be configured per axis")

    for axis_index, value in enumerate(values):
        if value <= 0:
            continue
        profile = axis_device_profile(runtime, axis_index)
        try:
            readback = profile.write_csp_interpolation_mode(
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
