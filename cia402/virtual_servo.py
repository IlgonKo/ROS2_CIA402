from interfaces.servo_interface import ServoInterface
from cia402.object_dictionary import ObjectDictionary
from cia402.state_machine import CiA402StateMachine


class VirtualCiA402Servo(ServoInterface): 
    def __init__(self, cycle_time=0.001):
        self.cycle_time = cycle_time

        self.od = ObjectDictionary()
        self.sm = CiA402StateMachine()

        self.actual_position = 0.0
        self.actual_velocity = 0.0
        
        self.kp = 5.0
        self.target_reached = False
        self.window_counter = 0
        self.previous_controlword = 0
        self.pp_active = False
        self.pp_target_position = self.actual_position

        #self.init_object_dictionary()

    # ---------------------------------
    # Servo Interface
    # ---------------------------------     
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
        self.od.write(0x6060,next_mode)

    def set_target_position(self, position):        
        current_target = self.od.read(0x607A)
        if position != current_target:
            self.target_reached = False
            self.window_counter = 0
        self.od.write(0x607A, position)

    def set_target_velocity(self,velocity):
        self.od.write(0x60FF,velocity)

    def set_motion_limits(self, max_velocity, acceleration, deceleration):
        self.od.write(0x607F, max_velocity)
        self.od.write(0x6083, acceleration)
        self.od.write(0x6084, deceleration)

    def get_motion_limits(self):
        return {
            "max_velocity": self.od.read(0x607F),
            "acceleration": self.od.read(0x6083),
            "deceleration": self.od.read(0x6084),
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

    # ---------------------------------
    # Main Cycle
    # ---------------------------------

    def process_cycle(self):
        controlword = self.od.read(0x6040)
        was_operation_enabled = self.sm.get_statusword() == 0x0027

        self.sm.process(controlword)
        is_operation_enabled = self.sm.get_statusword() == 0x0027
        if was_operation_enabled and not is_operation_enabled:
            self.stop_at_current_position()

        mode = self.od.read(0x6060)

        if mode == 1:
            self.process_pp()
        elif mode == 8:
            self.process_csp()
        elif mode == 9:
            self.process_csv()

        statusword = self.sm.get_statusword()

        if self.target_reached:
            statusword |= (1 << 10)

        self.od.write(0x6041, statusword)
        self.previous_controlword = controlword

    # ---------------------------------
    # PP
    # ---------------------------------

    def process_pp(self):
        if self.sm.get_statusword() != 0x0027:
            return

        controlword = self.od.read(0x6040)
        new_setpoint = (
            bool(controlword & (1 << 4)) and
            not bool(self.previous_controlword & (1 << 4))
        )

        if new_setpoint:
            self.pp_target_position = self.od.read(0x607A)
            self.pp_active = True
            self.target_reached = False
            self.window_counter = 0

        if not self.pp_active:
            self._decelerate_to_stop()
            self._write_actual_feedback()
            self.update_target_reached()
            return

        target = self.pp_target_position
        max_vel = abs(float(self.od.read(0x607F)))
        accel = abs(float(self.od.read(0x6083)))
        decel = abs(float(self.od.read(0x6084)))
        window = abs(float(self.od.read(0x6067)))
        dt = self.cycle_time

        error = target - self.actual_position
        distance = abs(error)
        if distance <= window and abs(self.actual_velocity) <= max(decel * dt, 1e-9):
            self.actual_position = target
            self.actual_velocity = 0.0
            self.pp_active = False
            self._write_actual_feedback()
            self.update_target_reached()
            return

        direction = 1.0 if error >= 0.0 else -1.0
        velocity_toward_target = self.actual_velocity * direction
        stopping_distance = (
            max(velocity_toward_target, 0.0) ** 2 / (2.0 * decel)
            if decel > 0.0
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
            velocity_limit * dt,
        )
        next_position = self.actual_position + self.actual_velocity * dt

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
            decel * self.cycle_time,
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

    # ---------------------------------
    # CSP
    # ---------------------------------

    def process_csp(self):

        if self.sm.get_statusword() != 0x0027:
            return

        target = self.od.read(0x607A)
        max_vel = self.od.read(0x607F)
        accel = self.od.read(0x6083)
        decel = self.od.read(0x6084)
        
        error = target - self.actual_position
        
        desired_velocity = self.kp * error
        desired_velocity = max(
            min(desired_velocity, max_vel),
            -max_vel,
        )

        delta_v = (desired_velocity - self.actual_velocity)

        if abs(desired_velocity) > abs(self.actual_velocity):
            limit = accel
        else:
            limit = decel

        max_delta_v = limit * self.cycle_time

        delta_v = max(min(delta_v, max_delta_v), -max_delta_v)

        self.actual_velocity += delta_v

        self.actual_position += (self.actual_velocity * self.cycle_time)
        
        self.od.write(0x6064, self.actual_position)

        self.od.write(0x606C, self.actual_velocity)

        self.update_target_reached()

    def process_csv(self):

        if self.sm.get_statusword() != 0x0027:

            return

        target_velocity = self.od.read(
            0x60FF
        )

        self.actual_velocity = \
            target_velocity

        self.actual_position += (
            self.actual_velocity *
            self.cycle_time
        )

        self.od.write(
            0x6064,
            int(
                self.actual_position
            )
        )

        self.od.write(
            0x606C,
            int(
                self.actual_velocity
            )
        )
