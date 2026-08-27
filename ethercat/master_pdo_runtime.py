class MasterPdoRuntime:
    """Master-owned PDO objects, codec, and raw cycle snapshots for one slave."""

    def __init__(self, device_profile):
        self.device_profile = device_profile
        self.rxpdo = device_profile.create_rxpdo()
        self.txpdo = device_profile.create_txpdo()
        self.pdo_codec = device_profile.pdo_codec
        self.prepared_output = None
        self.transmitted_output = None
        self.received_input = None

    def encode_output_candidate(self):
        payload = self.pdo_codec.encode_rxpdo(self.rxpdo)
        return None if payload is None else bytes(payload)

    def commit_prepared_output(self, payload):
        self.prepared_output = payload

    def transmitted_output_candidate(self):
        payload = self.prepared_output
        return None if payload is None else bytes(payload)

    def commit_transmitted_output(self, payload):
        self.transmitted_output = payload
        self.prepared_output = None

    def validate_input_payload(self, payload):
        payload = bytes(payload)
        mapping_size = getattr(self.txpdo, "mapping_size", None)
        if callable(mapping_size):
            expected_size = int(mapping_size())
            if len(payload) < expected_size:
                raise ValueError(
                    "TxPDO payload is too small. "
                    f"Expected at least {expected_size} bytes, "
                    f"got {len(payload)} bytes."
                )
        return payload

    def decode_input(self, payload):
        self.pdo_codec.decode_txpdo(payload, self.txpdo)
        self.received_input = payload

    def reset_processdata(self):
        self.prepared_output = None
        self.transmitted_output = None
        self.received_input = None
