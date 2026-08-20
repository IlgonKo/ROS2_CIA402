PV_USER_POSITION_UNITS = {
    0x1000: "rad",
    0x4100: "deg",
    0xB400: "rev",
}

LINEAR_USER_POSITION_UNITS = {
    0x0100: "m",
}


class AxisUnitConverter:
    def __init__(self, axis_count):
        self.axis_count = int(axis_count)
        self.configure()

    def configure(
        self,
        user_position_units=None,
        converting_unit_exponents=None,
    ):
        self.user_position_units = self._axis_values(user_position_units, None)
        self.converting_unit_exponents = self._axis_values(
            converting_unit_exponents,
            None,
        )

    def metadata(self):
        return [self.axis_metadata(index) for index in range(self.axis_count)]

    def axis_metadata(self, axis_index):
        axis_index = int(axis_index)
        unit = self.user_position_units[axis_index]
        exponents = self._unit_exponents(axis_index)
        motion_kind = self.motion_kind(unit)
        position_unit = self.api_position_unit_name(unit)
        acceleration_scale = self.scale_from_exponent(exponents[2])
        return {
            "axis": axis_index,
            "user_position_unit": unit,
            "user_position_unit_name": self.unit_name(unit),
            "motion_kind": motion_kind,
            "pv_allowed": self.pv_allowed(unit),
            "converting_unit_exponents": exponents,
            "position_unit": position_unit,
            "velocity_unit": f"{position_unit}/s",
            "acceleration_unit": f"{position_unit}/s^2",
            "deceleration_unit": f"{position_unit}/s^2",
            "jerk_unit": f"{position_unit}/s^3",
            "position_scale": self.scale_from_exponent(exponents[0]),
            "velocity_scale": self.scale_from_exponent(exponents[1]),
            "acceleration_scale": acceleration_scale,
            "deceleration_scale": acceleration_scale,
            "jerk_scale": self.scale_from_exponent(exponents[3]),
        }

    def position_counts_per_api_unit(self, axis_index):
        axis_index = int(axis_index)
        unit = self.user_position_units[axis_index]
        if self.motion_kind(unit) in ("linear", "rotary"):
            scale = max(
                self.scale_from_exponent(self._unit_exponents(axis_index)[0]),
                1e-12,
            )
            return self.api_to_user_unit_factor(unit) / scale
        return 1.0

    def position_drive_to_api(self, axis_index, value):
        return float(value) / self.position_counts_per_api_unit(axis_index)

    def position_api_to_drive(self, axis_index, value):
        return float(value) * self.position_counts_per_api_unit(axis_index)

    def motion_drive_to_api(self, axis_index, value, kind="velocity"):
        unit = self.user_position_units[int(axis_index)]
        return (
            float(value)
            * self._motion_scale(axis_index, kind)
            / self.api_to_user_unit_factor(unit)
        )

    def motion_api_to_drive(self, axis_index, value, kind="velocity"):
        unit = self.user_position_units[int(axis_index)]
        return (
            float(value)
            * self.api_to_user_unit_factor(unit)
            / self._motion_scale(axis_index, kind)
        )

    def _motion_scale(self, axis_index, kind):
        exponent_index = {
            "velocity": 1,
            "acceleration": 2,
            "deceleration": 2,
            "jerk": 3,
        }.get(kind, 1)
        return max(
            self.scale_from_exponent(
                self._unit_exponents(axis_index)[exponent_index]
            ),
            1e-12,
        )

    def _unit_exponents(self, axis_index):
        values = self.converting_unit_exponents[int(axis_index)]
        return list(values) if values is not None else [None, None, None, None]

    def _axis_values(self, values, default):
        result = [default for _ in range(self.axis_count)] if values is None else list(values)
        if len(result) != self.axis_count:
            raise ValueError("unit configuration count must match axis count")
        return result

    @staticmethod
    def unit_name(unit):
        if unit is None:
            return "unknown"
        unit = int(unit)
        return (
            PV_USER_POSITION_UNITS.get(unit)
            or LINEAR_USER_POSITION_UNITS.get(unit)
            or f"0x{unit:04X}"
        )

    @staticmethod
    def motion_kind(unit):
        if unit is None:
            return "unknown"
        unit = int(unit)
        if unit in PV_USER_POSITION_UNITS:
            return "rotary"
        if unit in LINEAR_USER_POSITION_UNITS:
            return "linear"
        return "unknown"

    @classmethod
    def api_position_unit_name(cls, unit):
        kind = cls.motion_kind(unit)
        if kind == "rotary":
            return "deg"
        if kind == "linear":
            return "mm"
        return cls.unit_name(unit)

    @staticmethod
    def pv_allowed(unit):
        return unit is not None and int(unit) in PV_USER_POSITION_UNITS

    @staticmethod
    def scale_from_exponent(exponent):
        if exponent is None:
            return 1.0
        exponent = int(exponent)
        return 10.0 ** (-exponent) if exponent > 0 else 10.0 ** exponent

    @staticmethod
    def api_to_user_unit_factor(unit):
        if unit is None:
            return 1.0
        unit = int(unit)
        if unit in LINEAR_USER_POSITION_UNITS:
            return 0.001
        if unit == 0x1000:
            return 3.141592653589793 / 180.0
        if unit == 0x4100:
            return 1.0
        if unit == 0xB400:
            return 1.0 / 360.0
        return 1.0
