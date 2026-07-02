from ethercat.rxpdo import RxPDO
from ethercat.txpdo import TxPDO
from ethercat.pdo_mapper import PdoMapper
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
        self.mapper = PdoMapper(
            self.axis,
            self.rxpdo,
            self.txpdo,
        )

    def process(self):
        # RxPDO -> Axis
        self.mapper.rxpdo_to_axis()

        # Axis -> VirtualServo cycle
        self.axis.update()

        # Axis -> TxPDO
        self.mapper.axis_to_txpdo()
