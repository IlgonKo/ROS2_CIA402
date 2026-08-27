from types import SimpleNamespace
import unittest

from configuration.bus import DeviceRole
from configuration.models import (
    BackendType,
    BusDeviceConfig,
    CommandLogConfig,
    CpxApIEcDeviceConfig,
    CspCommandStepLogConfig,
    CspProfile,
    CycleConfig,
    CycleStatsLogConfig,
    DistributedClockConfig,
    EtherCATConfig,
    IoModuleConfig,
    LoggingConfig,
    MotionConfig,
    PositionFeedbackLagLogConfig,
    PreLoggingConfig,
    StatusLogConfig,
    TrajectoryLogConfig,
    VelocityAnomalyLogConfig,
    CmmtDeviceConfig,
    CspInterpolationMode,
)
from device.cmmt.non_pdo_configuration import CMMT_NON_PDO_CONFIGURATIONS
from device.cpx_ap_i_ec.profile import CPXApIEcDeviceProfile
from device.virtual_cpx_ap_i_ec import VirtualCpxApDevice
from ethercat.mock_master import MockMaster
from ethercat.mock_slave import MockSlave
from motion_server.api.encoder import io_device_snapshot
from motion_server.app.startup import (
    build_device_models,
    connect_bus,
    create_axis_runtime,
)
from motion_server.handlers.command.io_output_write import write_output_target
from motion_server.handlers.status.io_input_read import input_read_data


def cpx_profile(*modules):
    config = SimpleNamespace(
        logical_id="io0",
        modules=tuple(
            SimpleNamespace(slot=slot, module_type=module_type)
            for slot, module_type in modules
        ),
        io_link_ports=(),
    )
    return CPXApIEcDeviceProfile(device_config=config)


def virtual_cpx_master(profile, **device_options):
    device = VirtualCpxApDevice(profile, **device_options)
    endpoint = MockSlave(device, profile.pdo_configuration)
    master = MockMaster([endpoint], device_profiles=[profile])
    return master, device


def exchange(master):
    master.prepare_processdata()
    master.send_processdata()
    master.receive_processdata()


class VirtualCpxPdoConfigurationTest(unittest.TestCase):
    def test_selects_smallest_fixed_esi_process_image(self):
        profile = cpx_profile((1, "do:8"), (2, "di:8"))

        self.assertEqual(profile.config.output_bytes, 2)
        self.assertEqual(profile.config.input_bytes, 1)
        self.assertEqual(profile.pdo_configuration.output_bytes, 16)
        self.assertEqual(profile.pdo_configuration.input_bytes, 16)
        self.assertEqual(profile.pdo_configuration.rxpdo_info.index, 0x1710)
        self.assertEqual(profile.pdo_configuration.txpdo_info.index, 0x1B10)
        self.assertEqual(
            len(profile.pdo_configuration.rxpdo_objects()),
            1,
        )

    def test_selects_larger_block_when_layout_crosses_boundary(self):
        profile = cpx_profile(
            (1, "iol:4:in8:out8"),
            (2, "iol:4:in8:out8"),
        )

        self.assertEqual(profile.config.output_bytes, 17)
        self.assertEqual(profile.config.input_bytes, 24)
        self.assertEqual(profile.pdo_configuration.output_bytes, 32)
        self.assertEqual(profile.pdo_configuration.input_bytes, 32)
        self.assertEqual(profile.pdo_configuration.rxpdo_info.index, 0x1711)
        self.assertEqual(profile.pdo_configuration.txpdo_info.index, 0x1B11)


class VirtualCpxOdModelTest(unittest.TestCase):
    def test_builds_station_selected_mapping_and_only_configured_module_od(self):
        profile = cpx_profile((1, "do:8"), (2, "di:8"))
        device = VirtualCpxApDevice(profile)
        od = device.od

        self.assertEqual(od.read(0x1018, 1), profile.esi_catalog.vendor_id)
        self.assertEqual(od.read(0x1018, 2), profile.esi_catalog.product_code)
        self.assertEqual(od.read(0x1000), 0x04561389)
        self.assertEqual(od.read(0x1008), "CPX-AP-I-EC-M12")
        self.assertEqual(od.read(0x1001), 0)
        self.assertEqual(od.read(0x1C12), 1)
        self.assertEqual(od.read(0x1C12, 1), 0x1710)
        self.assertEqual(od.read(0x1C13, 1), 0x1B10)
        self.assertEqual(od.read(0x1710), 1)
        self.assertEqual(od.read(0x1710, 1), 0x6F000180)
        self.assertTrue(od.has_entry(0x6F00, 1))
        self.assertTrue(od.has_entry(0x7F00, 1))
        self.assertFalse(od.has_entry(0x6F00, 2))
        self.assertFalse(od.has_entry(0x1711, 0))
        self.assertFalse(od.has_entry(0x1B11, 0))
        self.assertTrue(od.has_entry(0x7010, 1))
        self.assertTrue(od.has_entry(0x6020, 1))
        self.assertFalse(od.has_entry(0x6030, 1))
        self.assertEqual(od.read(0xF050), 3)
        self.assertEqual(od.read(0xF030), 3)

    def test_preop_validates_module_list_and_process_image_readback(self):
        profile = cpx_profile((1, "do:8"), (2, "di:8"))
        master, _device = virtual_cpx_master(profile)

        master.connect(target_state="preop")

        self.assertEqual(
            master.read_assigned_pdo_mapping_entries(0, 0x1C12),
            profile.pdo_configuration.rxpdo_mapping_entries(),
        )
        self.assertEqual(master.slaves[0].rxpdo.mapping_size(), 16)
        self.assertEqual(master.slaves[0].txpdo.mapping_size(), 16)


