from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

from configuration.models import IoLinkPortConfig

from device.cpx_ap_i_ec.ap_module_idents import (
    CONFIGURED_MODULE_LIST_INDEX,
    write_configured_module_idents,
)
from device.cpx_ap_i_ec.profile import CPXApIEcDeviceProfile
from device.virtual_cpx_ap_i_ec import VirtualCpxApDevice
from ethercat.mock_master import MockMaster
from ethercat.mock_slave import MockSlave


# Independent ESI Variant 32 fixture: 30 data bytes + 2 padding bytes per port.
VARIANT32_OUTPUT = [
    0x700101F0, 0x00000010,
    0x700102F0, 0x00000010,
    0x700103F0, 0x00000010,
    0x700104F0, 0x00000010,
]
VARIANT32_INPUT = [
    0x600101F0, 0x00000010,
    0x600102F0, 0x00000010,
    0x600103F0, 0x00000010,
    0x600104F0, 0x00000010,
    0x60010508, 0x60010608, 0x60010708, 0x60010808,
]
FIXED_OUTPUT128 = [
    0x6F000180, 0x6F000280, 0x6F000380, 0x6F000480,
    0x6F000580, 0x6F000680, 0x6F000780, 0x6F000880,
]
FIXED_INPUT256 = [
    0x7F000180, 0x7F000280, 0x7F000380, 0x7F000480,
    0x7F000580, 0x7F000680, 0x7F000780, 0x7F000880,
    0x7F000980, 0x7F000A80, 0x7F000B80, 0x7F000C80,
    0x7F000D80, 0x7F000E80, 0x7F000F80, 0x7F001080,
]


def profile_for(modules=((1, "iol:4:in128:out128"),), ports=()):
    return CPXApIEcDeviceProfile(device_config=SimpleNamespace(
        logical_id="io0",
        modules=tuple(
            SimpleNamespace(slot=slot, module_type=kind) for slot, kind in modules
        ),
        io_link_ports=tuple(
            IoLinkPortConfig(selector=selector, device_name=name)
            for selector, name in ports
        ),
    ))


