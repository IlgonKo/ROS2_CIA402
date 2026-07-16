from dataclasses import dataclass

from motion_server.drive.unit_conversion import DriveUnitConverter


@dataclass(frozen=True)
class DriveBinding:
    axis_index: int
    slave_index: int


@dataclass
class DriveCommand:
    target_position: int | None = None
    target_velocity: int | None = None
    velocity_offset: int | None = None
    controlword: int | None = None
    mode_of_operation: int | None = None


@dataclass(frozen=True)
class DriveFeedback:
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


class DriveSdoAccess:
    def __init__(self, sdo, drive_bindings):
        self._sdo = sdo
        self._slave_indices = [
            binding.slave_index for binding in drive_bindings
        ]

    def __getattr__(self, name):
        operation = getattr(self._sdo, name)

        def drive_operation(axis_index, *args, **kwargs):
            slave_index = self._slave_indices[int(axis_index)]
            return operation(slave_index, *args, **kwargs)

        return drive_operation


class DriveManager:
    """Owns drive-to-slave mapping and drive communication."""

    def __init__(self, ethercat_master, drive_bindings):
        self.ethercat_master = ethercat_master
        self.drive_bindings = list(drive_bindings)
        self._validate_bindings()
        self.drives = [
            ethercat_master.slaves[binding.slave_index]
            for binding in self.drive_bindings
        ]
        self.sdo = DriveSdoAccess(
            ethercat_master.sdo,
            self.drive_bindings,
        )
        self.last_diagnostics = []
        self.unit_converter = DriveUnitConverter(len(self.drives))
        self.configure_unit_conversion()

    def configure_unit_conversion(
        self,
        user_position_units=None,
        converting_unit_exponents=None,
        position_counts_per_unit=1.0,
    ):
        self.unit_converter.configure(
            user_position_units,
            converting_unit_exponents,
            position_counts_per_unit,
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

    @property
    def devices(self):
        return self.ethercat_master.slaves

    def connect(self):
        self.ethercat_master.connect()

    def close(self):
        self.ethercat_master.close()

    def prepare_processdata(self):
        self.ethercat_master.prepare_processdata()

    def send_processdata(self):
        self.ethercat_master.send_processdata()

    def receive_processdata(self):
        return self.ethercat_master.receive_processdata()

    def expected_wkc(self):
        return self.ethercat_master.expected_wkc()

    def feedback(self):
        return [
            DriveFeedback(
                statusword=int(drive.txpdo.statusword),
                mode_of_operation_display=int(
                    drive.txpdo.mode_of_operation_display
                ),
                actual_position=float(drive.txpdo.actual_position),
                actual_velocity=float(drive.txpdo.actual_velocity),
            )
            for drive in self.drives
        ]

    def modes_of_operation(self):
        return [int(drive.rxpdo.mode_of_operation) for drive in self.drives]

    def target_positions(self):
        return [int(drive.rxpdo.target_position) for drive in self.drives]

    def actual_positions(self):
        return [float(item.actual_position) for item in self.feedback()]

    def set_target_position(self, axis_index, target_position):
        drive = self.drives[int(axis_index)]
        drive.rxpdo.target_position = int(round(target_position))

    def apply_commands(self, commands):
        for drive, command in zip(self.drives, commands):
            if command is None:
                continue
            if isinstance(command, dict):
                command = DriveCommand(**command)
            for field in (
                "target_position",
                "target_velocity",
                "velocity_offset",
                "controlword",
                "mode_of_operation",
            ):
                value = getattr(command, field)
                if value is not None and drive.rxpdo.has_field(field):
                    setattr(drive.rxpdo, field, value)

    def set_controlword_all(self, controlword):
        for drive in self.drives:
            drive.rxpdo.controlword = controlword

    def set_mode_of_operation_all(self, mode_of_operation):
        for drive in self.drives:
            drive.rxpdo.mode_of_operation = mode_of_operation

    def set_mock_motion_limits(
        self,
        axis_index,
        max_velocity,
        acceleration,
        deceleration,
    ):
        axis = getattr(self.drives[axis_index], "axis", None)
        if axis is not None:
            axis.set_motion_limits(max_velocity, acceleration, deceleration)

    def _validate_bindings(self):
        axis_indices = [binding.axis_index for binding in self.drive_bindings]
        if axis_indices != list(range(len(self.drive_bindings))):
            raise ValueError(
                "drive bindings must have ordered, contiguous axis indices"
            )
        slave_indices = [binding.slave_index for binding in self.drive_bindings]
        if len(slave_indices) != len(set(slave_indices)):
            raise ValueError("each drive must bind to a unique slave")
        device_count = len(self.ethercat_master.slaves)
        if any(index < 0 or index >= device_count for index in slave_indices):
            raise ValueError("drive binding contains an invalid slave index")