class VirtualCpxProcessDataTest(unittest.TestCase):
    def test_output_state_and_independent_input_state_have_no_loopback(self):
        profile = cpx_profile(
            (1, "do:8"),
            (2, "di:8"),
            (3, "aio:4:4"),
        )
        master, device = virtual_cpx_master(profile)
        master.connect(target_state="preop")
        rxpdo = master.slaves[0].rxpdo
        txpdo = master.slaves[0].txpdo

        rxpdo.set_module_digital_output(1, 0, True)
        rxpdo.set_module_analog_output(3, 0, -1234)
        exchange(master)

        self.assertTrue(device.module(1).digital_outputs[0])
        self.assertEqual(device.module(3).analog_outputs[0], -1234)
        self.assertFalse(txpdo.get_module_digital_input(2, 0))
        self.assertEqual(txpdo.get_module_analog_input(3, 0), 0)

        device.set_digital_input(2, 1, True)
        device.set_analog_input(3, 1, 2345)
        exchange(master)

        self.assertTrue(txpdo.get_module_digital_input(2, 1))
        self.assertEqual(txpdo.get_module_analog_input(3, 1), 2345)
        self.assertFalse(txpdo.get_module_digital_input(2, 0))

    def test_io_link_buffers_are_sized_raw_and_not_looped_back(self):
        profile = cpx_profile((1, "iol:4:in8:out8"))
        master, device = virtual_cpx_master(profile)
        master.connect(target_state="preop")
        output = bytes(range(8))
        input_payload = bytes(range(12, 24))

        master.slaves[0].rxpdo.set_io_link_output(1, output)
        exchange(master)

        self.assertEqual(bytes(device.module(1).io_link_output), output)
        self.assertEqual(master.slaves[0].txpdo.get_io_link_input(1), bytes(12))

        device.set_io_link_input(1, input_payload)
        exchange(master)

        self.assertEqual(
            master.slaves[0].txpdo.get_io_link_input(1),
            input_payload,
        )

    def test_out_of_range_and_wrong_buffer_size_are_rejected(self):
        profile = cpx_profile(
            (1, "aio:4:4"),
            (2, "iol:4:in8:out8"),
        )
        master, device = virtual_cpx_master(profile)

        with self.assertRaises(ValueError):
            master.slaves[0].rxpdo.set_module_analog_output(1, 0, 40000)
        with self.assertRaises(ValueError):
            device.set_analog_input(1, 0, -40000)
        with self.assertRaises(ValueError):
            master.slaves[0].rxpdo.set_io_link_output(2, b"\x01")
        with self.assertRaises(ValueError):
            device.set_io_link_input(2, b"\x01")
        with self.assertRaises(ValueError):
            device.set_analog_input(1, -1, 0)
        with self.assertRaises(ValueError):
            device.set_analog_input(1, 4, 0)
        with self.assertRaises(TypeError):
            device.set_analog_input(1, 0, 1.5)
        with self.assertRaises(TypeError):
            master.slaves[0].rxpdo.set_module_digital_output(1, 0, 1)


