class IoSdoAccess:
    def __init__(self, sdo, io_device_group):
        self._sdo = sdo
        self._io_device_group = io_device_group

    def __getattr__(self, name):
        operation = getattr(self._sdo, name)

        def io_operation(io_selector, *args, **kwargs):
            slave_index = self._io_device_group.slave_index(io_selector)
            return operation(slave_index, *args, **kwargs)

        return io_operation


class IoDeviceGroup:
    """Non-axis I/O device view over EtherCAT devices."""

    def __init__(self, ethercat_master):
        self.ethercat_master = ethercat_master
        self.sdo = IoSdoAccess(ethercat_master.sdo, self)

    @property
    def devices(self):
        return [
            self.device_info(slave_index, slave, io_index)
            for io_index, (slave_index, slave) in enumerate(self._io_slaves())
        ]

    def slave_index(self, io_selector):
        if isinstance(io_selector, int):
            return self._slave_index_by_io_index(io_selector)

        text = str(io_selector).strip()
        if text.isdigit():
            return self._slave_index_by_io_index(int(text))

        for device in self.devices:
            if str(device["id"]) == text:
                return device["slave_index"]

        raise ValueError(f"Unknown I/O device: {io_selector}")

    def selected_device(self, io_id=None, slave_index=None):
        devices = self.devices
        if io_id is None and slave_index is None:
            if len(devices) == 1:
                return devices[0]
            raise ValueError("I/O id is required when multiple I/O devices exist")

        for device in devices:
            if io_id is not None and str(device["id"]) == str(io_id):
                return device
            if slave_index is not None and int(device["slave_index"]) == int(slave_index):
                return device

        selector = io_id if io_id is not None else slave_index
        raise ValueError(f"Unknown I/O device: {selector}")

    def _slave_index_by_io_index(self, io_index):
        io_slaves = self._io_slaves()
        io_index = int(io_index)
        if io_index < 0 or io_index >= len(io_slaves):
            raise ValueError(f"Invalid I/O index: {io_index}")
        return io_slaves[io_index][0]

    def _io_slaves(self):
        return [
            (slave_index, slave)
            for slave_index, slave in enumerate(self.ethercat_master.slaves)
            if not self._is_motion_axis(slave)
        ]

    @staticmethod
    def _is_motion_axis(slave):
        profile = getattr(slave, "device_profile", None)
        return getattr(profile, "is_motion_axis", True)

    @staticmethod
    def device_info(slave_index, slave, io_index):
        profile = getattr(slave, "device_profile", None)
        config = getattr(profile, "config", None)
        return {
            "id": getattr(config, "io_id", f"io{io_index}"),
            "slave_index": slave_index,
            "profile": getattr(profile, "name", ""),
            "slave": slave,
        }
