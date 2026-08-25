from device.cmmt.error_catalog import load_cmmt_error_catalog
from device.cmmt.esi_catalog import cmmt_catalog_by_profile_name
from device.cmmt.pdo_codec import CiA402PdoCodec
from device.cmmt.pdo_configuration import get_pdo_configuration, pdo_od_role
from device.cmmt.required_non_pdo_od import (
    required_non_pdo_od,
    required_non_pdo_od_roles as cmmt_required_non_pdo_od_roles,
)
from device.cmmt.rxpdo import RxPDO
from device.cmmt.txpdo import TxPDO
from device.capabilities import DeviceCapability


class CMMTDeviceProfile:
    name = "cmmt"
    variant = None
    capabilities = frozenset({DeviceCapability.AXIS_RESTART})

    PROFILE_POSITION_MODE = 1
    PROFILE_VELOCITY_MODE = 3
    JOG_MODE = -3
    HOMING_MODE = 6
    CSP_MODE = 8

    PP_BASE_CONTROLWORD = 0x000F
    PP_NEW_SETPOINT_CONTROLWORD = 0x003F
    PP_SETPOINT_ACK_BIT = 12
    PP_SETPOINT_ACK_MASK = 1 << PP_SETPOINT_ACK_BIT
    PP_HANDSHAKE_MAX_CYCLES = 100

    HOMING_START_BIT = 1 << 4
    HOMING_REFERENCED_MASK = 1 << 15
    HOMING_ERROR_MASK = 1 << 13

    STATUSWORD_INDEX = pdo_od_role("statusword").index
    ERROR_CODE_INDEX = required_non_pdo_od("error_code").index
    ERROR_CODE_SUBINDEX = required_non_pdo_od("error_code").subindex
    MODE_DISPLAY_INDEX = pdo_od_role("mode_of_operation_display").index
    MODE_OF_OPERATION_INDEX = pdo_od_role("mode_of_operation").index
    CSP_INTERPOLATION_MODE_INDEX = required_non_pdo_od("csp_interpolation_mode").index
    CSP_INTERPOLATION_MODE_SUBINDEX = required_non_pdo_od("csp_interpolation_mode").subindex
    PP_JERK_INDEX = required_non_pdo_od("pp_jerk").index
    PP_JERK_SUBINDEX = required_non_pdo_od("pp_jerk").subindex
    USER_UNIT_INDEX = required_non_pdo_od("user_position_unit").index
    USER_UNIT_POSITION_SUBINDEX = required_non_pdo_od("user_position_unit").subindex
    CONVERTING_UNIT_INDEX = required_non_pdo_od("converting_unit_position").index
    CONVERTING_UNIT_POSITION_SUBINDEX = required_non_pdo_od("converting_unit_position").subindex
    CONVERTING_UNIT_VELOCITY_SUBINDEX = required_non_pdo_od("converting_unit_velocity").subindex
    CONVERTING_UNIT_ACCELERATION_SUBINDEX = required_non_pdo_od(
        "converting_unit_acceleration"
    ).subindex
    CONVERTING_UNIT_JERK_SUBINDEX = required_non_pdo_od("converting_unit_jerk").subindex
    DEFAULT_CONVERTING_UNIT_EXPONENTS = [6, 3, 3, 3]
    SOFTWARE_POSITION_LIMIT_INDEX = required_non_pdo_od("software_position_limit_negative").index
    MAX_PROFILE_VELOCITY_INDEX = required_non_pdo_od("max_profile_velocity").index
    NEGATIVE_VELOCITY_LIMIT_INDEX = required_non_pdo_od("negative_velocity_limit").index
    NEGATIVE_VELOCITY_LIMIT_SUBINDEX = required_non_pdo_od(
        "negative_velocity_limit"
    ).subindex
    PROFILE_VELOCITY_INDEX = pdo_od_role("profile_velocity").index
    PROFILE_ACCELERATION_INDEX = required_non_pdo_od("profile_acceleration").index
    PROFILE_DECELERATION_INDEX = required_non_pdo_od("profile_deceleration").index
    MAX_ACCELERATION_INDEX = required_non_pdo_od("max_acceleration").index
    MAX_DECELERATION_INDEX = required_non_pdo_od("max_deceleration").index
    SYNC_PARAMETER_INDEX = required_non_pdo_od("sync_mode").index
    DEVICE_RESET_INDEX = required_non_pdo_od("device_reset_command").index
    DEVICE_RESET_COMMAND_SUBINDEX = required_non_pdo_od("device_reset_command").subindex
    PARAMETER_SAVE_INDEX = required_non_pdo_od("parameter_save_command").index
    PARAMETER_SAVE_COMMAND_SUBINDEX = required_non_pdo_od("parameter_save_command").subindex
    PARAMETER_SAVE_STATUS_SUBINDEX = required_non_pdo_od("parameter_save_status").subindex
    PARAMETER_SAVE_SELECTION_SUBINDEX = required_non_pdo_od(
        "parameter_save_selection"
    ).subindex
    PARAMETER_SAVE_RETURN_CODE_SUBINDEX = required_non_pdo_od(
        "parameter_save_return_code"
    ).subindex
    PARAMETER_SAVE_RETURN_VALUE_SUBINDEX = required_non_pdo_od(
        "parameter_save_return_value"
    ).subindex

    MOTION_MODES = {
        "pp": PROFILE_POSITION_MODE,
        "pv": PROFILE_VELOCITY_MODE,
        "jog": JOG_MODE,
        "csp": CSP_MODE,
    }

    pdo_codec = CiA402PdoCodec

    def create_rxpdo(self):
        return RxPDO(self.pdo_configuration)

    def create_txpdo(self):
        return TxPDO(self.pdo_configuration)

    def prepare_process_image(
        self,
        master,
        slave_index,
    ):
        self.validate_identity(master, slave_index)
        self.validate_catalog_support()
        expected_rxpdo = self.expected_rxpdo_mapping_entries()
        expected_txpdo = self.expected_txpdo_mapping_entries()

        self.write_pdo_mapping(
            master,
            slave_index,
            label="RxPDO",
            assignment_index=0x1C12,
            pdo_index=0x1600,
            mapping_entries=expected_rxpdo,
        )
        self.write_pdo_mapping(
            master,
            slave_index,
            label="TxPDO",
            assignment_index=0x1C13,
            pdo_index=0x1A00,
            mapping_entries=expected_txpdo,
        )

        actual_rxpdo = master.read_assigned_pdo_mapping_entries(
            slave_index,
            0x1C12,
        )
        actual_txpdo = master.read_assigned_pdo_mapping_entries(
            slave_index,
            0x1C13,
        )

        self.validate_pdo_mapping(
            slave_index,
            "RxPDO",
            expected_rxpdo,
            actual_rxpdo,
        )
        self.validate_pdo_mapping(
            slave_index,
            "TxPDO",
            expected_txpdo,
            actual_txpdo,
        )

        master.slaves[slave_index].rxpdo.select_mapping(actual_rxpdo)
        master.slaves[slave_index].txpdo.select_mapping(actual_txpdo)
        print(
            f"Slave {slave_index}: validated {self.name.upper()} "
            f"identity and PDO mapping from device "
            f"pdo_configuration={self.pdo_configuration.name}",
            flush=True,
        )

    def write_pdo_mapping(
        self,
        master,
        slave_index,
        label,
        assignment_index,
        pdo_index,
        mapping_entries,
    ):
        mapping_entries = [int(entry) for entry in mapping_entries]
        master.sdo.write_uint8(slave_index, assignment_index, 0, 0)
        master.sdo.write_uint8(slave_index, pdo_index, 0, 0)

        for subindex, mapping_entry in enumerate(mapping_entries, start=1):
            master.sdo.write_uint32(
                slave_index,
                pdo_index,
                subindex,
                mapping_entry,
            )

        master.sdo.write_uint8(
            slave_index,
            pdo_index,
            0,
            len(mapping_entries),
        )
        master.sdo.write_uint16(slave_index, assignment_index, 1, pdo_index)
        master.sdo.write_uint8(slave_index, assignment_index, 0, 1)

        print(
            f"Slave {slave_index}: wrote {self.name.upper()} {label} mapping "
            f"assignment=0x{assignment_index:04X} pdo=0x{pdo_index:04X} "
            f"entries={len(mapping_entries)}",
            flush=True,
        )

    def validate_identity(self, master, slave_index):
        if self.esi_catalog is None:
            return

        identity = master.read_slave_identity(slave_index)
        actual_product_code = identity.get("product_code")
        if actual_product_code is None:
            raise RuntimeError(
                f"{self.name.upper()} identity read failed on slave {slave_index}. "
                "Could not read product code from EtherCAT identity object."
            )

        expected_product_code = int(self.esi_catalog.product_code)
        if int(actual_product_code) != expected_product_code:
            raise RuntimeError(
                f"CMMT profile mismatch on slave {slave_index}. "
                f"Configured={self.name} "
                f"({self.esi_catalog.type_name}, "
                f"product_code={expected_product_code}/0x{expected_product_code:08X}) "
                f"Actual product_code={int(actual_product_code)}/"
                f"0x{int(actual_product_code):08X}. "
                "Check MOTION_SERVER_BUS and use cmmt_as or cmmt_st for the "
                "actual drive type."
            )

        actual_revision = identity.get("revision")
        expected_revision = int(self.esi_catalog.revision)
        revision_text = "unknown"
        if actual_revision is not None:
            revision_text = f"0x{int(actual_revision):08X}"
        print(
            f"Slave {slave_index}: {self.name.upper()} identity "
            f"type={self.esi_catalog.type_name} "
            f"product_code=0x{expected_product_code:08X} "
            f"revision={revision_text} "
            f"esi_revision=0x{expected_revision:08X}",
            flush=True,
        )

    def validate_catalog_support(self):
        if self.esi_catalog is None:
            return

        for role in self.pdo_configuration.od_roles():
            self.validate_catalog_od_role(
                role.role,
                role.index,
                role.subindex,
                role.object_entry().bit_length,
                "PDO configuration",
            )

        for role in self.required_non_pdo_od_roles():
            self.validate_catalog_od_role(
                role.role,
                role.index,
                role.subindex,
                self.expected_data_type_bits(role.data_type),
                "required non-PDO OD",
            )

    def validate_catalog_od_role(
        self,
        role,
        index,
        subindex,
        expected_bit_length,
        source,
    ):
        try:
            catalog_object = self.esi_catalog.object_info(index, subindex)
        except KeyError as exc:
            raise RuntimeError(
                f"{self.name.upper()} {source} role {role!r} references "
                f"0x{index:04X}:{subindex:02X}, but it is not present in "
                f"{self.esi_catalog.path.name}."
            ) from exc

        if catalog_object.bit_size != int(expected_bit_length):
            raise RuntimeError(
                f"{self.name.upper()} {source} role {role!r} bit size mismatch "
                f"at 0x{index:04X}:{subindex:02X}. "
                f"Configured={expected_bit_length}, "
                f"ESI={catalog_object.bit_size} "
                f"({catalog_object.name})."
            )

    @staticmethod
    def expected_data_type_bits(data_type):
        from device.pdo_metadata import ObjectDictionaryEntry

        return ObjectDictionaryEntry(
            0,
            0,
            "",
            data_type,
        ).bit_length

    def required_non_pdo_od_roles(self):
        return cmmt_required_non_pdo_od_roles()

    def object_dictionary_entries(self):
        if self.esi_catalog is None:
            return ()
        return tuple(self.esi_catalog.objects.items())

    def expected_rxpdo_mapping_entries(self):
        return self.pdo_configuration.rxpdo_mapping_entries()

    def expected_txpdo_mapping_entries(self):
        return self.pdo_configuration.txpdo_mapping_entries()

    def validate_pdo_mapping(self, slave_index, label, expected, actual):
        expected = list(expected)
        actual = list(actual)
        if actual == expected:
            return

        raise RuntimeError(
            f"CMMT {label} mapping mismatch on slave {slave_index}.\n"
            f"Expected {label}:\n{self.format_pdo_entries(expected)}\n"
            f"Actual {label}:\n{self.format_pdo_entries(actual)}\n"
            "Configure the drive PDO mapping before starting Motion Server."
        )

    @staticmethod
    def format_pdo_entries(entries):
        if not entries:
            return "  <empty>"
        lines = []
        total_bits = 0
        for entry in entries:
            entry = int(entry)
            index = (entry >> 16) & 0xFFFF
            subindex = (entry >> 8) & 0xFF
            bit_length = entry & 0xFF
            total_bits += bit_length
            lines.append(
                f"  0x{entry:08X} -> "
                f"0x{index:04X}:{subindex:02X} {bit_length} bits"
            )
        lines.append(f"  total: {total_bits} bits / {total_bits // 8} bytes")
        return "\n".join(lines)

    MAIN_GROUPS = {
        1: "Current",
        2: "Voltage",
        3: "Temperature",
        5: "Motion",
        6: "Configuration/parameterization",
        7: "Monitoring",
        8: "Communication",
        9: "Safety engineering",
        10: "Internal hardware",
        11: "Software",
        12: "Maintenance",
        13: "Various",
        16: "External device",
        17: "Security (data)",
        18: "Encoder",
    }
    SUBGROUPS = {
        (1, 1): "Short circuit",
        (1, 2): "I2t",
        (1, 3): "Braking resistor",
        (2, 1): "Supply",
        (2, 2): "DC link circuit",
        (2, 3): "Principal voltage",
        (2, 4): "Encoder supply",
        (3, 1): "Device",
        (3, 2): "Output stage",
        (3, 3): "Motor",
        (5, 1): "Homing",
        (5, 2): "Motion control",
        (5, 3): "Interpolation",
        (6, 0): "No allocation",
        (6, 2): "Critical limits",
        (6, 5): "Parameter set",
        (7, 1): "Limitations",
        (7, 2): "Motion monitoring",
        (7, 3): "Critical limits",
        (7, 4): "Zero angle detection",
        (7, 5): "Analogue input",
        (7, 11): "Friction",
        (8, 0): "No allocation",
        (8, 3): "PROFINET",
        (8, 4): "EtherCAT",
        (8, 6): "EtherNet",
        (8, 9): "PROFIdrive",
        (8, 12): "CiA 402",
        (8, 13): "EtherNet/IP",
        (8, 14): "MP",
        (9, 0): "No allocation",
        (9, 1): "STO",
        (9, 2): "SBC",
        (10, 1): "Module error",
        (11, 0): "No allocation",
        (11, 1): "Exception",
        (11, 2): "Task",
        (11, 3): "File system",
        (11, 4): "Firmware update",
        (11, 5): "Device configuration",
        (11, 6): "LibRTE",
        (11, 7): "Warm start",
        (11, 8): "Version management",
        (12, 1): "Operating time",
        (13, 1): "Diagnostics",
        (13, 2): "Auto-tuning",
        (16, 1): "CDSB",
        (17, 1): "User login",
        (18, 0): "No allocation",
        (18, 1): "EnDat",
        (18, 2): "Hiperface",
        (18, 3): "Quadrature incremental encoder",
        (18, 4): "Nikon A",
        (18, 5): "BiSS C",
        (18, 6): "Sin/Cos",
        (18, 7): "ProfiDrive",
    }

    def __init__(self, axis_index=None, slave_index=None, device_config=None):
        self.axis_index = axis_index
        self.slave_index = slave_index
        self.error_catalog = load_cmmt_error_catalog()
        self.non_pdo_configuration = (
            device_config.non_pdo_configuration
            if device_config is not None
            else None
        )
        self.esi_catalog = (
            cmmt_catalog_by_profile_name(self.name)
            if self.variant is not None
            else None
        )
        if device_config is None:
            self.pdo_configuration = get_pdo_configuration()
            self.pdo_configuration_source = "profile default"
        else:
            self.pdo_configuration = get_pdo_configuration(
                device_config.pdo_configuration,
            )
            self.pdo_configuration_source = "typed device config"

    def mode_code(self, mode_name):
        if mode_name == "homing":
            return self.HOMING_MODE
        return self.MOTION_MODES[mode_name]

    def read_diagnostics(self, master, axis_index):
        diagnostics = {}
        try:
            diagnostics["statusword"] = master.sdo.read_uint16(
                axis_index,
                self.STATUSWORD_INDEX,
                0,
            )
        except Exception as exc:
            diagnostics["statusword"] = f"read failed: {exc}"

        try:
            diagnostics["error_code"] = master.sdo.read_uint32(
                axis_index,
                self.ERROR_CODE_INDEX,
                self.ERROR_CODE_SUBINDEX,
            )
        except Exception as exc:
            diagnostics["error_code"] = f"read failed: {exc}"

        diagnostics["error_code_text"] = self.format_error_code(
            diagnostics["error_code"]
        )

        try:
            diagnostics["mode_display"] = master.sdo.read_int8(
                axis_index,
                self.MODE_DISPLAY_INDEX,
                0,
            )
        except Exception as exc:
            diagnostics["mode_display"] = f"read failed: {exc}"

        return diagnostics

    def read_user_unit_position(self, master, axis_index):
        return master.sdo.read_uint16(
            axis_index,
            self.USER_UNIT_INDEX,
            self.USER_UNIT_POSITION_SUBINDEX,
        )

    def read_converting_unit_exponents(self, master, axis_index):
        subindices = [
            self.CONVERTING_UNIT_POSITION_SUBINDEX,
            self.CONVERTING_UNIT_VELOCITY_SUBINDEX,
            self.CONVERTING_UNIT_ACCELERATION_SUBINDEX,
            self.CONVERTING_UNIT_JERK_SUBINDEX,
        ]
        values = []
        for value_index, subindex in enumerate(subindices):
            try:
                value = int(master.sdo.read_int8(
                    axis_index,
                    self.CONVERTING_UNIT_INDEX,
                    subindex,
                ))
            except Exception as exc:
                value = self.DEFAULT_CONVERTING_UNIT_EXPONENTS[value_index]
                print(
                    "CMMT converting unit exponent read failed; "
                    "using default. "
                    f"axis={axis_index} "
                    f"object=0x{self.CONVERTING_UNIT_INDEX:04X}:{subindex:02X} "
                    f"default={value} error={exc}",
                    flush=True,
                )
            values.append(value)
        return values

    def format_error_code(self, error_code):
        if not isinstance(error_code, int):
            return "read fail"
        if error_code == 0:
            return "No error"

        catalog_entry = self.error_catalog.get(error_code)
        if catalog_entry is not None:
            return self._format_catalog_entry(catalog_entry)

        main_group = (error_code >> 24) & 0xFF
        subgroup = (error_code >> 16) & 0xFF
        error_number = error_code & 0xFFFF
        if main_group or subgroup:
            main_text = self.MAIN_GROUPS.get(main_group, "Unknown main group")
            subgroup_text = self.SUBGROUPS.get(
                (main_group, subgroup),
                "Unknown subgroup",
            )
            return (
                f"Error {error_number} | "
                f"{main_group:02d} {main_text} / "
                f"{subgroup:02d} {subgroup_text}"
            )

        return f"Error {error_number} | CMMT 16-bit error number"

    def _format_catalog_entry(self, entry):
        parts = [
            f"{entry['id']} {entry['message']}",
        ]
        if entry.get("description"):
            parts.append(entry["description"])
        if entry.get("remedy"):
            parts.append(f"Remedy: {entry['remedy']}")
        if entry.get("classification"):
            parts.append(f"Classification: {entry['classification']}")
        return " | ".join(parts)

    def configure_mode_code(self, master, axis_index, code):
        master.sdo.write_int8(axis_index, self.MODE_OF_OPERATION_INDEX, 0, code)
        master.slaves[axis_index].rxpdo.mode_of_operation = code

    def write_csp_interpolation_mode(self, master, axis_index, value):
        master.sdo.write_uint32(
            axis_index,
            self.CSP_INTERPOLATION_MODE_INDEX,
            self.CSP_INTERPOLATION_MODE_SUBINDEX,
            int(value),
        )
        return master.sdo.read_uint32(
            axis_index,
            self.CSP_INTERPOLATION_MODE_INDEX,
            self.CSP_INTERPOLATION_MODE_SUBINDEX,
        )

    def write_profile_settings(
        self,
        master,
        axis_index,
        profile_velocity,
        profile_acceleration,
        profile_deceleration,
    ):
        master.sdo.write_uint32(
            axis_index,
            self.PROFILE_VELOCITY_INDEX,
            0,
            max(0, int(profile_velocity)),
        )
        master.sdo.write_uint32(
            axis_index,
            self.PROFILE_ACCELERATION_INDEX,
            0,
            max(0, int(profile_acceleration)),
        )
        master.sdo.write_uint32(
            axis_index,
            self.PROFILE_DECELERATION_INDEX,
            0,
            max(0, int(profile_deceleration)),
        )

    def write_profile_motion_limits(self, master, axis_index, limits):
        self.write_profile_settings(
            master,
            axis_index,
            limits.max_velocity,
            limits.acceleration,
            limits.deceleration,
        )

    def write_motion_limits(
        self,
        master,
        axis_index,
        positive_velocity_limit,
        negative_velocity_limit,
        max_acceleration,
        max_deceleration,
    ):
        master.sdo.write_uint32(
            axis_index,
            self.MAX_PROFILE_VELOCITY_INDEX,
            0,
            max(0, int(positive_velocity_limit)),
        )
        master.sdo.write_float32(
            axis_index,
            self.NEGATIVE_VELOCITY_LIMIT_INDEX,
            self.NEGATIVE_VELOCITY_LIMIT_SUBINDEX,
            float(negative_velocity_limit) / 1000.0,
        )
        master.sdo.write_uint32(
            axis_index,
            self.MAX_ACCELERATION_INDEX,
            0,
            max(0, int(max_acceleration)),
        )
        master.sdo.write_uint32(
            axis_index,
            self.MAX_DECELERATION_INDEX,
            0,
            max(0, int(max_deceleration)),
        )

    def read_profile_settings(self, master, axis_index):
        return [
            float(master.sdo.read_uint32(
                axis_index,
                self.PROFILE_VELOCITY_INDEX,
                0,
            )),
            float(master.sdo.read_uint32(
                axis_index,
                self.PROFILE_ACCELERATION_INDEX,
                0,
            )),
            float(master.sdo.read_uint32(
                axis_index,
                self.PROFILE_DECELERATION_INDEX,
                0,
            )),
            float(master.sdo.read_uint32(
                axis_index,
                self.PP_JERK_INDEX,
                self.PP_JERK_SUBINDEX,
            )),
        ]

    def read_motion_limits(self, master, axis_index):
        positive_velocity_limit = float(master.sdo.read_uint32(
            axis_index,
            self.MAX_PROFILE_VELOCITY_INDEX,
            0,
        ))
        negative_velocity_limit = float(master.sdo.read_float32(
            axis_index,
            self.NEGATIVE_VELOCITY_LIMIT_INDEX,
            self.NEGATIVE_VELOCITY_LIMIT_SUBINDEX,
        )) * 1000.0
        return [
            positive_velocity_limit,
            negative_velocity_limit,
            float(master.sdo.read_uint32(
                axis_index,
                self.MAX_ACCELERATION_INDEX,
                0,
            )),
            float(master.sdo.read_uint32(
                axis_index,
                self.MAX_DECELERATION_INDEX,
                0,
            )),
        ]

    def write_profile_jerk(self, master, axis_index, pp_jerk):
        master.sdo.write_uint32(
            axis_index,
            self.PP_JERK_INDEX,
            self.PP_JERK_SUBINDEX,
            max(0, int(pp_jerk)),
        )

    def read_software_position_limits(self, master, axis_index):
        return [
            master.sdo.read_int32(
                axis_index,
                self.SOFTWARE_POSITION_LIMIT_INDEX,
                1,
            ),
            master.sdo.read_int32(
                axis_index,
                self.SOFTWARE_POSITION_LIMIT_INDEX,
                2,
            ),
        ]

    def write_software_position_limits(
        self,
        master,
        axis_index,
        negative_limit,
        positive_limit,
    ):
        master.sdo.write_int32(
            axis_index,
            self.SOFTWARE_POSITION_LIMIT_INDEX,
            1,
            negative_limit,
        )
        master.sdo.write_int32(
            axis_index,
            self.SOFTWARE_POSITION_LIMIT_INDEX,
            2,
            positive_limit,
        )

    def configure_sync_parameters(
        self,
        master,
        slave_index,
        sync_mode,
        cycle_time,
    ):
        if sync_mode is None:
            return False

        master.sdo.write_uint16(
            slave_index,
            self.SYNC_PARAMETER_INDEX,
            0x01,
            sync_mode,
        )
        master.sdo.write_float32(
            slave_index,
            self.SYNC_PARAMETER_INDEX,
            0x02,
            cycle_time,
        )
        master.sdo.write_float32(
            slave_index,
            self.SYNC_PARAMETER_INDEX,
            0x09,
            cycle_time,
        )
        return True

    def save_parameters(self, master, axis_index):
        master.sdo.write_uint16(
            axis_index,
            self.PARAMETER_SAVE_INDEX,
            self.PARAMETER_SAVE_SELECTION_SUBINDEX,
            1,
        )
        try:
            master.sdo.write_uint8(
                axis_index,
                self.PARAMETER_SAVE_INDEX,
                self.PARAMETER_SAVE_COMMAND_SUBINDEX,
                1,
            )
            status = master.sdo.read_uint8(
                axis_index,
                self.PARAMETER_SAVE_INDEX,
                self.PARAMETER_SAVE_STATUS_SUBINDEX,
            )
            return_code = master.sdo.read_uint16(
                axis_index,
                self.PARAMETER_SAVE_INDEX,
                self.PARAMETER_SAVE_RETURN_CODE_SUBINDEX,
            )
            return_value = master.sdo.read_uint16(
                axis_index,
                self.PARAMETER_SAVE_INDEX,
                self.PARAMETER_SAVE_RETURN_VALUE_SUBINDEX,
            )
        finally:
            master.sdo.write_uint8(
                axis_index,
                self.PARAMETER_SAVE_INDEX,
                self.PARAMETER_SAVE_COMMAND_SUBINDEX,
                0,
            )
        return {
            "status": int(status),
            "return_code": int(return_code),
            "return_value": int(return_value),
        }

    def request_axis_restart(self, master, axis_index):
        self.write_axis_restart_command(master, axis_index, 0)
        return self.write_axis_restart_command(master, axis_index, 1)

    def clear_axis_restart_request(self, master, axis_index):
        return self.write_axis_restart_command(master, axis_index, 0)

    def write_axis_restart_command(self, master, axis_index, value):
        master.sdo.write_uint8(
            axis_index,
            self.DEVICE_RESET_INDEX,
            self.DEVICE_RESET_COMMAND_SUBINDEX,
            int(value),
        )
        return {
            "object": (
                f"0x{self.DEVICE_RESET_INDEX:04X}:"
                f"{self.DEVICE_RESET_COMMAND_SUBINDEX:02X}"
            ),
            "command": int(value),
        }


class CMMTASDeviceProfile(CMMTDeviceProfile):
    name = "cmmt_as"
    variant = "as"


class CMMTSTDeviceProfile(CMMTDeviceProfile):
    name = "cmmt_st"
    variant = "st"
