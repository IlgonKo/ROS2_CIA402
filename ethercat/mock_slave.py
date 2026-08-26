from device.virtual_servo_drive import VirtualOdBridge


class MockSlave:
    def __init__(self, virtual_device, device_profile):
        self.virtual_device = virtual_device
        self.device_profile = device_profile
        self.rxpdo = device_profile.create_rxpdo()
        self.txpdo = device_profile.create_txpdo()
        self.od_bridge = VirtualOdBridge(
            self.virtual_device.od,
            self.rxpdo,
            self.txpdo,
        )

    def process(self):
        self.virtual_device.apply_rxpdo(self.rxpdo)
        self.virtual_device.update()
        self.od_bridge.od_to_txpdo()

    def read_sdo(self, index, subindex, size):
        return self.od_bridge.read_sdo(index, subindex, size)

    def write_sdo(self, index, subindex, payload):
        definition, value = self.od_bridge.write_sdo(index, subindex, payload)
        self.virtual_device.on_object_write(
            definition,
            value,
            self.rxpdo,
            self.txpdo,
        )
        self.od_bridge.rxpdo_to_od()
        self.od_bridge.od_to_txpdo()
