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
        self.od.write(0x6060,int(mode))

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

        self.sm.process(controlword)

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

    # ---------------------------------
    # CSP
    # ---------------------------------

    def process_pp(self):
        self.process_csp()

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
