class PdoMapper:
    def __init__(self, axis, rxpdo, txpdo):
        self.axis = axis
        self.rxpdo = rxpdo
        self.txpdo = txpdo

    def rxpdo_to_axis(self):
        self.axis.set_controlword(self.rxpdo.controlword)
        self.axis.set_mode(self.rxpdo.mode_of_operation)
        self.axis.set_target_position(self.rxpdo.target_position)
        self.axis.set_target_velocity(self.rxpdo.target_velocity)

    def axis_to_txpdo(self):
        self.txpdo.statusword = self.axis.get_statusword()
        self.txpdo.mode_of_operation_display = self.rxpdo.mode_of_operation
        self.txpdo.actual_position = self.axis.get_actual_position()
        self.txpdo.actual_velocity = self.axis.get_actual_velocity()
