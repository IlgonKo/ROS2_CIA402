from device.virtual_device import VirtualOdBridge


class MockSlave:
    def __init__(self, virtual_device, pdo_configuration):
        self.virtual_device = virtual_device
        self.od_bridge = VirtualOdBridge(
            self.virtual_device.od,
            pdo_configuration,
        )

    def exchange_processdata(self, output_payload):
        self.od_bridge.rxpdo_payload_to_od(output_payload)
        self.virtual_device.model_update()
        return self.od_bridge.od_to_txpdo_payload()

    def model_update(self):
        self.virtual_device.model_update()

    def read_sdo(self, index, subindex, size):
        return self.od_bridge.read_sdo(index, subindex, size)

    def write_sdo(self, index, subindex, payload):
        self.od_bridge.write_sdo(index, subindex, payload)
        self.model_update()

    def read_identity(self):
        catalog = self.virtual_device.device_profile.esi_catalog
        if catalog is None:
            return {}
        return {
            "product_code": int(catalog.product_code),
            "revision": int(catalog.revision),
        }
