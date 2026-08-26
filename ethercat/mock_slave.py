from device.virtual_device import VirtualOdBridge


class MockSlave:
    def __init__(self, virtual_device, device_profile):
        self.virtual_device = virtual_device
        self.device_profile = device_profile
        self.rxpdo = device_profile.create_rxpdo()
        self.txpdo = device_profile.create_txpdo()
        self.pdo_codec = device_profile.pdo_codec
        self.od_bridge = VirtualOdBridge(
            self.virtual_device.od,
            device_profile.pdo_configuration,
        )

    def process(self):
        rxpdo_payload = self.pdo_codec.encode_rxpdo(self.rxpdo)
        self.od_bridge.rxpdo_payload_to_od(rxpdo_payload)
        self.model_update()

    def model_update(self):
        self.virtual_device.model_update()
        txpdo_payload = self.od_bridge.od_to_txpdo_payload()
        self.pdo_codec.decode_txpdo(txpdo_payload, self.txpdo)

    def read_sdo(self, index, subindex, size):
        return self.od_bridge.read_sdo(index, subindex, size)

    def write_sdo(self, index, subindex, payload):
        self.od_bridge.write_sdo(index, subindex, payload)
        self.model_update()
