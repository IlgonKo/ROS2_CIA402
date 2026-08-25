from dataclasses import dataclass


@dataclass
class AxisParameterValues:
    user_position_unit: int | None
    converting_unit_exponents: list | None
    software_position_limits: list
    profile_settings: list
    motion_limits: list
    axis_metadata: dict


class AxisParameterRuntimeCache:
    """Single server-side cache of axis parameters read from device OD."""

    def __init__(self, axis_count):
        self.axes = [
            AxisParameterValues(
                None, None, [0.0, 0.0], [0.0] * 4, [0.0] * 4, {}
            )
            for _ in range(int(axis_count))
        ]

    def update_axis(
        self,
        axis_index,
        *,
        user_position_unit=None,
        converting_unit_exponents=None,
        software_position_limits=None,
        profile_settings=None,
        motion_limits=None,
        axis_metadata=None,
    ):
        values = self.axes[int(axis_index)]
        if user_position_unit is not None:
            values.user_position_unit = int(user_position_unit)
        if converting_unit_exponents is not None:
            values.converting_unit_exponents = list(converting_unit_exponents)
        if software_position_limits is not None:
            values.software_position_limits = list(software_position_limits)
        if profile_settings is not None:
            values.profile_settings = list(profile_settings)
        if motion_limits is not None:
            values.motion_limits = list(motion_limits)
        if axis_metadata is not None:
            values.axis_metadata = dict(axis_metadata)

    @property
    def user_position_units(self):
        return [axis.user_position_unit for axis in self.axes]

    @property
    def converting_unit_exponents(self):
        return [axis.converting_unit_exponents for axis in self.axes]

    @property
    def software_position_limits(self):
        return [axis.software_position_limits for axis in self.axes]

    @property
    def profile_settings(self):
        return [axis.profile_settings for axis in self.axes]

    @property
    def motion_limits(self):
        return [axis.motion_limits for axis in self.axes]

    @property
    def axis_metadata(self):
        return [axis.axis_metadata for axis in self.axes]
