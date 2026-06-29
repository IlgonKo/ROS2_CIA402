from abc import ABC
from abc import abstractmethod

class ServoInterface(ABC):    
    @abstractmethod
    def set_controlword(self, controlword):
        pass

    @abstractmethod
    def get_statusword(self):
        pass

    @abstractmethod
    def update(self):
        pass

    @abstractmethod
    def set_mode(self, mode):
        pass

    @abstractmethod
    def set_target_position(self, pos):
        pass

    @abstractmethod
    def set_target_velocity(self, vel):
        pass

    @abstractmethod
    def get_target_position(self):
        pass

    @abstractmethod
    def get_position(self):
        pass

    @abstractmethod
    def get_velocity(self):
        pass

    @abstractmethod
    def is_target_reached(self):
        pass

    @abstractmethod
    def set_motion_limits(self, max_velocity, acceleration, deceleration):
        pass

    @abstractmethod
    def get_motion_limits(self):
        pass

    @abstractmethod
    def set_software_position_limits(self, negative_limit, positive_limit):
        pass

    @abstractmethod
    def get_software_position_limits(self):
        pass

    @abstractmethod
    def set_position_loop_gain(self, kp):
        pass

    @abstractmethod
    def get_position_loop_gain(self):
        pass
