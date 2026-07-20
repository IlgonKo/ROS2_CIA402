class AxisRuntime:
    """Coordinates an EtherCAT master with an independent motion controller."""

    def __init__(self, drive_manager, motion_controller):
        self.drive_manager = drive_manager
        self.motion_controller = motion_controller
        if len(self.drive_manager.drives) != self.motion_controller.axis_count:
            raise ValueError(
                "drive count must match MotionController axis_count"
            )

    @property
    def ethercat_master(self):
        return self.drive_manager.ethercat_master

    @property
    def last_diagnostics(self):
        return self.drive_manager.last_diagnostics

    @last_diagnostics.setter
    def last_diagnostics(self, value):
        self.drive_manager.last_diagnostics = value

    @property
    def slaves(self):
        return self.drive_manager.drives

    @property
    def ethercat_devices(self):
        return self.drive_manager.devices

    @property
    def sdo(self):
        return self.drive_manager.sdo

    @property
    def cycle_time(self):
        return self.ethercat_master.cycle_time

    @property
    def trajectory_generators(self):
        return self.motion_controller.trajectory_generators

    @property
    def motion_limits(self):
        return self.motion_controller.motion_limits

    @property
    def csp_counts_per_unit(self):
        return self.motion_controller.csp_counts_per_unit

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

    def connect(self):
        self.drive_manager.connect()

    def close(self):
        self.drive_manager.close()

    def expected_wkc(self):
        return self.drive_manager.expected_wkc()

    def get_dc_time_ns(self):
        return self.ethercat_master.get_dc_time_ns()

    def get_slave_input_bytes(self, slave_index=0):
        return self.ethercat_master.get_slave_input_bytes(slave_index)

    def get_slave_output_bytes(self, slave_index=0):
        return self.ethercat_master.get_slave_output_bytes(slave_index)

    def prepare_processdata(self):
        commands = self.motion_controller.update_commands(
            self.drive_manager.modes_of_operation(),
            self.drive_manager.target_positions(),
        )
        self.drive_manager.apply_commands(commands)
        self.drive_manager.prepare_processdata()

    def send_processdata(self):
        self.drive_manager.send_processdata()

    def receive_processdata(self):
        return self.drive_manager.receive_processdata()

    def set_target_positions(self, target_positions):
        self.motion_controller.set_target_positions(target_positions)

    def sync_trajectory_to_actual_positions(self):
        self.motion_controller.sync_trajectory_to_actual_positions(
            self.drive_manager.actual_positions()
        )

    def sync_trajectory_to_actual_position(self, axis_index):
        self.motion_controller.sync_trajectory_to_actual_position(
            axis_index,
            self.drive_manager.actual_positions()[axis_index],
        )

    def set_controlword_all(self, controlword):
        self.drive_manager.set_controlword_all(controlword)

    def set_mode_of_operation_all(self, mode_of_operation):
        self.drive_manager.set_mode_of_operation_all(mode_of_operation)

    def set_axis_motion_limits(self, *args, **kwargs):
        self.motion_controller.set_axis_motion_limits(*args, **kwargs)
        axis_index = int(args[0] if args else kwargs["axis_index"])
        max_velocity = args[1] if len(args) > 1 else kwargs["max_velocity"]
        acceleration = args[2] if len(args) > 2 else kwargs["acceleration"]
        deceleration = args[3] if len(args) > 3 else kwargs["deceleration"]
        self.drive_manager.set_mock_motion_limits(
            axis_index,
            max_velocity,
            acceleration,
            deceleration,
        )

    def set_axis_csp_counts_per_unit(self, *args, **kwargs):
        self.motion_controller.set_axis_csp_counts_per_unit(*args, **kwargs)

    def hold_axes(self, target_positions, axis_indices):
        actual_positions = self.drive_manager.actual_positions()
        positions = self.motion_controller.hold_axes(
            target_positions,
            actual_positions,
            axis_indices,
        )
        for axis_index in axis_indices:
            self.drive_manager.set_target_position(
                axis_index,
                positions[axis_index],
            )
        return positions

    def relative_target_positions(self, axis_indices, distances):
        return self.motion_controller.relative_target_positions(
            self.drive_manager.actual_positions(),
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
            self.drive_manager.set_target_position(
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
            self.drive_manager.actual_positions()[axis_index],
        )
