import ast
import unittest
from collections import Counter
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
    "motion_server/handlers/command/axis_settings.py::set_software_position_limits",
    "motion_server/handlers/command/motion.py::command_position_axes",
    "motion_server/server.py::run_main_once",
    "ros/bridge.py::connection_loop",
    "ros/control_panel.py::follow_joint_action_ready",
}

APPROVED_BROAD_CATCH_COUNTS = {
    "device/cmmt/profile.py::read_diagnostics": 3,
    "ethercat/pysoem_master.py::connect": 2,
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


def broad_exception_names(tree):
    names = {"Exception", "BaseException"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module != "builtins":
            continue
        for imported_name in node.names:
            if imported_name.name in {"Exception", "BaseException"}:
                names.add(imported_name.asname or imported_name.name)
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Name):
                continue
            if node.value.id not in names:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id not in names:
                    names.add(target.id)
                    changed = True
    return names


def is_broad_exception_type(node, names=None):
    names = names or {"Exception", "BaseException"}
    if node is None:
        return True
    if isinstance(node, ast.Name):
        return node.id in names
    if isinstance(node, ast.Attribute):
        return node.attr in {"Exception", "BaseException"}
    if isinstance(node, ast.Tuple):
        return any(is_broad_exception_type(item, names) for item in node.elts)
    return False


def broad_catch_locations():
    locations = Counter()
    for path in source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        names = broad_exception_names(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if not is_broad_exception_type(node.type, names):
                continue
            locations[f"{relative}::{owner_name(node, parents)}"] += 1
    return locations


class ErrorContractStaticTest(unittest.TestCase):
    def test_broad_catch_detector_includes_bare_tuple_and_attribute_forms(self):
        source = """
from builtins import Exception as RootException
AssignedException = RootException
try: pass
except: pass
try: pass
except (ValueError, Exception): pass
try: pass
except builtins.BaseException: pass
try: pass
except RootException: pass
try: pass
except AssignedException: pass
try: pass
except ValueError: pass
"""
        tree = ast.parse(source)
        handlers = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ExceptHandler)
        ]
        names = broad_exception_names(tree)
        self.assertEqual(
            [is_broad_exception_type(handler.type, names) for handler in handlers],
            [True, True, True, True, True, False],
        )

    def test_broad_catches_match_approved_function_allowlist(self):
        actual = broad_catch_locations()
        expected = Counter({location: 1 for location in APPROVED_BROAD_CATCHES})
        expected.update({
            location: count - 1
            for location, count in APPROVED_BROAD_CATCH_COUNTS.items()
        })
        self.assertEqual(actual, expected)

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
            "raise_operation_rejected",
            "send_status_operation",
            '"ok": True',
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
