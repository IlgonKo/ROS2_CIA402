class CspTrajectoryGenerator:
    def __init__(self, initial_position=0.0):
        self.command_position = float(initial_position)
        self.target_position = float(initial_position)
        self.command_velocity = 0.0

    def set_target_position(self, target_position):
        self.target_position = float(target_position)

    def update(self, cycle_time, max_velocity, acceleration, deceleration):
        error = self.target_position - self.command_position

        if abs(error) <= 1e-9 and abs(self.command_velocity) <= 1e-9:
            self.command_position = self.target_position
            self.command_velocity = 0.0
            return self.command_position

        direction = 1.0 if error >= 0.0 else -1.0
        distance_remaining = abs(error)
        braking_distance = (
            self.command_velocity * self.command_velocity
        ) / (2.0 * max(deceleration, 1e-9))

        if distance_remaining <= braking_distance:
            desired_velocity = 0.0
        else:
            desired_velocity = direction * max_velocity

        delta_v = desired_velocity - self.command_velocity

        if abs(desired_velocity) > abs(self.command_velocity):
            velocity_limit = acceleration
        else:
            velocity_limit = deceleration

        max_delta_v = velocity_limit * cycle_time
        delta_v = max(min(delta_v, max_delta_v), -max_delta_v)

        self.command_velocity += delta_v
        next_position = self.command_position + self.command_velocity * cycle_time

        if self._crossed_target(next_position):
            self.command_position = self.target_position
            self.command_velocity = 0.0
        else:
            self.command_position = next_position

        return self.command_position

    def _crossed_target(self, next_position):
        if self.target_position >= self.command_position:
            return next_position >= self.target_position

        return next_position <= self.target_position
