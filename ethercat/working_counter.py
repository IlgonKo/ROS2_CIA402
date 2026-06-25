class WorkingCounter:

    def __init__(self):

        self.expected = 0

    def add_slave(self):

        self.expected += 2

    def get_expected(self):

        return self.expected