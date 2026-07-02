class ObjectDictionary:

    def __init__(self):

        self.objects = {

            0x6040: 0,       # Controlword
            0x6041: 0x0040,  # Statusword
            (0x2145, 0x0C): 0x00000000,  # CMMT most serious error

            0x6060: 8,       # Mode of operation
            0x6061: 8,       # Mode Display
            0x6098: 35,      # Homing method
            (0x6099, 1): 100,  # Homing speed during search for switch
            (0x6099, 2): 50,   # Homing speed during search for zero
            0x609A: 100,     # Homing acceleration

            0x607A: 0.0,       # Target Position
            0x6064: 0.0,       # Actual Position
            (0x1C32, 1): 1,  # Synchronisation mode: sync with process data
            (0x1C32, 2): 8000000,  # Drive sync time (ns)
            (0x607D, 1): -1000000,  # Negative Software Position Limit
            (0x607D, 2): 1000000,   # Positive Software Position Limit

            0x60FF: 0.0,       # Target Velocity
            0x606C: 0.0,        # Actual Velocity
            (0x60A4, 1): 100000,  # Profile jerk

            0x6067: 20,      # Position Window
            0x6068: 20,      # Position Window Time(ms)

            0x607F: 100,     # max Velocity(mm/sec)
            0x6083 : 50,    # Profile Acceleration(mm/sec^2)
            0x6084 : 50     # Profile Deceleration(mm/sec^2)
        }

    def read(self, index, subindex=None):

        key = (index, subindex) if subindex is not None else index
        return self.objects[key]

    def write(self, index, value, subindex=None):

        key = (index, subindex) if subindex is not None else index
        self.objects[key] = value
