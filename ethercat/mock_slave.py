from device.cmmt.mock_pdo_adapter import MockPdoAdapter
from device.cmmt.rxpdo import RxPDO
from device.cmmt.txpdo import TxPDO


class MockSlave:
    def __init__(self, axis):
        self.axis = axis
        self.rxpdo = RxPDO()
        self.txpdo = TxPDO()
        self.pdo_adapter = MockPdoAdapter(
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
