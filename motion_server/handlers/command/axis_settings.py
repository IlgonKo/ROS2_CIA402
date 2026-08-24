from motion_server.control.axis_units import (
    axis_metadata,
    axis_motion_api_to_drive,
    axis_motion_drive_to_api,
    axis_position_api_to_drive,
    axis_position_drive_to_api,
    motion_limits_drive_to_api,
)
from motion_server.config import (
    DEVICE_PROFILE,
    MOTION_MODES,
    require_pdo_fields_for_mode,
    status_log,
)
from motion_server.control.axis_operations import (
    axis_count,
    configure_motion_mode,
    hold_axis_at_actual_position,
    mode_code,
    reject_if_pv_not_allowed,
    update_motion_mode_summary,
)
from motion_server.api import (
    public_command_name,
    require_uint32,
    selected_axes,
)
from motion_server.failure import (
    InvalidArgumentException,
    ItemFailure,
    MotionServerException,
    PartialFailure,
    ResourceNotFoundException,
)


def set_motion_limits(message, runtime, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, runtime, command)
        requested_limits = []
        for axis_index in axes:
            current_limits = list(state["motion_limits"][axis_index])
            positive_velocity_limit = axis_motion_api_to_drive(
                state,
                axis_index,
                message.get(
                    "positive_velocity_limit",
                    message.get(
                        "max_profile_velocity_positive",
                        message.get(
                            "max_profile_velocity",
                            axis_motion_drive_to_api(
                                state,
                                axis_index,
                                current_limits[0],
                                "velocity",
                            ),
                        ),
                    ),
                )
            )
            negative_velocity_limit = axis_motion_api_to_drive(
                state,
                axis_index,
                message.get(
                    "negative_velocity_limit",
                    message.get(
                        "max_profile_velocity_negative",
                        axis_motion_drive_to_api(
                            state,
                            axis_index,
                            current_limits[1],
                            "velocity",
                        ),
                    ),
                )
            )
            max_acceleration = axis_motion_api_to_drive(
                state,
                axis_index,
                message.get(
                    "max_acceleration",
                    message.get(
                        "acceleration",
                        axis_motion_drive_to_api(
                            state,
                            axis_index,
                            current_limits[2],
                            "acceleration",
                        ),
                    ),
                ),
                "acceleration",
            )
            max_deceleration = axis_motion_api_to_drive(
                state,
                axis_index,
                message.get(
                    "max_deceleration",
                    message.get(
                        "deceleration",
                        axis_motion_drive_to_api(
                            state,
                            axis_index,
                            current_limits[3],
                            "deceleration",
                        ),
                    ),
                ),
                "deceleration",
            )
            requested_limits.append(
                (
                    axis_index,
                    positive_velocity_limit,
                    negative_velocity_limit,
                    max_acceleration,
                    max_deceleration,
                )
            )
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvalidArgumentException(
            "motion_limits", "contains invalid values",
        ) from exc

    for (
        axis_index,
        positive_velocity_limit,
        negative_velocity_limit,
        max_acceleration,
        max_deceleration,
    ) in requested_limits:
        update_axis_motion_limits(
            runtime,
            state,
            axis_index,
            positive_velocity_limit,
            negative_velocity_limit,
            max_acceleration,
            max_deceleration,
        )


def update_axis_motion_limits(
    runtime,
    state,
    axis_index,
    positive_velocity_limit,
    negative_velocity_limit,
    acceleration,
    deceleration,
):
    requested_limits = [
        positive_velocity_limit,
        negative_velocity_limit,
        acceleration,
        deceleration,
    ]
    api_axis_limits = motion_limits_drive_to_api(
        state,
        axis_index,
        requested_limits,
    )
    write_axis_motion_limits(runtime, axis_index, requested_limits)
    runtime.set_axis_motion_limits(
        axis_index,
        max(abs(api_axis_limits[0]), abs(api_axis_limits[1])),
        api_axis_limits[2],
        api_axis_limits[3],
        0.0,
    )
    runtime.slaves[axis_index].motion_server_motion_limits = list(
        requested_limits
    )
    state["motion_limits"][axis_index] = requested_limits


def write_axis_motion_limits(runtime, axis_index, axis_limits):
    DEVICE_PROFILE.write_motion_limits(
        runtime,
        axis_index,
        axis_limits[0],
        axis_limits[1],
        axis_limits[2],
        axis_limits[3],
    )


