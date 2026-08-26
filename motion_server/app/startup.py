import time
import logging

from device.capabilities import DeviceCapability
from device.exceptions import (
    DeviceLayoutInvalidException,
    PdoCatalogMismatchException,
)

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
from motion_server.control.axis_units import motion_limits_drive_to_api
from motion_server.api import require_uint32
from motion_server.runtime_logging import RuntimeLogger
from motion_server.app.initialization import (
    InitializationCause,
    InitializationException,
)


LOGGER = logging.getLogger(__name__)


def build_device_models(devices):
    profiles = []
    for device in devices:
        try:
            profiles.append(get_device_profile_for_device(device))
        except DeviceLayoutInvalidException as exc:
            raise InitializationException(
                InitializationCause.DEVICE_LAYOUT_INVALID
            ) from exc
        except PdoCatalogMismatchException as exc:
            raise InitializationException(
                InitializationCause.PDO_CATALOG_MISMATCH
            ) from exc
    return tuple(profiles)


def close_initialization_resource(resource, *, logger=None):
    if resource is None:
        return None
    logger = logger or LOGGER
    try:
        resource.close()
    except Exception as exc:
        logger.exception(
            "Initialization resource cleanup failed: resource=%s",
            type(resource).__name__,
        )
        return exc
    return None


def create_axis_runtime(
    ethercat,
    motion,
    logging_config,
    devices,
    *,
    device_profiles=None,
):
    runtime_logger = RuntimeLogger(logging_config)
    sync_mode = ethercat.sync_mode
    device_profile_names = [device.profile_name for device in devices]
    device_profiles = list(
        device_profiles
        if device_profiles is not None
        else build_device_models(devices)
    )
    if len(device_profiles) != len(devices):
        raise ValueError("Device model count must match configured device count")
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

    master = None
    device_manager = None
    try:
        if ethercat.backend.value == "mock":
            if axis_slave_indices != list(range(axis_count_value)) or (
                len(device_profile_names) != axis_count_value
            ):
                raise ValueError(
                    "mock backend supports only one-to-one axis/slave mapping"
                )
            slaves = []
            for axis_index in range(axis_count_value):
                device_profile = device_profiles[axis_index]
                virtual_device = VirtualCiA402Servo(
                    cycle_time=ethercat.cycle.period,
                    device_profile=device_profile,
                )
                slaves.append(MockSlave(
                    virtual_device,
                    device_profile,
                ))

            master = MockMaster(
                slaves,
                cycle_time=ethercat.cycle.period,
            )
        else:
            master = PySOEMMaster(
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
            csp_velocity_offset_enabled=motion.csp_velocity_offset,
            csp_command_step_threshold=(
                logging_config.csp_command_step.step_threshold
            ),
            csp_command_step_error_threshold=(
                logging_config.csp_command_step.error_threshold
            ),
            csp_profile=motion.csp_profile.value,
        )
        device_manager = DeviceManager(master, axis_bindings)
        runtime = AxisRuntime(
            device_manager,
            motion_controller,
            runtime_logger=runtime_logger,
        )
        if ethercat.backend.value == "mock":
            require_pdo_fields_for_mode(runtime, motion.initial_motion_mode)
            require_txpdo_fields(runtime)
        return runtime
    except Exception:
        close_initialization_resource(device_manager or master)
        raise


def connect_bus(runtime):
    runtime.connect(target_state="preop")


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
    values = {
        "user_position_units": read_axis_user_position_units(runtime),
        "converting_unit_exponents": read_axis_converting_unit_exponents(runtime),
        "software_position_limits": read_axis_software_position_limits(runtime),
        "profile_settings": read_axis_profile_settings(runtime),
        "motion_limits": read_axis_motion_limits(runtime),
    }
    if any(item is None for item in values["user_position_units"]):
        raise InitializationException(
            InitializationCause.REQUIRED_PARAMETER_READ_FAILED
        )
    if any(item is None for item in values["converting_unit_exponents"]):
        raise InitializationException(
            InitializationCause.REQUIRED_PARAMETER_READ_FAILED
        )
    values["profile_settings"] = [
        item if item is not None else [0.0, 0.0, 0.0, 0.0]
        for item in values["profile_settings"]
    ]
    values["motion_limits"] = [
        item if item is not None else [0.0, 0.0, 0.0, 0.0]
        for item in values["motion_limits"]
    ]
    return values


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


def refresh_axis_parameter_cache(runtime, axis_index):
    """Refresh one axis cache from authoritative device OD readback."""
    profile = axis_device_profile(runtime, axis_index)
    unit = int(profile.read_user_unit_position(runtime, axis_index))
    exponents = profile.read_converting_unit_exponents(runtime, axis_index)
    software_limits = profile.read_software_position_limits(runtime, axis_index)
    profile_settings = profile.read_profile_settings(runtime, axis_index)
    motion_limits = profile.read_motion_limits(runtime, axis_index)

    cached_units = runtime.axis_parameters.user_position_units
    cached_exponents = runtime.axis_parameters.converting_unit_exponents
    cached_units[axis_index] = unit
    cached_exponents[axis_index] = exponents
    runtime.device_manager.axes.configure_unit_conversion(
        cached_units, cached_exponents
    )
    metadata = runtime.device_manager.axes.unit_metadata()[axis_index]
    runtime.axis_parameters.update_axis(
        axis_index,
        user_position_unit=unit,
        converting_unit_exponents=exponents,
        software_position_limits=software_limits,
        profile_settings=profile_settings,
        motion_limits=motion_limits,
        axis_metadata=metadata,
    )
    scale = runtime.device_manager.axes.position_counts_per_api_unit(axis_index)
    runtime.set_axis_position_counts_per_api_unit(axis_index, scale)
    unit_state = {"axis_devices": runtime.device_manager.axes}
    api_limits = motion_limits_drive_to_api(unit_state, axis_index, motion_limits)
    current_jerk = runtime.motion_limits[axis_index].jerk
    runtime.set_axis_motion_limits(
        axis_index,
        max(abs(api_limits[0]), abs(api_limits[1])),
        api_limits[2],
        api_limits[3],
        current_jerk,
    )
    runtime.slaves[axis_index].motion_server_motion_limits = list(motion_limits)
    synchronize_profile_velocity_command(
        runtime,
        axis_index,
        profile_settings,
    )
    return runtime.axis_parameters.axes[axis_index]


def synchronize_profile_velocity_command(runtime, axis_index, profile_settings):
    """Seed an outgoing PDO command from authoritative device readback."""
    slave = runtime.slaves[axis_index]
    if slave.rxpdo.has_field("profile_velocity"):
        slave.rxpdo.profile_velocity = require_uint32(
            profile_settings[0],
            f"axis {axis_index} profile_velocity",
        )


def synchronize_startup_profile_velocity_commands(runtime, startup_sdo):
    if startup_sdo is None:
        return
    for axis_index, profile_settings in enumerate(
        startup_sdo["profile_settings"]
    ):
        synchronize_profile_velocity_command(
            runtime,
            axis_index,
            profile_settings,
        )


def initialize_drive(runtime, motion_mode, csp_interpolation_modes, startup_sdo_reader=None):
    startup_sdo = None
    require_txpdo_fields(runtime)
    clear_axis_restart_commands(runtime)
    if startup_sdo_reader is not None:
        startup_sdo = startup_sdo_reader(runtime)
        # RxPDO is the outgoing process image. Seed mapped parameter commands
        # before the first cyclic exchange so zero-filled buffers cannot
        # overwrite authoritative device OD values.
        synchronize_startup_profile_velocity_commands(runtime, startup_sdo)
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
