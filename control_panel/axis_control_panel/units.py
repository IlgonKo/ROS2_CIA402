"""Unit conversion helpers for the Axis Control Panel."""
PV_USER_POSITION_UNITS = {
    0x1000: "rad",
    0x4100: "deg",
    0xB400: "rev",
}

LINEAR_USER_POSITION_UNITS = {
    0x0100: "m",
}

MODE_DISPLAY_NAMES = {
    1: "pp",
    3: "pv",
    6: "homing",
    8: "csp",
    -3: "jog",
}


def user_position_unit_name(user_position_unit):
    if user_position_unit is None:
        return "unknown"
    unit = int(user_position_unit)
    return (
        PV_USER_POSITION_UNITS.get(unit)
        or LINEAR_USER_POSITION_UNITS.get(unit)
        or f"0x{unit:04X}"
    )


def axis_motion_kind(user_position_unit):
    if user_position_unit is None:
        return "unknown"
    unit = int(user_position_unit)
    if unit in PV_USER_POSITION_UNITS:
        return "rotary"
    if unit in LINEAR_USER_POSITION_UNITS:
        return "linear"
    return "unknown"


def api_position_unit_name(user_position_unit):
    motion_kind = axis_motion_kind(user_position_unit)
    if motion_kind == "rotary":
        return "deg"
    if motion_kind == "linear":
        return "mm"
    return user_position_unit_name(user_position_unit)


def api_to_user_unit_factor(user_position_unit):
    if user_position_unit is None:
        return 1.0
    unit = int(user_position_unit)
    if unit in LINEAR_USER_POSITION_UNITS:
        return 0.001
    if unit == 0x1000:
        return 3.141592653589793 / 180.0
    if unit == 0x4100:
        return 1.0
    if unit == 0xB400:
        return 1.0 / 360.0
    return 1.0


def scale_from_exponent(exponent, default=1.0):
    if exponent is None:
        return default
    exponent_value = int(exponent)
    if exponent_value > 0:
        return 10.0 ** (-exponent_value)
    return 10.0 ** exponent_value


def build_axis_metadata(axis_index, user_position_unit, exponents):
    if exponents is None:
        exponents = [None, None, None, None]
    user_unit_name = user_position_unit_name(user_position_unit)
    position_unit = api_position_unit_name(user_position_unit)
    acceleration_scale = scale_from_exponent(exponents[2], 1.0)
    return {
        "axis": axis_index,
        "user_position_unit": user_position_unit,
        "user_position_unit_name": user_unit_name,
        "motion_kind": axis_motion_kind(user_position_unit),
        "pv_allowed": user_position_unit is not None
        and int(user_position_unit) in PV_USER_POSITION_UNITS,
        "converting_unit_exponents": exponents,
        "position_unit": position_unit,
        "velocity_unit": f"{position_unit}/s",
        "acceleration_unit": f"{position_unit}/s^2",
        "deceleration_unit": f"{position_unit}/s^2",
        "jerk_unit": f"{position_unit}/s^3",
        "position_scale": scale_from_exponent(exponents[0], 1.0),
        "velocity_scale": scale_from_exponent(exponents[1], 1.0),
        "acceleration_scale": acceleration_scale,
        "deceleration_scale": acceleration_scale,
        "jerk_scale": scale_from_exponent(exponents[3], 1.0),
    }


class UnitConversionMixin:
    def axis_user_position_unit(self, axis_index):
        metadata = self.axis_metadata(axis_index)
        value = metadata.get("user_position_unit")
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        return None

    def axis_metadata(self, axis_index):
        if axis_index < len(self.latest_axis_metadata):
            metadata = self.latest_axis_metadata[axis_index]
            if isinstance(metadata, dict):
                return metadata
        return {}

    def axis_unit_labels(self, axis_index):
        metadata = self.axis_metadata(axis_index)
        position_unit = metadata.get("position_unit", "mm")
        velocity_unit = metadata.get("velocity_unit", f"{position_unit}/s")
        acceleration_unit = metadata.get("acceleration_unit", f"{position_unit}/s^2")
        jerk_unit = metadata.get("jerk_unit", f"{position_unit}/s^3")
        return position_unit, velocity_unit, acceleration_unit, jerk_unit

    def axis_unit_scale(self, axis_index):
        metadata = self.axis_metadata(axis_index)
        if metadata.get("motion_kind") == "rotary":
            return 1_000_000.0
        return self.position_counts_per_unit

    def axis_motion_scale(self, axis_index, kind="velocity"):
        metadata = self.axis_metadata(axis_index)
        key = {
            "velocity": "velocity_scale",
            "acceleration": "acceleration_scale",
            "deceleration": "deceleration_scale",
            "jerk": "jerk_scale",
        }.get(kind, "velocity_scale")
        try:
            return float(metadata.get(key, 1.0))
        except (TypeError, ValueError):
            return 1.0

    def position_count_to_unit(self, position_count, axis_index=None):
        return float(position_count)

    def position_unit_to_count(self, position_unit, axis_index=None):
        return float(position_unit)

    def velocity_count_to_unit(self, velocity_count, axis_index=None):
        return float(velocity_count)

    def motion_drive_to_unit(self, value, axis_index=None, kind="velocity"):
        return float(value)

    def motion_unit_to_drive(self, value, axis_index=None, kind="velocity"):
        return float(value)