class CpxProcessImageTest(unittest.TestCase):
    def test_configured_module_ident_entries_are_written_before_count(self):
        sdo = Mock()
        master = SimpleNamespace(sdo=sdo)

        write_configured_module_idents(master, 1, [0x2084, 0x200A, 0x2014])

        self.assertEqual(
            sdo.method_calls,
            [
                call.write_uint32(
                    1, CONFIGURED_MODULE_LIST_INDEX, 1, 0x2084,
                ),
                call.write_uint32(
                    1, CONFIGURED_MODULE_LIST_INDEX, 2, 0x200A,
                ),
                call.write_uint32(
                    1, CONFIGURED_MODULE_LIST_INDEX, 3, 0x2014,
                ),
                call.write_uint8(
                    1, CONFIGURED_MODULE_LIST_INDEX, 0, 3,
                ),
            ],
        )

    def test_variant32_layout_has_no_extra_station_byte(self):
        profile = profile_for()
        self.assertEqual(profile.config.layout.station_output_bytes, 0)
        self.assertEqual(profile.config.output_bytes, 128)
        self.assertEqual(profile.config.input_bytes, 132)
        self.assertEqual(profile.pdo_configuration.output_bytes, 128)
        self.assertEqual(profile.pdo_configuration.input_bytes, 256)

    def test_iodd_inference_matches_explicit_variant32(self):
        inferred = profile_for(
            modules=((1, "iol:4"),),
            ports=(("0", "Balluff_BCM_R16E_004_CI01"),),
        )
        self.assertEqual(inferred.config.io_link_devices[0].device.process_data_size, (32, 3))
        self.assertEqual(inferred.config.output_bytes, 128)
        self.assertEqual(inferred.config.input_bytes, 132)
        self.assertEqual(
            inferred.pdo_configuration.validate_actual_process_image(
                1, VARIANT32_OUTPUT, VARIANT32_INPUT,
            ),
            (128, 132),
        )

    def test_accepts_independent_modular_mapping(self):
        self.assertEqual(
            profile_for().pdo_configuration.validate_actual_process_image(
                1, VARIANT32_OUTPUT, VARIANT32_INPUT,
            ),
            (128, 132),
        )

    def test_accepts_independent_fixed_mapping(self):
        self.assertEqual(
            profile_for().pdo_configuration.validate_actual_process_image(
                1, FIXED_OUTPUT128, FIXED_INPUT256,
            ),
            (128, 256),
        )

    def test_rejects_wrong_output_size_order_and_objects(self):
        wrong_object = list(VARIANT32_OUTPUT)
        wrong_object[0] = 0x700201F0
        reordered = list(VARIANT32_OUTPUT)
        reordered[0], reordered[2] = reordered[2], reordered[0]
        for entries in (
            VARIANT32_OUTPUT[:-1],
            VARIANT32_OUTPUT + [0x08],
            FIXED_OUTPUT128 + [0x6F000980],
            FIXED_OUTPUT128 * 2,
            wrong_object,
            reordered,
        ):
            with self.subTest(entries=entries), self.assertRaisesRegex(
                RuntimeError, "RxPDO/output mapping mismatch",
            ):
                profile_for().pdo_configuration.validate_actual_process_image(
                    1, entries, VARIANT32_INPUT,
                )

    def test_rejects_input_truncation_extra_diagnostic_and_wrong_slot(self):
        wrong_slot = list(VARIANT32_INPUT)
        wrong_slot[-1] = 0x60020808
        for entries in (
            VARIANT32_INPUT[:-1],
            VARIANT32_INPUT + [0x61020120],
            wrong_slot,
        ):
            with self.subTest(entries=entries), self.assertRaisesRegex(
                RuntimeError, "TxPDO/input mapping mismatch",
            ):
                profile_for().pdo_configuration.validate_actual_process_image(
                    1, VARIANT32_OUTPUT, entries,
                )

    def test_slot_offsets_and_empty_direction(self):
        profile = profile_for(modules=((1, "di:8"), (3, "di:8")))
        inputs = [
            0x60010101, 0x60010201, 0x60010301, 0x60010401,
            0x60010501, 0x60010601, 0x60010701, 0x60010801,
            0x60030101, 0x60030201, 0x60030301, 0x60030401,
            0x60030501, 0x60030601, 0x60030701, 0x60030801,
        ]
        self.assertEqual(
            profile.pdo_configuration.validate_actual_process_image(
                1, [], inputs,
            ),
            (0, 2),
        )
        inputs[-1] = 0x60020801
        with self.assertRaisesRegex(RuntimeError, "TxPDO/input mapping mismatch"):
            profile.pdo_configuration.validate_actual_process_image(
                1, [], inputs,
            )

    def test_prepare_resizes_to_verified_device_mapping_and_codec_preserves_tail(self):
        profile = profile_for()
        rxpdo, txpdo = profile.create_rxpdo(), profile.create_txpdo()
        master = SimpleNamespace(
            slaves=[SimpleNamespace(rxpdo=rxpdo, txpdo=txpdo)],
            read_assigned_pdo_mapping_entries=Mock(
                side_effect=[VARIANT32_OUTPUT, VARIANT32_INPUT],
            ),
        )
        with patch("device.cpx_ap_i_ec.profile.configure_io_link_variants"), patch(
            "device.cpx_ap_i_ec.profile.configure_ap_module_idents",
        ):
            profile.prepare_process_image(master, 0)
        self.assertEqual(rxpdo.mapping_size(), 128)
        self.assertEqual(txpdo.mapping_size(), 132)
        payload = bytes(range(128))
        rxpdo.set_io_link_output(1, payload)
        self.assertEqual(profile.pdo_codec.encode_rxpdo(rxpdo), payload)
        incoming = payload + b"\x11\x22\x33\x44"
        profile.pdo_codec.decode_txpdo(incoming, txpdo)
        self.assertEqual(txpdo.get_io_link_input(1), incoming)

    def test_failed_validation_does_not_resize_buffers(self):
        profile = profile_for()
        rxpdo, txpdo = profile.create_rxpdo(), profile.create_txpdo()
        master = SimpleNamespace(
            slaves=[SimpleNamespace(rxpdo=rxpdo, txpdo=txpdo)],
            read_assigned_pdo_mapping_entries=Mock(
                side_effect=[VARIANT32_OUTPUT, VARIANT32_INPUT[:-1]],
            ),
        )
        with patch("device.cpx_ap_i_ec.profile.configure_io_link_variants"), patch(
            "device.cpx_ap_i_ec.profile.configure_ap_module_idents",
        ), self.assertRaisesRegex(RuntimeError, "TxPDO/input mapping mismatch"):
            profile.prepare_process_image(master, 0)
        self.assertEqual(rxpdo.mapping_size(), 128)
        self.assertEqual(txpdo.mapping_size(), 256)

    def test_variant32_virtual_transport_still_uses_esi_fixed_blocks(self):
        profile = profile_for()
        device = VirtualCpxApDevice(profile)
        master = MockMaster(
            [MockSlave(device, profile.pdo_configuration)], device_profiles=[profile],
        )
        try:
            master.connect(target_state="preop")
            self.assertEqual(master.read_assigned_pdo_mapping_entries(0, 0x1C12), FIXED_OUTPUT128)
            self.assertEqual(master.read_assigned_pdo_mapping_entries(0, 0x1C13), FIXED_INPUT256)
            payload = bytes(range(128))
            master.slaves[0].rxpdo.set_io_link_output(1, payload)
            device.set_io_link_input(1, payload + b"\x11\x22\x33\x44")
            master.prepare_processdata()
            master.send_processdata()
            master.receive_processdata()
            self.assertEqual(device.module(1).io_link_output, payload)
            self.assertEqual(master.slaves[0].txpdo.get_io_link_input(1), payload + b"\x11\x22\x33\x44")
        finally:
            master.close()


if __name__ == "__main__":
    unittest.main()