def set_profile(message, runtime, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, runtime, command)
        requested_profiles = []
        for axis_index in axes:
            current_settings = list(state["profile_settings"][axis_index])
            is_pv_axis = state["motion_modes"][axis_index] == "pv"
            profile_velocity = float(
                message.get(
                    "profile_velocity",
                    message.get(
                        "velocity",
                        axis_motion_drive_to_api(
                            state,
                            axis_index,
                            current_settings[0],
                            "velocity",
                        ),
                    ),
                )
            )
            if is_pv_axis:
                profile_velocity = axis_motion_drive_to_api(
                    state,
                    axis_index,
                    current_settings[0],
                    "velocity",
                )
            profile_acceleration = float(
                message.get(
                    "profile_acceleration",
                    message.get(
                        "acceleration",
                        axis_motion_drive_to_api(
                            state,
                            axis_index,
                            current_settings[1],
                            "acceleration",
                        ),
                    ),
                )
            )
            profile_deceleration = float(
                message.get(
                    "profile_deceleration",
                    message.get(
                        "deceleration",
                        axis_motion_drive_to_api(
                            state,
                            axis_index,
                            current_settings[2],
                            "deceleration",
                        ),
                    ),
                )
            )
            profile_jerk = None
            if (
                not is_pv_axis
                and ("profile_jerk" in message or "jerk" in message)
            ):
                profile_jerk = float(
                    message.get(
                        "profile_jerk",
                        message.get("jerk"),
                    )
                )
            requested_profiles.append(
                (
                    axis_index,
                    axis_motion_api_to_drive(state, axis_index, profile_velocity),
                    axis_motion_api_to_drive(
                        state,
                        axis_index,
                        profile_acceleration,
                        "acceleration",
                    ),
                    axis_motion_api_to_drive(
                        state,
                        axis_index,
                        profile_deceleration,
                        "deceleration",
                    ),
                    (
                        axis_motion_api_to_drive(
                            state, axis_index, profile_jerk, "jerk",
                        )
                        if profile_jerk is not None
                        else None
                    ),
                )
            )
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvalidArgumentException(
            "profile", "contains invalid values",
        ) from exc

    for profile in requested_profiles:
        update_axis_profile_settings(runtime, state, *profile)

    status_log(
        "Received axis/profile: "
        f"axes={axes} profile_settings={state['profile_settings']}",
    )


def update_axis_profile_settings(
    runtime,
    state,
    axis_index,
    profile_velocity,
    profile_acceleration,
    profile_deceleration,
    profile_jerk=None,
):
    current_jerk = state["profile_settings"][axis_index][3]
    is_pv_axis = state["motion_modes"][axis_index] == "pv"
    requested_settings = [
        profile_velocity,
        profile_acceleration,
        profile_deceleration,
        current_jerk if profile_jerk is None else profile_jerk,
    ]
    checked_profile_velocity = None
    if not is_pv_axis and runtime.slaves[axis_index].rxpdo.has_field("profile_velocity"):
        checked_profile_velocity = require_uint32(
            profile_velocity,
            f"axis {axis_index} profile_velocity",
        )
    if is_pv_axis:
        runtime.sdo.write_uint32(
            axis_index,
            DEVICE_PROFILE.PROFILE_ACCELERATION_INDEX,
            0,
            max(0, int(profile_acceleration)),
        )
        runtime.sdo.write_uint32(
            axis_index,
            DEVICE_PROFILE.PROFILE_DECELERATION_INDEX,
            0,
            max(0, int(profile_deceleration)),
        )
    else:
        DEVICE_PROFILE.write_profile_settings(
            runtime,
            axis_index,
            profile_velocity,
            profile_acceleration,
            profile_deceleration,
        )
    if profile_jerk is not None:
        DEVICE_PROFILE.write_profile_jerk(runtime, axis_index, profile_jerk)
    if checked_profile_velocity is not None:
        runtime.slaves[axis_index].rxpdo.profile_velocity = checked_profile_velocity
    state["profile_settings"][axis_index] = requested_settings


