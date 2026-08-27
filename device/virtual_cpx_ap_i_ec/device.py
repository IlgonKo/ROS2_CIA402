from device.virtual_cpx_ap_i_ec.module import VirtualApModule
from device.virtual_cpx_ap_i_ec.od_model import VirtualCpxOdModel


AP_ACCESS_INDEX = 0x27F0


class VirtualCpxApDevice:
    """Virtual CPX-AP-I-EC station driven only by OD state and Model_Update."""

    def __init__(
        self,
        device_profile,
        *,
        ap_gateway=None,
        isdu_gateway=None,
    ):
        self.device_profile = device_profile
        self.od = VirtualCpxOdModel(device_profile)
        self.modules = {
            int(module.slot): VirtualApModule(module)
            for module in device_profile.config.layout.modules
        }
        self.ap_gateway = ap_gateway
        self.isdu_gateway = isdu_gateway
        self.last_ap_request = None
        self.last_isdu_requests = {}

    def module(self, slot):
        try:
            return self.modules[int(slot)]
        except KeyError as exc:
            raise ValueError(f"Unknown Virtual CPX AP module slot: {slot}") from exc

    def set_digital_input(self, slot, channel, value):
        self.module(slot).set_digital_input(channel, value)

    def set_analog_input(self, slot, channel, value):
        self.module(slot).set_analog_input(channel, value)

    def set_io_link_input(self, slot, payload):
        self.module(slot).set_io_link_input(payload)

    def reset_inputs(self, slot=None):
        modules = (
            self.modules.values()
            if slot is None
            else (self.module(slot),)
        )
        for module in modules:
            module.reset_inputs()

    def input_snapshot(self):
        modules = []
        for module in self.modules.values():
            snapshot = module.input_snapshot()
            if snapshot["inputs"]:
                modules.append(snapshot)
        return {
            "modules": modules,
        }

    def model_update(self):
        self._dispatch_gateway_request()
        output_image = self._read_process_image(
            self.device_profile.pdo_configuration.rxpdo_objects()
        )
        for module in self.modules.values():
            module.consume_output_image(output_image)

        input_image = bytearray(
            self.device_profile.pdo_configuration.input_bytes
        )
        for module in self.modules.values():
            module.publish_input_image(input_image)
        self._write_process_image(
            self.device_profile.pdo_configuration.txpdo_objects(),
            input_image,
        )

    def _dispatch_gateway_request(self):
        key = self.od.last_write_key
        if key == (AP_ACCESS_INDEX, 1):
            self._dispatch_ap_request()
            return
        for slot, module in self.modules.items():
            if module.module.module_type != "iol":
                continue
            index = 0x2001 + slot * 0x10
            if key == (index, 1):
                self._dispatch_isdu_request(slot, index)
                return

    def _dispatch_ap_request(self):
        length = int(self.od.read(AP_ACCESS_INDEX, 6))
        request = {
            "direction": int(self.od.read(AP_ACCESS_INDEX, 1)),
            "ap_access_module": int(self.od.read(AP_ACCESS_INDEX, 2)),
            "module": max(0, int(self.od.read(AP_ACCESS_INDEX, 2)) - 1),
            "parameter_id": int(self.od.read(AP_ACCESS_INDEX, 3)),
            "instance": int(self.od.read(AP_ACCESS_INDEX, 4)),
            "length": length,
            "data": bytes(self.od.read(AP_ACCESS_INDEX, 7))[:length],
        }
        self.last_ap_request = request
        response = self._gateway_response(self.ap_gateway, request)
        self._apply_gateway_response(AP_ACCESS_INDEX, response)

    def _dispatch_isdu_request(self, slot, index):
        length = int(self.od.read(index, 6))
        request = {
            "direction": int(self.od.read(index, 1)),
            "module": int(slot),
            "port": int(self.od.read(index, 2)),
            "index": int(self.od.read(index, 3)),
            "subindex": int(self.od.read(index, 4)),
            "length": length,
            "data": bytes(self.od.read(index, 7))[:length],
        }
        self.last_isdu_requests[int(slot)] = request
        response = self._gateway_response(self.isdu_gateway, request)
        self._apply_gateway_response(index, response)

    @staticmethod
    def _gateway_response(gateway, request):
        if gateway is None:
            return {"status": 0, "data": b""}
        response = gateway(dict(request))
        return {} if response is None else dict(response)

    def _apply_gateway_response(self, index, response):
        status = int(response.get("status", 0))
        payload = bytes(response.get("data", b""))
        maximum = len(bytes(self.od.read(index, 7)))
        if len(payload) > maximum:
            raise ValueError(
                f"Gateway response for 0x{index:04X} exceeds {maximum} bytes."
            )
        self.od.write_internal(index, status, 5)
        self.od.write_internal(index, len(payload), 6)
        self.od.write_internal(
            index,
            payload + bytes(maximum - len(payload)),
            7,
        )

    def _read_process_image(self, objects):
        return b"".join(
            bytes(self.od.read(obj.index, obj.subindex))
            for obj in objects
        )

    def _write_process_image(self, objects, payload):
        payload = bytes(payload)
        offset = 0
        for obj in objects:
            end = offset + obj.byte_length
            self.od.write_internal(
                obj.index,
                payload[offset:end],
                obj.subindex,
            )
            offset = end
