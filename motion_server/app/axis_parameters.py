from dataclasses import dataclass

from motion_server.app.runtime_parameters import (
    RuntimeParameterAddress,
    RuntimeParameterCache,
    RuntimeParameterDefinition,
)


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

    def __init__(self, axis_count, *, parameter_cache=None):
        self.parameter_cache = parameter_cache or RuntimeParameterCache()
        self.axes = [
            AxisParameterValues(
                None, None, [0.0, 0.0], [0.0] * 4, [0.0] * 4, {}
            )
            for _ in range(int(axis_count))
        ]
        for axis_index in range(int(axis_count)):
            for definition in axis_parameter_definitions(axis_index):
                self.parameter_cache.register(definition)

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
            self.parameter_cache.update(
                axis_parameter_key(axis_index, "user_position_unit"),
                values.user_position_unit,
            )
        if converting_unit_exponents is not None:
            values.converting_unit_exponents = list(converting_unit_exponents)
            self.parameter_cache.update(
                axis_parameter_key(axis_index, "converting_unit_exponents"),
                list(values.converting_unit_exponents),
            )
        if software_position_limits is not None:
            values.software_position_limits = list(software_position_limits)
            self.parameter_cache.update(
                axis_parameter_key(axis_index, "software_position_limits"),
                list(values.software_position_limits),
            )
        if profile_settings is not None:
            values.profile_settings = list(profile_settings)
            self.parameter_cache.update(
                axis_parameter_key(axis_index, "profile_settings"),
                list(values.profile_settings),
            )
        if motion_limits is not None:
            values.motion_limits = list(motion_limits)
            self.parameter_cache.update(
                axis_parameter_key(axis_index, "motion_limits"),
                list(values.motion_limits),
            )
        if axis_metadata is not None:
            values.axis_metadata = dict(axis_metadata)
            self.parameter_cache.update(
                axis_parameter_key(axis_index, "axis_metadata"),
                dict(values.axis_metadata),
                source="runtime_projection",
            )

    def invalidate_axis(self, axis_index, error, *, fields=None):
        selected_fields = tuple(fields or AXIS_PARAMETER_FIELDS)
        return tuple(
            self.parameter_cache.invalidate(
                axis_parameter_key(axis_index, field),
                error,
            )
            for field in selected_fields
        )

    def parameter_values(self, axis_index=None, *, valid=None):
        if axis_index is None:
            return self.parameter_cache.values(source_type="axis", valid=valid)
        return self.parameter_cache.values(
            source_type="axis",
            source_index=int(axis_index),
            valid=valid,
        )

    def snapshot(self, axis_index=None, *, valid=None):
        if axis_index is None:
            return self.parameter_cache.snapshot(source_type="axis", valid=valid)
        return self.parameter_cache.snapshot(
            source_type="axis",
            source_index=int(axis_index),
            valid=valid,
        )

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


AXIS_PARAMETER_FIELDS = (
    "user_position_unit",
    "converting_unit_exponents",
    "software_position_limits",
    "profile_settings",
    "motion_limits",
    "axis_metadata",
)


def axis_parameter_key(axis_index, field):
    return f"axis.{int(axis_index)}.{field}"


def axis_parameter_definitions(axis_index):
    axis_index = int(axis_index)
    return (
        RuntimeParameterDefinition(
            key=axis_parameter_key(axis_index, "user_position_unit"),
            address=RuntimeParameterAddress(
                "axis",
                axis_index,
                "ethercat_od",
                index=0x216E,
                subindex=1,
                role="user_position_unit",
            ),
            name="User position unit",
            data_type="uint16",
            required=True,
            refresh_on_startup=True,
            refresh_on_recovery=True,
            used_by=("unit_conversion", "status"),
        ),
        RuntimeParameterDefinition(
            key=axis_parameter_key(axis_index, "converting_unit_exponents"),
            address=RuntimeParameterAddress(
                "axis",
                axis_index,
                "ethercat_od_group",
                index=0x2194,
                role="converting_unit_exponents",
            ),
            name="Converting unit exponents",
            data_type="int8[]",
            required=True,
            refresh_on_startup=True,
            refresh_on_recovery=True,
            used_by=("unit_conversion", "status"),
        ),
        RuntimeParameterDefinition(
            key=axis_parameter_key(axis_index, "software_position_limits"),
            address=RuntimeParameterAddress(
                "axis",
                axis_index,
                "ethercat_od_group",
                index=0x607D,
                role="software_position_limits",
            ),
            name="Software position limits",
            data_type="int32[]",
            refresh_on_startup=True,
            refresh_on_recovery=True,
            used_by=("software_limit", "status"),
        ),
        RuntimeParameterDefinition(
            key=axis_parameter_key(axis_index, "profile_settings"),
            address=RuntimeParameterAddress(
                "axis",
                axis_index,
                "ethercat_od_group",
                role="profile_settings",
            ),
            name="Profile settings",
            data_type="float[]",
            refresh_on_startup=True,
            refresh_on_recovery=True,
            used_by=("command_default", "status", "rxpdo_projection"),
        ),
        RuntimeParameterDefinition(
            key=axis_parameter_key(axis_index, "motion_limits"),
            address=RuntimeParameterAddress(
                "axis",
                axis_index,
                "ethercat_od_group",
                role="motion_limits",
            ),
            name="Motion limits",
            data_type="float[]",
            refresh_on_startup=True,
            refresh_on_recovery=True,
            used_by=("motion_controller", "status"),
        ),
        RuntimeParameterDefinition(
            key=axis_parameter_key(axis_index, "axis_metadata"),
            address=RuntimeParameterAddress(
                "axis",
                axis_index,
                "axis_projection",
                role="axis_metadata",
            ),
            name="Axis unit metadata",
            data_type="object",
            refresh_on_startup=True,
            refresh_on_recovery=True,
            used_by=("unit_conversion", "status"),
        ),
    )
