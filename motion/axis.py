from interfaces.servo_interface import ServoInterface

class Axis:

    def __init__(self, name: str, servo: ServoInterface):
        self.name = name
        self.servo = servo

    def set_controlword(self, controlword):
        self.servo.set_controlword(controlword)

    def set_mode(self, mode):
        self.servo.set_mode(mode)

    def update(self):
        self.servo.update()

    def set_target_position(self,position):
        self.servo.set_target_position(position)

    def set_target_velocity(self,velocity):
        self.servo.set_target_velocity(velocity)

    def set_motion_limits(self, max_velocity, acceleration, deceleration):
        self.servo.set_motion_limits(
            max_velocity,
            acceleration,
            deceleration,
        )

    def get_motion_limits(self):
        return self.servo.get_motion_limits()

    def set_position_loop_gain(self, kp):
        self.servo.set_position_loop_gain(kp)

    def get_position_loop_gain(self):
        return self.servo.get_position_loop_gain()

    def get_actual_position(self):
        return self.servo.get_position()

    def get_actual_velocity(self):
        return self.servo.get_velocity()
    
    def get_target_position(self):
        return self.servo.get_target_position()

    def get_statusword(self):
        return self.servo.get_statusword()

    def is_target_reached(self):
        return self.servo.is_target_reached()
