from device.virtual_servo_drive.od_model import VirtualObjectDictionary
from device.cia402 import CiA402StateMachine


class VirtualCiA402Servo:
    def __init__(self, cycle_time=0.001, device_profile=None):
        self.cycle_time = cycle_time
        if device_profile is None:
            raise ValueError("VirtualCiA402Servo requires an explicit device_profile")
        self.device_profile = device_profile

        self.od = VirtualObjectDictionary(device_profile)
        self.sm = CiA402StateMachine()

        self.actual_position = 0.0
        self.actual_velocity = 0.0

        self.kp = 5.0
        self.target_reached = False
        self.window_counter = 0
        self.previous_controlword = 0
        self.pp_active = False
        self.pp_target_position = self.actual_position
        self.pp_setpoint_ack = False
        self.halt_active = False
        self.homing_active = False
        self.homing_counter = 0
        self.homing_referenced = False
        self.homing_error = False
        self.software_limit_warning = False
        self.position_target_rejected = False

        #self.init_object_dictionary()

    def apply_rxpdo(self, rxpdo):
        self.set_controlword(rxpdo.controlword)
        self.set_mode(rxpdo.mode_of_operation)
        if rxpdo.has_field("target_position"):
            self.set_target_position(rxpdo.target_position)
        if rxpdo.has_field("profile_velocity"):
            self.set_profile_velocity(rxpdo.profile_velocity)
        if rxpdo.has_field("target_velocity"):
            self.set_target_velocity(rxpdo.target_velocity)
        handled = {
            "controlword",
            "mode_of_operation",
            "target_position",
            "profile_velocity",
            "target_velocity",
        }
        for obj in rxpdo.mapping:
            if obj.index != 0 and obj.field is not None and obj.field not in handled:
                self.od.write(obj.index, getattr(rxpdo, obj.field), obj.subindex)

    def set_controlword(self, controlword):
        self.od.write(0x6040, int(controlword))

    def get_statusword(self):
        return self.od.read(0x6041)

    def update(self):
        self.process_cycle()

    def set_mode(self,mode):
        next_mode = int(mode)
        current_mode = int(self.od.read(0x6060))
        if next_mode != current_mode:
            self.stop_at_current_position()
            if next_mode != 6:
                self.homing_active = False
                self.homing_error = False
        self.od.write(0x6060,next_mode)
        self.od.write(0x6061,next_mode)

    def set_target_position(self, position):
        if self._position_command_requires_reference() and not self.homing_referenced:
            return

        if not self._position_target_is_within_software_limits(position):
            self.software_limit_warning = True
            self.position_target_rejected = True
            self.stop_at_current_position()
            self.target_reached = False
            return

        self.position_target_rejected = False
        if not self._actual_position_exceeds_software_limits():
            self.software_limit_warning = False

        current_target = self.od.read(0x607A)
        if position != current_target:
            self.target_reached = False
            self.window_counter = 0
        self.od.write(0x607A, position)

    def set_target_velocity(self,velocity):
        self.od.write(0x60FF,velocity)

    def set_profile_velocity(self, velocity):
        self.od.write(0x6081, velocity)

    def set_software_position_limits(self, negative_limit, positive_limit):
        self.od.write(0x607D, negative_limit, 1)
        self.od.write(0x607D, positive_limit, 2)

    def get_software_position_limits(self):
        return {
            "negative_limit": self.od.read(0x607D, 1),
            "positive_limit": self.od.read(0x607D, 2),
        }

    def set_position_loop_gain(self, kp):
        self.kp = float(kp)

    def get_position_loop_gain(self):
        return self.kp

    def get_position(self):
        return self.od.read(0x6064)

    def get_target_position(self):
        return self.od.read(0x607A)

    def get_velocity(self):
        return self.od.read(0x606C)

    def is_target_reached(self):
        return self.target_reached

    def stop_at_current_position(self):
        self.actual_velocity = 0.0
        self.pp_active = False
        self.pp_target_position = self.actual_position
        self.od.write(0x607A, self.actual_position)
        self.od.write(0x6064, self.actual_position)
        self.od.write(0x606C, self.actual_velocity)
        self.window_counter = 0
        self.target_reached = True

    # ---------------------------------
    # CiA402
    # ---------------------------------

    def is_in_position(self):
        target = self.od.read(0x607A)

        actual = self.od.read(0x6064)

        window = self.od.read(0x6067)

        return abs(target - actual) <= window

    def update_target_reached(self):
        if self.is_in_position():
            self.window_counter += 1
        else:
            self.window_counter = 0
            self.target_reached = False

        window_time_ms = self.od.read(0x6068)

        required_count = max(1,int(window_time_ms /(self.cycle_time *1000)))

        if self.window_counter >= required_count:
            self.target_reached = True

    def _position_command_requires_reference(self):
        return int(self.od.read(0x6060)) in {1, 8}

    # ---------------------------------
    # Main Cycle
    # ---------------------------------

    def process_cycle(self):
        controlword = self.od.read(0x6040)
        self.halt_active = bool(controlword & (1 << 8))
        was_operation_enabled = self.sm.get_statusword() == 0x0027

        self.sm.process(controlword)
        is_operation_enabled = self.sm.get_statusword() == 0x0027
        if was_operation_enabled and not is_operation_enabled:
            self.stop_at_current_position()

        mode = self.od.read(0x6060)

        if mode == 1:
            self.process_pp()
        elif mode == 3:
            self.process_pv()
        elif mode == 8:
            self.process_csp()
        elif mode == 6:
            self.process_homing()
        elif mode == -3:
            self.process_jog()

        statusword = self.sm.get_statusword()

        if self.target_reached:
            statusword |= (1 << 10)
        if self.pp_setpoint_ack:
            statusword |= (1 << 12)
        if self._is_moving():
            statusword |= (1 << 8)
        if self._software_limit_is_active():
            statusword |= (1 << 7)
            statusword |= (1 << 11)
        if self.homing_referenced:
            statusword |= (1 << 15)
        if mode == 6 and self.homing_error:
            statusword |= (1 << 3)

        self.od.write(0x6041, statusword)
        self.previous_controlword = controlword

    # ---------------------------------
    # Homing
    # ---------------------------------

    def process_homing(self):
        if self.sm.get_statusword() != 0x0027:
            return

        controlword = self.od.read(0x6040)
        start_homing = (
            bool(controlword & (1 << 4)) and
            not bool(self.previous_controlword & (1 << 4))
        )

        if start_homing:
            self.homing_active = True
            self.homing_counter = max(1, int(0.1 / self.cycle_time))
            self.homing_referenced = False
            self.homing_error = False
            self.actual_velocity = 0.0
            self._write_actual_feedback()
            self.target_reached = False

        if not self.homing_active:
            return

        self.homing_counter -= 1
        if self.homing_counter > 0:
            return

        self.actual_position = 0.0
        self.actual_velocity = 0.0
        self.od.write(0x607A, self.actual_position)
        self._write_actual_feedback()
        self.target_reached = True
        self.homing_active = False
        self.homing_referenced = True

    # ---------------------------------
    # PP
    # ---------------------------------

    def process_pp(self):
        if self.sm.get_statusword() != 0x0027:
            return

        if self.halt_active:
            self.pp_active = False
            self.pp_setpoint_ack = False
            self._decelerate_to_stop()
            self._write_actual_feedback()
            self.target_reached = abs(self.actual_velocity) <= 1e-9
            return

        if not self.homing_referenced:
            self.pp_active = False
            self.pp_setpoint_ack = False
            self.target_reached = False
            self._decelerate_to_stop()
            self._write_actual_feedback()
            return

        controlword = self.od.read(0x6040)
        new_setpoint = (
            bool(controlword & (1 << 4)) and
            not bool(self.previous_controlword & (1 << 4))
        )

        if new_setpoint:
            if self.position_target_rejected:
                self.pp_active = False
                self.pp_setpoint_ack = False
                self._decelerate_to_stop()
                self._write_actual_feedback()
                return
            else:
                self.pp_target_position = self.od.read(0x607A)
                self.pp_active = True
            self.target_reached = False
            self.window_counter = 0

        self.pp_setpoint_ack = bool(controlword & (1 << 4))

        if not self.pp_active:
            self._decelerate_to_stop()
            self._write_actual_feedback()
            self.update_target_reached()
            return

        target = self.pp_target_position
        profile_vel = abs(float(self.od.read(0x6081)))
        positive_limit = abs(float(self.od.read(0x607F)))
        negative_limit = abs(float(self.od.read(0x2183, 0x0C)) * 1000.0)
        max_profile_vel = positive_limit
        if target < self.actual_position and negative_limit > 0:
            max_profile_vel = negative_limit
        max_vel = min(profile_vel, max_profile_vel) if max_profile_vel > 0 else profile_vel
        accel = abs(float(self.od.read(0x6083)))
        decel = abs(float(self.od.read(0x6084)))
        window = abs(float(self.od.read(0x6067)))
        dt = self.cycle_time

        error = target - self.actual_position
        distance = abs(error)
        if distance <= window and abs(self.actual_velocity) <= max(
            self._acceleration_to_velocity_delta(decel, dt),
            1e-9,
        ):
            self.actual_position = target
            self.actual_velocity = 0.0
            self.pp_active = False
            self._write_actual_feedback()
            self.update_target_reached()
            return

        direction = 1.0 if error >= 0.0 else -1.0
        velocity_toward_target = self.actual_velocity * direction
        position_velocity_toward_target = (
            self._velocity_to_position_rate(self.actual_velocity) * direction
        )
        decel_position_rate = self._acceleration_to_position_rate(decel)
        stopping_distance = (
            max(position_velocity_toward_target, 0.0) ** 2
            / (2.0 * decel_position_rate)
            if decel_position_rate > 0.0
            else 0.0
        )

        if velocity_toward_target < 0.0:
            desired_velocity = 0.0
            velocity_limit = decel
        elif distance <= stopping_distance:
            desired_velocity = 0.0
            velocity_limit = decel
        else:
            desired_velocity = direction * max_vel
            velocity_limit = accel

        self.actual_velocity = self._move_towards(
            self.actual_velocity,
            desired_velocity,
            self._acceleration_to_velocity_delta(velocity_limit, dt),
        )
        next_position = (
            self.actual_position
            + self._velocity_to_position_rate(self.actual_velocity) * dt
        )

        if (
            (target - self.actual_position) == 0.0 or
            (target - self.actual_position) * (target - next_position) <= 0.0
        ):
            self.actual_position = target
            self.actual_velocity = 0.0
            self.pp_active = False
        else:
            self.actual_position = next_position

        self._write_actual_feedback()
        self.update_target_reached()

    def _decelerate_to_stop(self):
        decel = abs(float(self.od.read(0x6084)))
        self.actual_velocity = self._move_towards(
            self.actual_velocity,
            0.0,
            self._acceleration_to_velocity_delta(decel, self.cycle_time),
        )
        self.actual_position += (
            self._velocity_to_position_rate(self.actual_velocity)
            * self.cycle_time
        )

    def _move_towards(self, current, target, max_delta):
        if max_delta <= 0.0:
            return current

        delta = target - current
        if abs(delta) <= max_delta:
            return target

        return current + max_delta * (1.0 if delta > 0.0 else -1.0)

    def _write_actual_feedback(self):
        self.od.write(0x6064, self.actual_position)
        self.od.write(0x606C, self.actual_velocity)

    def _scale_from_exponent(self, exponent):
        exponent = int(exponent)
        return 10.0 ** (-exponent) if exponent > 0 else 10.0 ** exponent

    def _unit_scale(self, subindex, default=1.0):
        try:
            return self._scale_from_exponent(self.od.read(0x2194, subindex))
        except Exception:
            return float(default)

    def _position_scale(self):
        return max(self._unit_scale(0x01), 1e-12)

    def _velocity_scale(self):
        return max(self._unit_scale(0x02), 1e-12)

    def _acceleration_scale(self):
        return max(self._unit_scale(0x03), 1e-12)

    def _velocity_to_position_rate(self, velocity):
        return float(velocity) * self._velocity_scale() / self._position_scale()

    def _position_rate_to_velocity(self, position_rate):
        return float(position_rate) * self._position_scale() / self._velocity_scale()

    def _acceleration_to_position_rate(self, acceleration):
        return float(acceleration) * self._acceleration_scale() / self._position_scale()

    def _acceleration_to_velocity_delta(self, acceleration, dt):
        return (
            float(acceleration)
            * self._acceleration_scale()
            / self._velocity_scale()
            * float(dt)
        )

    # ---------------------------------
    # PV
    # ---------------------------------

    def process_pv(self):
        if self.sm.get_statusword() != 0x0027:
            return

        target_velocity = 0.0 if self.halt_active else float(self.od.read(0x60FF))
        positive_limit = abs(float(self.od.read(0x607F)))
        negative_limit = abs(float(self.od.read(0x2183, 0x0C)) * 1000.0)
        if target_velocity >= 0.0 and positive_limit > 0.0:
            target_velocity = min(target_velocity, positive_limit)
        elif target_velocity < 0.0 and negative_limit > 0.0:
            target_velocity = max(target_velocity, -negative_limit)

        accel = float(self.od.read(0x6083))
        decel = float(self.od.read(0x6084))
        if abs(target_velocity) > abs(self.actual_velocity):
            limit = accel
        else:
            limit = decel

        self.actual_velocity = self._move_towards(
            self.actual_velocity,
            target_velocity,
            self._acceleration_to_velocity_delta(limit, self.cycle_time),
        )
        self.actual_position += (
            self._velocity_to_position_rate(self.actual_velocity)
            * self.cycle_time
        )
        self._write_actual_feedback()
        self.target_reached = abs(self.actual_velocity - target_velocity) <= max(
            self._acceleration_to_velocity_delta(limit, self.cycle_time),
            1e-9,
        )

    # ---------------------------------
    # Jog
    # ---------------------------------

    def process_jog(self):
        if self.sm.get_statusword() != 0x0027:
            return

        controlword = self.od.read(0x6040)
        positive = bool(controlword & (1 << 4))
        negative = bool(controlword & (1 << 5))
        if positive == negative or self.halt_active:
            target_velocity = 0.0
        else:
            direction = 1.0 if positive else -1.0
            target_velocity = direction * self._jog_velocity_limit(controlword)

        accel = float(self.od.read(0x6083))
        decel = float(self.od.read(0x6084))
        target_velocity = self._limit_jog_velocity_at_software_limit(target_velocity)
        if abs(target_velocity) > abs(self.actual_velocity):
            limit = accel
        else:
            limit = decel

        self.actual_velocity = self._move_towards(
            self.actual_velocity,
            target_velocity,
            self._acceleration_to_velocity_delta(limit, self.cycle_time),
        )
        self.actual_position += (
            self._velocity_to_position_rate(self.actual_velocity)
            * self.cycle_time
        )
        self._write_actual_feedback()
        self.target_reached = abs(self.actual_velocity) <= 1e-9

    def _jog_velocity_limit(self, controlword):
        profile_velocity = abs(float(self.od.read(0x6081)))
        positive_limit = abs(float(self.od.read(0x607F)))
        negative_limit = abs(float(self.od.read(0x2183, 0x0C)) * 1000.0)
        configured_limits = [
            value for value in (profile_velocity, positive_limit, negative_limit)
            if value > 0.0
        ]
        max_velocity = min(configured_limits) if configured_limits else 0.0

        if controlword & (1 << 12):
            speed_factor = 1.0
        elif controlword & (1 << 11):
            speed_factor = 0.25
        else:
            speed_factor = 0.5

        return max_velocity * speed_factor

    def _limit_jog_velocity_at_software_limit(self, target_velocity):
        target_velocity = float(target_velocity)
        if abs(target_velocity) <= 1e-12:
            return 0.0

        negative_limit, positive_limit = self._software_position_limits()
        if target_velocity > 0.0 and self.actual_position >= positive_limit:
            return 0.0
        if target_velocity < 0.0 and self.actual_position <= negative_limit:
            return 0.0
        return target_velocity

    def _software_position_limits(self):
        negative_limit = float(self.od.read(0x607D, 1))
        positive_limit = float(self.od.read(0x607D, 2))
        if negative_limit > positive_limit:
            return positive_limit, negative_limit
        return negative_limit, positive_limit

    def _position_target_is_within_software_limits(self, position):
        negative_limit, positive_limit = self._software_position_limits()
        position = float(position)
        return negative_limit <= position <= positive_limit

    def _actual_position_exceeds_software_limits(self):
        negative_limit, positive_limit = self._software_position_limits()
        return (
            self.actual_position < negative_limit or
            self.actual_position > positive_limit
        )

    def _software_limit_is_active(self):
        return (
            self.software_limit_warning or
            self._actual_position_exceeds_software_limits()
        )

    def _is_moving(self):
        return (
            abs(float(self.actual_velocity)) > 1e-9 or
            self.pp_active or
            self.homing_active
        )

    # ---------------------------------
    # CSP
    # ---------------------------------

    def process_csp(self):

        if self.sm.get_statusword() != 0x0027:
            return

        if self.halt_active:
            self._decelerate_to_stop()
            self._write_actual_feedback()
            self.target_reached = abs(self.actual_velocity) <= 1e-9
            return

        if not self.homing_referenced:
            self.target_reached = False
            self._decelerate_to_stop()
            self._write_actual_feedback()
            return

        target = self.od.read(0x607A)
        profile_vel = abs(float(self.od.read(0x6081)))
        positive_limit = abs(float(self.od.read(0x607F)))
        negative_limit = abs(float(self.od.read(0x2183, 0x0C)) * 1000.0)
        max_profile_vel = positive_limit
        if target < self.actual_position and negative_limit > 0:
            max_profile_vel = negative_limit
        max_vel = min(profile_vel, max_profile_vel) if max_profile_vel > 0 else profile_vel
        accel = self.od.read(0x6083)
        decel = self.od.read(0x6084)

        error = target - self.actual_position

        desired_velocity = self._position_rate_to_velocity(self.kp * error)
        desired_velocity = max(
            min(desired_velocity, max_vel),
            -max_vel,
        )

        delta_v = (desired_velocity - self.actual_velocity)

        if abs(desired_velocity) > abs(self.actual_velocity):
            limit = accel
        else:
            limit = decel

        max_delta_v = self._acceleration_to_velocity_delta(
            limit,
            self.cycle_time,
        )

        delta_v = max(min(delta_v, max_delta_v), -max_delta_v)

        self.actual_velocity += delta_v

        self.actual_position += (
            self._velocity_to_position_rate(self.actual_velocity)
            * self.cycle_time
        )

        self.od.write(0x6064, self.actual_position)

        self.od.write(0x606C, self.actual_velocity)

        self.update_target_reached()