class VirtualCpxGatewayTest(unittest.TestCase):
    def test_ap_gateway_dispatches_request_and_returns_response(self):
        requests = []

        def gateway(request):
            requests.append(request)
            return {"status": 0, "data": b"\x11\x22"}

        profile = cpx_profile((1, "do:8"))
        master, device = virtual_cpx_master(profile, ap_gateway=gateway)
        master.connect(target_state="preop")

        master.sdo.write_uint16(0, 0x27F0, 2, 2)
        master.sdo.write_uint32(0, 0x27F0, 3, 123)
        master.sdo.write_uint16(0, 0x27F0, 4, 4)
        master.sdo.write_uint8(0, 0x27F0, 1, 0)

        self.assertEqual(requests[-1]["module"], 1)
        self.assertEqual(requests[-1]["parameter_id"], 123)
        self.assertEqual(device.last_ap_request["instance"], 4)
        self.assertEqual(master.sdo.read_uint16(0, 0x27F0, 5), 0)
        self.assertEqual(master.sdo.read_uint16(0, 0x27F0, 6), 2)
        self.assertEqual(master.read_sdo(0, 0x27F0, 7, 512)[:2], b"\x11\x22")

    def test_isdu_gateway_dispatches_per_module_without_parameter_storage(self):
        requests = []

        def gateway(request):
            requests.append(request)
            return {"status": 0, "data": b"\x33"}

        profile = cpx_profile((1, "iol:4:in8:out8"))
        master, device = virtual_cpx_master(profile, isdu_gateway=gateway)
        master.connect(target_state="preop")
        index = 0x2011

        master.sdo.write_uint8(0, index, 2, 3)
        master.sdo.write_uint16(0, index, 3, 0x20)
        master.sdo.write_uint8(0, index, 4, 1)
        master.sdo.write_uint8(0, index, 1, 0)

        self.assertEqual(requests[-1]["module"], 1)
        self.assertEqual(requests[-1]["port"], 3)
        self.assertEqual(requests[-1]["index"], 0x20)
        self.assertEqual(device.last_isdu_requests[1]["subindex"], 1)
        self.assertEqual(master.sdo.read_uint16(0, index, 5), 0)
        self.assertEqual(master.sdo.read_uint8(0, index, 6), 1)


class VirtualCpxRuntimeIntegrationTest(unittest.TestCase):
    @staticmethod
    def logging_config():
        return LoggingConfig(
            CommandLogConfig(False),
            StatusLogConfig(False, 1.0),
            CycleStatsLogConfig(False, 1.0),
            TrajectoryLogConfig(False, False),
            VelocityAnomalyLogConfig(False, 0.0, 0.0, 1.0),
            PositionFeedbackLagLogConfig(False, 1.0),
            CspCommandStepLogConfig(False, 0.0, 0.0),
            PreLoggingConfig(False, 0),
        )

    def runtime(self):
        axis = BusDeviceConfig(
            0,
            DeviceRole.AXIS,
            "cmmt_as",
            None,
            CmmtDeviceConfig(
                "cmmt_as",
                0,
                "motion_server_default",
                CMMT_NON_PDO_CONFIGURATIONS["linear_mm"],
            ),
        )
        io = BusDeviceConfig(
            1,
            DeviceRole.IO,
            "cpx_ap_i_ec",
            "io0",
            CpxApIEcDeviceConfig(
                "cpx_ap_i_ec",
                "io0",
                (
                    IoModuleConfig(1, "do:8"),
                    IoModuleConfig(2, "di:8"),
                ),
                (),
            ),
        )
        ethercat = EtherCATConfig(
            BackendType.MOCK,
            "",
            None,
            CycleConfig(0.01, 0.0),
            DistributedClockConfig(
                False, 0, False, False, 0, 0.0, 0.0, 0.0
            ),
        )
        motion = MotionConfig(
            "pp",
            CspProfile.QUINTIC,
            100000.0,
            CspInterpolationMode.CSP,
            False,
        )
        devices = (axis, io)
        profiles = build_device_models(devices)
        runtime = create_axis_runtime(
            ethercat,
            motion,
            self.logging_config(),
            devices,
            device_profiles=profiles,
        )
        connect_bus(runtime)
        return runtime

    def test_mixed_axis_io_runtime_uses_existing_api_contract(self):
        runtime = self.runtime()

        self.assertEqual(len(runtime.slaves), 1)
        self.assertEqual(len(runtime.ethercat_devices), 2)
        self.assertEqual(len(runtime.device_manager.io.devices), 1)

        write_output_target(
            {
                "io": "io0",
                "slot": 1,
                "kind": "digital",
                "channel": 0,
                "value": True,
            },
            runtime,
        )
        runtime.ethercat_master.prepare_processdata()
        runtime.send_processdata()
        runtime.receive_processdata()
        virtual_device = (
            runtime.ethercat_master._slave_endpoints[1].virtual_device
        )
        self.assertTrue(virtual_device.module(1).digital_outputs[0])

        virtual_device.set_digital_input(2, 3, True)
        runtime.ethercat_master.prepare_processdata()
        runtime.send_processdata()
        runtime.receive_processdata()
        response = input_read_data({"io": "io0", "raw": True}, runtime)

        self.assertTrue(response["modules"][1]["inputs"]["digital"][3])
        self.assertEqual(response["output_bytes"], 16)
        self.assertEqual(response["input_bytes"], 16)
        self.assertEqual(
            runtime.sdo.io.read_uint8("io0", 0x1001, 0),
            0,
        )
        snapshot = io_device_snapshot(runtime.device_manager.io.devices[0])
        self.assertTrue(snapshot["digital_outputs"][0])


if __name__ == "__main__":
    unittest.main()
