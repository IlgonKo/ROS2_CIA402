from motion_server.diagnostic import DiagnosticManager


class AxisRuntime:
    """Coordinates an EtherCAT master with an independent motion controller."""

    def __init__(
        self,
        device_manager,
        motion_controller,
        diagnostic_manager=None,
    ):
        self.device_manager = device_manager
        self.motion_controller = motion_controller
        self.diagnostic_manager = diagnostic_manager or DiagnosticManager()
        if len(self.device_manager.axis_devices) != self.motion_controller.axis_count:
            raise ValueError(
                "axis device count must match MotionController axis_count"
            )

    @property
    def ethercat_master(self):
        return self.device_manager.ethercat_master

    @property
    def last_diagnostics(self):
        return self.device_manager.last_diagnostics

    @last_diagnostics.setter
    def last_diagnostics(self, value):
        self.device_manager.last_diagnostics = value

    @property
    def slaves(self):
        return self.device_manager.axis_devices

    @property
    def ethercat_devices(self):
        return self.device_manager.ethercat_devices

    @property
    def sdo(self):
        return self.device_manager.sdo

    @property
    def cycle_time(self):
        return self.ethercat_master.cycle_time

    @property
    def trajectory_generators(self):
        return self.motion_controller.trajectory_generators

    @property
    def motion_limits(self):
        return self.motion_controller.motion_limits

    def axis_position_counts_per_api_unit(self, axis_index):
        return self.motion_controller.position_counts_per_api_unit(axis_index)

    @property
    def csp_velocity_offset_enabled(self):
        return self.motion_controller.csp_velocity_offset_enabled

    @property
    def last_csp_command_steps(self):
        return self.motion_controller.last_csp_command_steps

    @property
    def last_csp_output_steps(self):
        return self.motion_controller.last_csp_output_steps

    @property
    def last_tx_dc_time_ns(self):
        return self.ethercat_master.last_tx_dc_time_ns

    @last_tx_dc_time_ns.setter
    def last_tx_dc_time_ns(self, value):
        self.ethercat_master.last_tx_dc_time_ns = value

    def __getattr__(self, name):
        if name.startswith("last_") or name in {"dc_time_ns", "wkc"}:
            return getattr(self.ethercat_master, name)
        raise AttributeError(name)

    def connect(self, target_state=None):
        self.device_manager.connect(target_state=target_state)

    def enter_operational(self):
        self.device_manager.enter_operational()

    def close(self):
        self.device_manager.close()

    def expected_wkc(self):
        return self.device_manager.expected_wkc()

    def get_dc_time_ns(self):
        return self.ethercat_master.get_dc_time_ns()

    def get_slave_input_bytes(self, slave_index=0):
        return self.ethercat_master.get_slave_input_bytes(slave_index)

    def get_slave_output_bytes(self, slave_index=0):
        return self.ethercat_master.get_slave_output_bytes(slave_index)

    def prepare_processdata(self):
        commands = self.motion_controller.update_commands(
            self.device_manager.axes.modes_of_operation(),
            self.device_manager.axes.target_positions(),
        )
        self.device_manager.axes.apply_commands(commands)
        self.device_manager.prepare_processdata()

    def send_processdata(self):
        self.device_manager.send_processdata()

    def receive_processdata(self):
        return self.device_manager.receive_processdata()

    def set_target_positions(self, target_positions):
        self.motion_controller.set_target_positions(target_positions)

    def sync_trajectory_to_actual_positions(self):
        self.motion_controller.sync_trajectory_to_actual_positions(
            self.device_manager.axes.actual_positions()
        )

    def sync_trajectory_to_actual_position(self, axis_index):
        self.motion_controller.sync_trajectory_to_actual_position(
            axis_index,
            self.device_manager.axes.actual_positions()[axis_index],
        )

    def set_controlword_all(self, controlword):
        self.device_manager.axes.set_controlword_all(controlword)

    def set_mode_of_operation_all(self, mode_of_operation):
        self.device_manager.axes.set_mode_of_operation_all(mode_of_operation)

    def set_axis_motion_limits(self, *args, **kwargs):
        self.motion_controller.set_axis_motion_limits(*args, **kwargs)

    def set_axis_position_counts_per_api_unit(self, *args, **kwargs):
        self.motion_controller.set_axis_position_counts_per_api_unit(
            *args,
            **kwargs,
        )

    def hold_axes(self, target_positions, axis_indices):
        actual_positions = self.device_manager.axes.actual_positions()
        positions = self.motion_controller.hold_axes(
            target_positions,
            actual_positions,
            axis_indices,
        )
        for axis_index in axis_indices:
            self.device_manager.axes.set_target_position(
                axis_index,
                positions[axis_index],
            )
        return positions

    def relative_target_positions(self, axis_indices, distances):
        return self.motion_controller.relative_target_positions(
            self.device_manager.axes.actual_positions(),
            axis_indices,
            distances,
        )

    def trajectory_progress(self, axis_indices):
        return self.motion_controller.trajectory_progress(axis_indices)

    def complete_trajectory(self, axis_indices, final_positions):
        completed = self.motion_controller.complete_trajectory(
            axis_indices,
            final_positions,
        )
        for axis_index, final_position in completed.items():
            self.device_manager.axes.set_target_position(
                axis_index,
                final_position,
            )
        return completed

    def command_positions(self, axis_indices):
        return self.motion_controller.command_positions(axis_indices)

    def set_axis_trajectories(self, axis_indices, timed_points_by_axis):
        self.motion_controller.set_axis_trajectories(
            axis_indices,
            timed_points_by_axis,
        )

    def sync_velocity_command(self, axis_index, velocity):
        self.motion_controller.sync_velocity_command(
            axis_index,
            velocity,
            self.device_manager.axes.actual_positions()[axis_index],
        )
