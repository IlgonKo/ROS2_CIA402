from device.cmmt.error_catalog import load_cmmt_error_catalog
from device.cmmt.txpdo import TxPDO


class CMMTDeviceProfile:
    name = "cmmt"

    PROFILE_POSITION_MODE = 1
    HOMING_MODE = 6
    CSP_MODE = 8
    CSV_MODE = 9

    PP_BASE_CONTROLWORD = 0x000F
    PP_NEW_SETPOINT_CONTROLWORD = 0x003F
    PP_SETPOINT_ACK_BIT = 12
    PP_SETPOINT_ACK_MASK = 1 << PP_SETPOINT_ACK_BIT
    PP_HANDSHAKE_MAX_CYCLES = 100

    HOMING_START_BIT = 1 << 4
    HOMING_REFERENCED_MASK = 1 << 15
    HOMING_ERROR_MASK = 1 << 13

    STATUSWORD_INDEX = 0x6041
    ERROR_CODE_INDEX = 0x2145
    ERROR_CODE_SUBINDEX = 0x0C
    MODE_DISPLAY_INDEX = 0x6061
    MODE_OF_OPERATION_INDEX = 0x6060
    CSP_INTERPOLATION_MODE_INDEX = 0x217B
    CSP_INTERPOLATION_MODE_SUBINDEX = 0x0D
    PP_JERK_INDEX = 0x60A4
    PP_JERK_SUBINDEX = 0x01
    SOFTWARE_POSITION_LIMIT_INDEX = 0x607D
    PROFILE_VELOCITY_INDEX = 0x6081
    PROFILE_ACCELERATION_INDEX = 0x6083
    PROFILE_DECELERATION_INDEX = 0x6084
    SYNC_PARAMETER_INDEX = 0x212E

    MOTION_MODES = {
        "pp": PROFILE_POSITION_MODE,
        "csp": CSP_MODE,
        "csv": CSV_MODE,
    }

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

    def __init__(self):
        self.error_catalog = load_cmmt_error_catalog()

    def mode_code(self, mode_name):
        if mode_name == "homing":
            return self.HOMING_MODE
        return self.MOTION_MODES[mode_name]

    def read_diagnostics(self, master, axis_index):
        diagnostics = {}
        try:
            diagnostics["statusword"] = master.sdo_read_uint16(
                axis_index,
                self.STATUSWORD_INDEX,
                0,
            )
        except Exception as exc:
            diagnostics["statusword"] = f"read failed: {exc}"

        try:
            diagnostics["error_code"] = master.sdo_read_uint32(
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
            diagnostics["mode_display"] = master.sdo_read_int8(
                axis_index,
                self.MODE_DISPLAY_INDEX,
                0,
            )
        except Exception as exc:
            diagnostics["mode_display"] = f"read failed: {exc}"

        return diagnostics

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
        master.slaves[axis_index].rxpdo.mode_of_operation = code
        master.sdo_write_int8(axis_index, self.MODE_OF_OPERATION_INDEX, 0, code)

    def write_csp_interpolation_mode(self, master, axis_index, value):
        master.sdo_write_uint32(
            axis_index,
            self.CSP_INTERPOLATION_MODE_INDEX,
            self.CSP_INTERPOLATION_MODE_SUBINDEX,
            int(value),
        )
        return master.sdo_read_uint32(
            axis_index,
            self.CSP_INTERPOLATION_MODE_INDEX,
            self.CSP_INTERPOLATION_MODE_SUBINDEX,
        )

    def write_profile_motion_limits(self, master, axis_index, limits):
        master.sdo_write_uint32(
            axis_index,
            self.PROFILE_VELOCITY_INDEX,
            0,
            max(0, int(limits.max_velocity)),
        )
        master.sdo_write_uint32(
            axis_index,
            self.PROFILE_ACCELERATION_INDEX,
            0,
            max(0, int(limits.acceleration)),
        )
        master.sdo_write_uint32(
            axis_index,
            self.PROFILE_DECELERATION_INDEX,
            0,
            max(0, int(limits.deceleration)),
        )

    def write_profile_jerk(self, master, axis_index, pp_jerk):
        master.sdo_write_uint32(
            axis_index,
            self.PP_JERK_INDEX,
            self.PP_JERK_SUBINDEX,
            max(0, int(pp_jerk)),
        )

    def read_software_position_limits(self, master, axis_index):
        return [
            master.sdo_read_int32(
                axis_index,
                self.SOFTWARE_POSITION_LIMIT_INDEX,
                1,
            ),
            master.sdo_read_int32(
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
        master.sdo_write_int32(
            axis_index,
            self.SOFTWARE_POSITION_LIMIT_INDEX,
            1,
            negative_limit,
        )
        master.sdo_write_int32(
            axis_index,
            self.SOFTWARE_POSITION_LIMIT_INDEX,
            2,
            positive_limit,
        )

    def default_txpdo1_mapping(self):
        return (
            TxPDO.MAPPING_ENTRIES,
            "Restored TxPDO1 mapping: default CMMT feedback layout",
        )

    def txpdo_setpoint_mapping(self):
        return (
            TxPDO.SETPOINT_REPLACE_ENTRIES,
            "Configured TxPDO1 mapping: replaced 0x6064:00 actual position "
            "with 0x6062:00 setpoint position",
        )

    def configure_sync_parameters(self, master, axis_count, sync_mode, cycle_time):
        if sync_mode is None:
            return False

        for axis_index in range(axis_count):
            master.sdo_write_uint16(
                axis_index,
                self.SYNC_PARAMETER_INDEX,
                0x01,
                sync_mode,
            )
            master.sdo_write_float32(
                axis_index,
                self.SYNC_PARAMETER_INDEX,
                0x02,
                cycle_time,
            )
            master.sdo_write_float32(
                axis_index,
                self.SYNC_PARAMETER_INDEX,
                0x09,
                cycle_time,
            )
        return True
