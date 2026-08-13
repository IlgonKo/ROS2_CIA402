from motion_server.device_manager.axis_device_group import AxisDeviceGroup
from motion_server.device_manager.io_device_group import IoDeviceGroup
from motion_server.device_manager.sdo_access import LogicalSdoAccess


class DeviceManager:
    """Owns EtherCAT devices and exposes logical axis/io groups."""

    def __init__(self, ethercat_master, axis_bindings):
        self.ethercat_master = ethercat_master
        self.axes = AxisDeviceGroup(ethercat_master, axis_bindings)
        self.io = IoDeviceGroup(ethercat_master)
        self.sdo = LogicalSdoAccess(self.axes.sdo, self.io.sdo)

    @property
    def axis_devices(self):
        return self.axes.devices

    @property
    def drives(self):
        return self.axis_devices

    @property
    def drive_bindings(self):
        return self.axes.axis_bindings

    @property
    def last_diagnostics(self):
        return self.axes.last_diagnostics

    @last_diagnostics.setter
    def last_diagnostics(self, value):
        self.axes.last_diagnostics = value

    @property
    def ethercat_devices(self):
        return self.ethercat_master.slaves

    @property
    def devices(self):
        return self.ethercat_devices

    def connect(self, target_state=None):
        self.ethercat_master.connect(target_state=target_state)

    def enter_operational(self):
        self.ethercat_master.enter_operational()

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

    def get_slave_input_bytes(self, slave_index=0):
        return self.ethercat_master.get_slave_input_bytes(slave_index)

    def get_slave_output_bytes(self, slave_index=0):
        return self.ethercat_master.get_slave_output_bytes(slave_index)

    def configure_unit_conversion(self, *args, **kwargs):
        return self.axes.configure_unit_conversion(*args, **kwargs)

    @property
    def user_position_units(self):
        return self.axes.user_position_units

    @property
    def converting_unit_exponents(self):
        return self.axes.converting_unit_exponents

    def unit_metadata(self):
        return self.axes.unit_metadata()

    def user_position_unit_name(self, unit):
        return self.axes.user_position_unit_name(unit)

    def pv_allowed(self, axis_index):
        return self.axes.pv_allowed(axis_index)

    def position_counts_per_api_unit(self, axis_index):
        return self.axes.position_counts_per_api_unit(axis_index)

    def position_drive_to_api(self, axis_index, value):
        return self.axes.position_drive_to_api(axis_index, value)

    def position_api_to_drive(self, axis_index, value):
        return self.axes.position_api_to_drive(axis_index, value)

    def motion_drive_to_api(self, axis_index, value, kind="velocity"):
        return self.axes.motion_drive_to_api(axis_index, value, kind)

    def motion_api_to_drive(self, axis_index, value, kind="velocity"):
        return self.axes.motion_api_to_drive(axis_index, value, kind)

    def feedback(self):
        return self.axes.feedback()

    def modes_of_operation(self):
        return self.axes.modes_of_operation()

    def target_positions(self):
        return self.axes.target_positions()

    def actual_positions(self):
        return self.axes.actual_positions()

    def set_target_position(self, axis_index, target_position):
        return self.axes.set_target_position(axis_index, target_position)

    def apply_commands(self, commands):
        return self.axes.apply_commands(commands)

    def set_controlword_all(self, controlword):
        return self.axes.set_controlword_all(controlword)

    def set_mode_of_operation_all(self, mode_of_operation):
        return self.axes.set_mode_of_operation_all(mode_of_operation)

    def set_mock_motion_limits(
        self,
        axis_index,
        max_velocity,
        acceleration,
        deceleration,
    ):
        return self.axes.set_mock_motion_limits(
            axis_index,
            max_velocity,
            acceleration,
            deceleration,
        )
