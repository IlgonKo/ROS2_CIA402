import time

class DistributedClock:

    def __init__(self):

        self.start = time.time_ns()

    def get_time_ns(self):

        return (
            time.time_ns()
            - self.start
        )