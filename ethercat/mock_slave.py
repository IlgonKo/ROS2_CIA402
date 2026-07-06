from device.cmmt.mock_pdo_adapter import MockPdoAdapter
from device.cmmt.rxpdo import RxPDO
from device.cmmt.txpdo import TxPDO
from ethercat.pysoem_master import AxisMotionLimits


class MockSlave:
    def __init__(self, axis):
        self.axis = axis
        self.rxpdo = RxPDO()
        self.txpdo = TxPDO()
        limits = self.axis.get_motion_limits()
        self.motion_limits = AxisMotionLimits(
            float(limits["max_velocity"]),
            float(limits["acceleration"]),
            float(limits["deceleration"]),
            float(limits.get("jerk", 0.0)),
        )
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
