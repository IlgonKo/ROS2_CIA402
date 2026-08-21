from device.virtual_servo_drive import VirtualOdBridge


class MockSlave:
    def __init__(self, axis, pdo_configuration=None, device_profile=None):
        self.axis = axis
        self.device_profile = device_profile
        self.rxpdo = device_profile.create_rxpdo()
        self.txpdo = device_profile.create_txpdo()
        self.od_bridge = VirtualOdBridge(
            self.axis,
            self.rxpdo,
            self.txpdo,
        )

    def process(self):
        # RxPDO -> Axis
        self.od_bridge.rxpdo_to_axis()

        # Axis -> VirtualServo cycle
        self.axis.update()

        # Axis -> TxPDO
        self.od_bridge.axis_to_txpdo()

    def read_sdo(self, index, subindex, size):
        return self.od_bridge.read_sdo(index, subindex, size)

    def write_sdo(self, index, subindex, payload):
        self.od_bridge.write_sdo(index, subindex, payload)
