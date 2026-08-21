from device.virtual_servo_drive import VirtualOdBridge


class MockSlave:
    def __init__(self, servo, device_profile):
        self.servo = servo
        self.device_profile = device_profile
        self.rxpdo = device_profile.create_rxpdo()
        self.txpdo = device_profile.create_txpdo()
        self.od_bridge = VirtualOdBridge(
            self.servo.od,
            self.rxpdo,
            self.txpdo,
        )

    def process(self):
        self.servo.apply_rxpdo(self.rxpdo)
        self.servo.update()
        self.od_bridge.od_to_txpdo()

    def read_sdo(self, index, subindex, size):
        return self.od_bridge.read_sdo(index, subindex, size)

    def write_sdo(self, index, subindex, payload):
        self.od_bridge.write_sdo(index, subindex, payload)
