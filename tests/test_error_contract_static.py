import ast
import unittest
from pathlib import Path

from motion_server.failure import EXCEPTION_FAILURE_MAPPINGS, FailureCode


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    "motion_server",
    "ethercat",
    "device",
    "control_panel",
    "motion_server_client",
    "ros",
)

# Broad catches are approved by function rather than line number so formatting
# changes do not invalidate the contract. Adding a new entry requires selecting
# one of the documented boundary/translation/best-effort purposes.
APPROVED_BROAD_CATCHES = {
    "control_panel/axis_control_panel/client.py::_connection_loop",
    "control_panel/axis_control_panel/connection.py::try_send",
    "control_panel/axis_control_panel/diagnosis.py::process_panel_sdo_read_queue",
    "control_panel/io_control_panel/client.py::_connection_loop",
    "control_panel/io_control_panel/control_panel.py::apply_digital_output",
    "control_panel/io_control_panel/control_panel.py::load_ec_catalog",
    "control_panel/io_control_panel/control_panel.py::load_iol_catalog",
    "control_panel/io_control_panel/control_panel.py::read_ap_parameter",
    "control_panel/io_control_panel/control_panel.py::read_iol_parameter",
    "control_panel/io_control_panel/control_panel.py::read_parameter",
    "control_panel/io_control_panel/control_panel.py::refresh",
    "control_panel/io_control_panel/control_panel.py::toggle_command_authority",
    "control_panel/io_control_panel/control_panel.py::write_ap_parameter",
    "control_panel/io_control_panel/control_panel.py::write_iol_parameter",
    "control_panel/io_control_panel/control_panel.py::write_parameter",
    "device/cmmt/profile.py::read_converting_unit_exponents",
    "device/cmmt/profile.py::read_diagnostics",
    "device/virtual_servo_drive/servo_model.py::_unit_scale",
    "ethercat/mock_master.py::read_sdo",
    "ethercat/mock_master.py::write_sdo",
    "ethercat/pysoem_master.py::connect",
    "ethercat/pysoem_master.py::describe_slaves",
    "ethercat/pysoem_master.py::get_dc_time_ns",
    "ethercat/pysoem_master.py::read_sdo",
    "ethercat/pysoem_master.py::read_slave_identity",
    "ethercat/pysoem_master.py::write_sdo",
    "motion_server/api/router.py::request_response",
    "motion_server/app/startup.py::clear_axis_restart_commands",
    "motion_server/app/startup.py::read_axis_converting_unit_exponents",
    "motion_server/app/startup.py::read_axis_motion_limits",
    "motion_server/app/startup.py::read_axis_profile_settings",
    "motion_server/app/startup.py::read_axis_software_position_limits",
    "motion_server/app/startup.py::read_axis_user_position_units",
    "motion_server/app/startup.py::write_csp_interpolation_modes",
    "motion_server/device_manager/axis_diagnostics.py::diagnostics_summary",
    "motion_server/handlers/command/axis_settings.py::set_mode",
    "motion_server/handlers/command/axis_settings.py::set_motion_limits",
    "motion_server/handlers/command/axis_settings.py::set_profile",
    "motion_server/handlers/command/axis_settings.py::set_software_position_limits",
    "motion_server/handlers/command/axis_state.py::disable",
    "motion_server/handlers/command/axis_state.py::enable",
    "motion_server/handlers/command/axis_state.py::reset_axes",
    "motion_server/handlers/command/axis_state.py::restart_axis",
    "motion_server/handlers/command/axis_state.py::stop_axes",
    "motion_server/handlers/command/jog.py::start_jog",
    "motion_server/handlers/command/jog.py::stop_jog",
    "motion_server/handlers/command/motion.py::command_position_axes",
    "motion_server/handlers/command/motion.py::move_absolute",
    "motion_server/handlers/command/motion.py::move_relative",
    "motion_server/handlers/command/motion.py::move_velocity",
    "motion_server/handlers/command/trajectory.py::stop",
    "motion_server/server.py::run_main_once",
    "ros/bridge.py::connection_loop",
    "ros/control_panel.py::follow_joint_action_ready",
}


def source_files():
    for root_name in SOURCE_ROOTS:
        yield from (REPOSITORY_ROOT / root_name).rglob("*.py")


def owner_name(node, parents):
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
    return "<module>"


def broad_catch_locations():
    locations = set()
    for path in source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if not isinstance(node.type, ast.Name):
                continue
            if node.type.id not in {"Exception", "BaseException"}:
                continue
            locations.add(f"{relative}::{owner_name(node, parents)}")
    return locations


class ErrorContractStaticTest(unittest.TestCase):
    def test_broad_catches_match_approved_function_allowlist(self):
        self.assertEqual(broad_catch_locations(), APPROVED_BROAD_CATCHES)

    def test_all_registered_mappings_use_public_failure_codes(self):
        public_codes = set(FailureCode)
        self.assertTrue(EXCEPTION_FAILURE_MAPPINGS)
        for exception_type, mapping in EXCEPTION_FAILURE_MAPPINGS.items():
            self.assertTrue(issubclass(exception_type, Exception))
            self.assertIn(mapping.code, public_codes)
            self.assertTrue(mapping.default_message)

    def test_request_capture_and_legacy_rejection_are_absent(self):
        forbidden = (
            "_RequestCaptureConnection",
            "_operation_result",
            "reject_command_message",
            "TECH_DEBT[TD-005]",
        )
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (REPOSITORY_ROOT / "motion_server").rglob("*.py")
        )
        for token in forbidden:
            self.assertNotIn(token, source)

    def test_request_handlers_do_not_send_transport_messages(self):
        checked_roots = (
            REPOSITORY_ROOT / "motion_server" / "handlers",
            REPOSITORY_ROOT / "motion_server" / "control",
        )
        for root in checked_roots:
            for path in root.rglob("*.py"):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("send_client_message", source, str(path))


if __name__ == "__main__":
    unittest.main()
