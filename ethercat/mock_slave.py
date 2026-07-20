from device.cmmt.rxpdo import RxPDO
from device.cmmt.txpdo import TxPDO
from device.virtual_servo_drive import VirtualPdoAdapter


class MockSlave:
    def __init__(self, axis):
        self.axis = axis
        self.rxpdo = RxPDO()
        self.txpdo = TxPDO()
        self.pdo_adapter = VirtualPdoAdapter(
            self.axis,
            self.rxpdo,
            self.txpdo,
        )

    def process(self):
        # RxPDO -> Axis
        self.pdo_adapter.rxpdo_to_axis()

        # Axis -> VirtualServo cycle
        self.axis.update()

        # Axis -> TxPDO
        self.pdo_adapter.axis_to_txpdo()