def set_software_position_limits(message, runtime, state, client):
    command = public_command_name(message)
    try:
        axes = selected_axes(message, runtime, command)
        requested_limits = []
        for axis_index in axes:
            current_limits = list(state["software_position_limits"][axis_index])
            negative_limit_api = float(
                message.get(
                    "negative_limit",
                    message.get(
                        "negative_software_position_limit",
                        axis_position_drive_to_api(
                            state,
                            axis_index,
                            current_limits[0],
                        ),
                    ),
                )
            )
            positive_limit_api = float(
                message.get(
                    "positive_limit",
                    message.get(
                        "positive_software_position_limit",
                        axis_position_drive_to_api(
                            state,
                            axis_index,
                            current_limits[1],
                        ),
                    ),
                )
            )
            negative_limit = int(round(axis_position_api_to_drive(
                state,
                axis_index,
                negative_limit_api,
            )))
            positive_limit = int(round(axis_position_api_to_drive(
                state,
                axis_index,
                positive_limit_api,
            )))
            if negative_limit > positive_limit:
                raise ValueError(
                    "negative software position limit is greater than "
                    f"positive limit. axis={axis_index} "
                    f"negative={negative_limit} positive={positive_limit}"
                )
            requested_limits.append(
                (
                    axis_index,
                    negative_limit_api,
                    positive_limit_api,
                    negative_limit,
                    positive_limit,
                )
            )
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvalidArgumentException(
            "software_position_limits", "contains invalid values",
        ) from exc

    for (
        axis_index,
        negative_limit_api,
        positive_limit_api,
        negative_limit,
        positive_limit,
    ) in requested_limits:
        DEVICE_PROFILE.write_software_position_limits(
            runtime,
            axis_index,
            negative_limit,
            positive_limit,
        )
        try:
            readback_limits = DEVICE_PROFILE.read_software_position_limits(
                runtime,
                axis_index,
            )
        except Exception as exc:
            readback_limits = [f"read failed: {exc}", f"read failed: {exc}"]
        state["software_position_limits"][axis_index] = [
            negative_limit,
            positive_limit,
        ]
        status_log(
            "Axis software position limits write: "
            f"axis={axis_index} "
            f"api=({negative_limit_api}, {positive_limit_api}) "
            f"drive=({negative_limit}, {positive_limit}) "
            f"readback={readback_limits} "
            f"metadata={axis_metadata(state, axis_index)}",
        )

    status_log(
        "Received axis/software_position_limits: "
        f"axes={axes} limits={state['software_position_limits']}",
    )


def set_mode(message, runtime, state, client=None):
    command = public_command_name(message)
    requested_mode = str(message.get("mode", "")).strip().lower()
    if requested_mode not in MOTION_MODES:
        raise InvalidArgumentException("mode", "is not supported")

    axis_value = message.get("axis", None)
    if axis_value is None:
        axis_indices = list(range(axis_count(runtime)))
    else:
        try:
            axis_index = int(axis_value)
        except (TypeError, ValueError):
            raise InvalidArgumentException("axis", "must be an integer")
        if axis_index < 0 or axis_index >= axis_count(runtime):
            raise ResourceNotFoundException("axis", axis_index)
        axis_indices = [axis_index]

    if all(state["motion_modes"][axis_index] == requested_mode for axis_index in axis_indices):
        return

    if requested_mode == "pv" and reject_if_pv_not_allowed(
        state,
        axis_indices,
        client,
        command,
    ):
        return

    for axis_index in axis_indices:
        require_pdo_fields_for_mode(runtime, requested_mode, axis_index)

    for axis_index in axis_indices:
        hold_axis_at_actual_position(runtime, state, axis_index)
    runtime.set_target_positions(state["target_positions"])

    changed_axes = []
    failed = []
    for axis_index in axis_indices:
        previous_mode = state["motion_modes"][axis_index]
        try:
            configure_motion_mode(runtime, requested_mode, axis_index)
        except MotionServerException as exc:
            failed.append((axis_index, exc))
            previous_code = mode_code(previous_mode)
            runtime.slaves[axis_index].rxpdo.mode_of_operation = previous_code
            status_log(
                "Motion mode change failed "
                f"axis={axis_index} requested={requested_mode.upper()} "
                f"previous={previous_mode.upper()} error={exc}",
            )
            continue

        state["motion_modes"][axis_index] = requested_mode
        changed_axes.append(axis_index)

    update_motion_mode_summary(state)
    if failed:
        if not changed_axes:
            raise failed[0][1]
        return PartialFailure(
            succeeded=changed_axes,
            failed=[
                ItemFailure(target=axis_index, exception=exception)
                for axis_index, exception in failed
            ],
        )

    if changed_axes:
        status_log(
            f"Motion mode changed axes={changed_axes} "
            f"to {requested_mode.upper()} modes={state['motion_modes']}",
        )
