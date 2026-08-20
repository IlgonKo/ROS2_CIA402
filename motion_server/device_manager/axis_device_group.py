from dataclasses import dataclass

from motion_server.device_manager.axis_unit_conversion import AxisUnitConverter


@dataclass(frozen=True)
class AxisBinding:
    axis_index: int
    slave_index: int


@dataclass
class AxisCommand:
    target_position: int | None = None
    target_velocity: int | None = None
    velocity_offset: int | None = None
    controlword: int | None = None
    mode_of_operation: int | None = None


@dataclass(frozen=True)
class AxisFeedback:
    statusword: int
    mode_of_operation_display: int
    actual_position: float
    actual_velocity: float

    @property
    def faulted(self):
        return bool(self.statusword & 0x0008)

    @property
    def operation_enabled(self):
        return bool(self.statusword & 0x0004)


class AxisSdoAccess:
    def __init__(self, sdo, axis_bindings):
        self._sdo = sdo
        self._slave_indices = [
            binding.slave_index for binding in axis_bindings
        ]

    def __getattr__(self, name):
        operation = getattr(self._sdo, name)

        def axis_operation(axis_index, *args, **kwargs):
            slave_index = self._slave_indices[int(axis_index)]
            return operation(slave_index, *args, **kwargs)

        return axis_operation


class AxisDeviceGroup:
    """Motion-axis view over EtherCAT devices."""

    def __init__(self, ethercat_master, axis_bindings):
        self.ethercat_master = ethercat_master
        self.axis_bindings = list(axis_bindings)
        self._validate_bindings()
        self.devices = [
            ethercat_master.slaves[binding.slave_index]
            for binding in self.axis_bindings
        ]
        self.sdo = AxisSdoAccess(ethercat_master.sdo, self.axis_bindings)
        self.last_diagnostics = []
        self.unit_converter = AxisUnitConverter(len(self.devices))
        self.configure_unit_conversion()

    def configure_unit_conversion(
        self,
        user_position_units=None,
        converting_unit_exponents=None,
    ):
        self.unit_converter.configure(
            user_position_units,
            converting_unit_exponents,
        )

    @property
    def user_position_units(self):
        return self.unit_converter.user_position_units

    @property
    def converting_unit_exponents(self):
        return self.unit_converter.converting_unit_exponents

    def unit_metadata(self):
        return self.unit_converter.metadata()

    def user_position_unit_name(self, unit):
        return self.unit_converter.unit_name(unit)

    def pv_allowed(self, axis_index):
        return self.unit_converter.pv_allowed(
            self.user_position_units[int(axis_index)]
        )

    def position_counts_per_api_unit(self, axis_index):
        return self.unit_converter.position_counts_per_api_unit(axis_index)

    def position_drive_to_api(self, axis_index, value):
        return self.unit_converter.position_drive_to_api(axis_index, value)

    def position_api_to_drive(self, axis_index, value):
        return self.unit_converter.position_api_to_drive(axis_index, value)

    def motion_drive_to_api(self, axis_index, value, kind="velocity"):
        return self.unit_converter.motion_drive_to_api(axis_index, value, kind)

    def motion_api_to_drive(self, axis_index, value, kind="velocity"):
        return self.unit_converter.motion_api_to_drive(axis_index, value, kind)

    def feedback(self):
        return [
            AxisFeedback(
                statusword=int(axis.txpdo.statusword),
                mode_of_operation_display=int(
                    axis.txpdo.mode_of_operation_display
                ),
                actual_position=float(axis.txpdo.actual_position),
                actual_velocity=float(axis.txpdo.actual_velocity),
            )
            for axis in self.devices
        ]

    def modes_of_operation(self):
        return [int(axis.rxpdo.mode_of_operation) for axis in self.devices]

    def target_positions(self):
        return [int(axis.rxpdo.target_position) for axis in self.devices]

    def actual_positions(self):
        return [float(item.actual_position) for item in self.feedback()]

    def set_target_position(self, axis_index, target_position):
        axis = self.devices[int(axis_index)]
        axis.rxpdo.target_position = int(round(target_position))

    def apply_commands(self, commands):
        for axis, command in zip(self.devices, commands):
            if command is None:
                continue
            if isinstance(command, dict):
                command = AxisCommand(**command)
            for field in (
                "target_position",
                "target_velocity",
                "velocity_offset",
                "controlword",
                "mode_of_operation",
            ):
                value = getattr(command, field)
                if value is not None and axis.rxpdo.has_field(field):
                    setattr(axis.rxpdo, field, value)

    def set_controlword_all(self, controlword):
        for axis in self.devices:
            axis.rxpdo.controlword = controlword

    def set_mode_of_operation_all(self, mode_of_operation):
        for axis in self.devices:
            axis.rxpdo.mode_of_operation = mode_of_operation

    def set_mock_motion_limits(
        self,
        axis_index,
        max_velocity,
        acceleration,
        deceleration,
    ):
        axis = getattr(self.devices[axis_index], "axis", None)
        if axis is not None:
            axis.set_motion_limits(
                self.motion_api_to_drive(axis_index, max_velocity),
                self.motion_api_to_drive(axis_index, acceleration, "acceleration"),
                self.motion_api_to_drive(axis_index, deceleration, "deceleration"),
            )

    def _validate_bindings(self):
        axis_indices = [binding.axis_index for binding in self.axis_bindings]
        if axis_indices != list(range(len(self.axis_bindings))):
            raise ValueError(
                "axis bindings must have ordered, contiguous axis indices"
            )
        slave_indices = [binding.slave_index for binding in self.axis_bindings]
        if len(slave_indices) != len(set(slave_indices)):
            raise ValueError("each axis must bind to a unique slave")
        device_count = len(self.ethercat_master.slaves)
        if any(index < 0 or index >= device_count for index in slave_indices):
            raise ValueError("axis binding contains an invalid slave index")
