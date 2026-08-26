"""Build panel update data from Motion Server feedback messages."""

from control_panel.axis_control_panel.units import build_axis_metadata


def initial_feedback(axis_count):
    return {
        "target_positions": [0.0 for _ in range(axis_count)],
        "actual_positions": [0.0 for _ in range(axis_count)],
        "actual_velocities": [0.0 for _ in range(axis_count)],
        "command_positions": [0.0 for _ in range(axis_count)],
        "position_counts_per_unit": 1.0,
        "statuswords": [0 for _ in range(axis_count)],
        "motion_limits": [0.0 for _ in range(axis_count * 4)],
        "profile_settings": [0.0 for _ in range(axis_count * 4)],
        "software_position_limits": [0.0 for _ in range(axis_count * 2)],
        "motion_mode": "pp",
        "server_mode": "basic",
        "capabilities": {},
        "device_diagnostics": [],
        "axis_diagnostic_statuses": [None for _ in range(axis_count)],
        "process_data_valid": False,
        "server_health": {},
        "command_authority": {
            "owner": None,
            "owned_by_this_client": False,
            "available": True,
        },
    }


def merge_system_feedback(feedback, message, axis_count):
    for key in (
        "target_positions",
        "actual_positions",
        "actual_velocities",
        "statuswords",
        "mode_displays",
        "command_authority",
        "process_data_valid",
        "server_health",
    ):
        if key in message:
            feedback[key] = message[key]

    if "statuswords" in message:
        diagnostics = _diagnostics(feedback, axis_count)
        for axis_index, statusword in enumerate(
            list(message["statuswords"])[:axis_count],
        ):
            diagnostics[axis_index]["statusword"] = int(statusword)

    if "mode_displays" in message:
        diagnostics = _diagnostics(feedback, axis_count)
        for axis_index, mode_display in enumerate(
            list(message["mode_displays"])[:axis_count],
        ):
            diagnostics[axis_index]["mode_display"] = int(mode_display)


def merge_axis_status(feedback, message, axis_count):
    axis_index = int(message.get("axis", -1))
    if axis_index < 0 or axis_index >= axis_count:
        return False

    scalar_to_array = {
        "target_position": "target_positions",
        "actual_position": "actual_positions",
        "actual_velocity": "actual_velocities",
        "command_position": "command_positions",
        "command_velocity": "command_velocities",
        "statusword": "statuswords",
        "mode_display": "mode_displays",
    }
    for scalar_key, array_key in scalar_to_array.items():
        if scalar_key not in message:
            continue
        values = feedback.setdefault(
            array_key,
            [0.0 for _ in range(axis_count)],
        )
        _extend(values, axis_count, 0.0)
        values[axis_index] = message[scalar_key]

    if "motion_mode" in message:
        modes = feedback.setdefault(
            "motion_modes",
            ["pp" for _ in range(axis_count)],
        )
        _extend(modes, axis_count, "pp")
        modes[axis_index] = str(message["motion_mode"]).lower()

    for array_key, value in (
        ("motion_limits", message.get("motion_limits")),
        ("profile_settings", message.get("profile_settings")),
    ):
        if value is None:
            continue
        set_axis_list_value(feedback, array_key, 4, axis_count, axis_index, value)

    if "software_position_limits" in message:
        set_axis_list_value(
            feedback,
            "software_position_limits",
            2,
            axis_count,
            axis_index,
            message["software_position_limits"],
        )

    if "axis_metadata" in message:
        metadata = feedback.setdefault(
            "axis_metadata",
            [{} for _ in range(axis_count)],
        )
        _extend(metadata, axis_count, {})
        metadata[axis_index] = message["axis_metadata"]

    if "user_position_unit" in message:
        units = feedback.setdefault(
            "user_position_units",
            [None for _ in range(axis_count)],
        )
        _extend(units, axis_count, None)
        units[axis_index] = message["user_position_unit"]

    if "converting_unit_exponents" in message:
        exponents = feedback.setdefault(
            "converting_unit_exponents",
            [None for _ in range(axis_count)],
        )
        _extend(exponents, axis_count, None)
        exponents[axis_index] = message["converting_unit_exponents"]

    if "axis_position_counts_per_unit" in message:
        default_counts = feedback.get("position_counts_per_unit", 1.0)
        counts_per_unit = feedback.setdefault(
            "axis_position_counts_per_unit",
            [default_counts for _ in range(axis_count)],
        )
        _extend(counts_per_unit, axis_count, default_counts)
        counts_per_unit[axis_index] = message["axis_position_counts_per_unit"]

    for key in (
        "drive_initialized",
        "initialization_error",
        "server_mode",
        "capabilities",
        "command_authority",
        "position_counts_per_unit",
    ):
        if key in message:
            feedback[key] = message[key]

    if "device_diagnostics" in message:
        diagnostics = _diagnostics(feedback, axis_count)
        diagnostics[axis_index] = message["device_diagnostics"]

    if "diagnostic_status" in message:
        statuses = feedback.setdefault(
            "axis_diagnostic_statuses",
            [None for _ in range(axis_count)],
        )
        _extend(statuses, axis_count, None)
        statuses[axis_index] = message["diagnostic_status"]

    return True


def set_axis_list_value(feedback, key, fields_per_axis, axis_count, axis_index, values):
    flat = feedback.setdefault(
        key,
        [0.0 for _ in range(axis_count * fields_per_axis)],
    )
    required = axis_count * fields_per_axis
    _extend(flat, required, 0.0)
    for field_index, value in enumerate(list(values)[:fields_per_axis]):
        flat[axis_index * fields_per_axis + field_index] = value


def _diagnostics(feedback, axis_count):
    diagnostics = feedback.setdefault("device_diagnostics", [])
    _extend(diagnostics, axis_count, {})
    return diagnostics


def _extend(values, size, fill):
    while len(values) < size:
        if isinstance(fill, dict):
            values.append(dict(fill))
        else:
            values.append(fill)


class PanelUpdateDataMixin:
    def _values(self, feedback, key, default):
        values = list(feedback.get(key, []))
        while len(values) < self.axis_count:
            values.append(default)
        return values[:self.axis_count]

    def _axis_lists(self, feedback, key, fields_per_axis, default):
        values = list(feedback.get(key, []))
        if values and all(isinstance(value, list) for value in values):
            rows = [list(value) for value in values]
        else:
            flat = values
            required = self.axis_count * fields_per_axis
            while len(flat) < required:
                flat.append(default)
            rows = [
                flat[index * fields_per_axis:(index + 1) * fields_per_axis]
                for index in range(self.axis_count)
            ]
        while len(rows) < self.axis_count:
            rows.append([default for _ in range(fields_per_axis)])
        return [
            (row + [default for _ in range(fields_per_axis)])[:fields_per_axis]
            for row in rows[:self.axis_count]
        ]

    def _axis_metadata(self, feedback, user_position_units, converting_unit_exponents):
        metadata = list(feedback.get("axis_metadata", []))
        while len(metadata) < self.axis_count:
            metadata.append({})
        rows = []
        for axis_index in range(self.axis_count):
            axis_metadata = metadata[axis_index]
            if isinstance(axis_metadata, dict) and axis_metadata:
                rows.append(axis_metadata)
                continue
            rows.append(build_axis_metadata(
                axis_index,
                user_position_units[axis_index],
                converting_unit_exponents[axis_index],
            ))
        return rows
