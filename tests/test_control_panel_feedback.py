import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from control_panel.axis_control_panel.client import AxisServerClient
from control_panel.axis_control_panel.control_panel import AxisServerControlPanel
from control_panel.axis_control_panel.diagnosis import DiagnosisMixin
from control_panel.io_control_panel.client import MotionServerClient
from control_panel.io_control_panel.control_panel import IOControlPanel
from control_panel.axis_control_panel.panel_update_data import (
    initial_feedback,
    merge_axis_status,
)
from control_panel.server_health import (
    format_server_health,
    normalize_server_health,
)
from motion_server.app.initialization import (
    INITIALIZATION_CAUSE_DEFINITIONS,
    InitializationCause,
    InitializationFailure,
    InitializationStatus,
)
from motion_server.app.session import ServerRuntimeState, ServerSession
from motion_server.handlers.status.feedback import system_feedback_message


class AxisFeedbackBootstrapTest(unittest.TestCase):
    def test_selected_axis_status_request_is_deduplicated_unless_forced(self):
        requests = []
        client = SimpleNamespace(
            process_data_valid=lambda: True,
            request_axis_status=lambda axis: requests.append(axis),
        )
        panel = object.__new__(AxisServerControlPanel)
        panel.axis_count = 2
        panel.client = client
        panel._last_axis_status_request = None
        panel.selected_axis = lambda: 0

        panel.request_selected_axis_status()
        panel.request_selected_axis_status()
        panel.request_selected_axis_status(force=True)

        self.assertEqual(requests, [0, 0])

    def test_first_feedback_latches_axis_count(self):
        client = AxisServerClient("127.0.0.1", 15000)
        initialized = client._merge_system_feedback(
            {
                "type": "system/feedback",
                "actual_positions": [1.0, 2.0, 3.0, 4.0],
                "process_data_valid": True,
                "server_health": {"runtime_state": "normal"},
            }
        )

        self.assertTrue(initialized)
        self.assertEqual(client.axis_count, 4)
        self.assertEqual(client.feedback["actual_positions"], [1.0, 2.0, 3.0, 4.0])

    def test_empty_degraded_feedback_does_not_invent_an_axis(self):
        client = AxisServerClient("127.0.0.1", 15000)
        initialized = client._merge_system_feedback(
            {
                "type": "system/feedback",
                "actual_positions": [],
                "process_data_valid": False,
                "server_health": {"runtime_state": "initialization_error"},
            }
        )

        self.assertFalse(initialized)
        self.assertEqual(client.axis_count, 0)
        self.assertEqual(
            client.feedback["server_health"]["runtime_state"],
            "initialization_error",
        )

    def test_changed_axis_count_requires_panel_restart(self):
        client = AxisServerClient("127.0.0.1", 15000, axis_count=2)
        client._merge_system_feedback(
            {
                "type": "system/feedback",
                "actual_positions": [1.0, 2.0, 3.0],
                "process_data_valid": True,
                "server_health": {"runtime_state": "normal"},
            }
        )

        self.assertIn("Restart Axis Control Panel", client.topology_error)
        self.assertFalse(client.feedback["process_data_valid"])

    def test_full_status_preserves_feedback_health(self):
        client = AxisServerClient("127.0.0.1", 15000, axis_count=1)
        client.feedback["server_health"] = {"runtime_state": "normal"}
        client.feedback["process_data_valid"] = True

        client._store_feedback(
            {"type": "system/axes/status", "actual_positions": [3.0]}
        )

        self.assertEqual(client.feedback["server_health"]["runtime_state"], "normal")
        self.assertTrue(client.feedback["process_data_valid"])

    def test_axis_diagnostic_status_is_stored_per_axis(self):
        feedback = initial_feedback(2)
        status = {
            "level": "fault",
            "statuses": [{"definition": {"code": "AXIS_DRIVE_FAULT"}}],
        }

        self.assertTrue(
            merge_axis_status(
                feedback,
                {"axis": 1, "diagnostic_status": status},
                2,
            )
        )
        self.assertIsNone(feedback["axis_diagnostic_statuses"][0])
        self.assertEqual(feedback["axis_diagnostic_statuses"][1], status)

    def test_axis_error_prefers_diagnostic_and_keeps_drive_detail(self):
        formatter = DiagnosisMixin()
        diagnostic_status = {
            "level": "fault",
            "statuses": [
                {
                    "definition": {
                        "level": "fault",
                        "code": "AXIS_DRIVE_FAULT",
                        "title": "Axis drive fault",
                        "description": "The drive reports a fault.",
                    }
                }
            ],
        }

        text = formatter._format_axis_error(
            diagnostic_status,
            {"error_code_text": "CMMT 0x1234"},
        )

        self.assertIn("FAULT AXIS_DRIVE_FAULT", text)
        self.assertIn("Drive: CMMT 0x1234", text)


class ServerHealthFeedbackTest(unittest.TestCase):
    @staticmethod
    def connected_feedback_fixture():
        axis_devices = SimpleNamespace(
            position_drive_to_api=lambda _axis, value: float(value),
            motion_drive_to_api=lambda _axis, value, _kind: float(value),
        )
        slave = SimpleNamespace(
            txpdo=SimpleNamespace(
                actual_position=12,
                actual_velocity=3,
                statusword=0x0027,
                mode_of_operation_display=1,
            )
        )
        runtime = SimpleNamespace(
            slaves=[slave],
            device_manager=SimpleNamespace(io=SimpleNamespace(devices=[])),
        )
        session = ServerSession(InitializationStatus.ready(), runtime=runtime)
        state = {
            "server_session": session,
            "initialization_status": session.initialization_status,
            "diagnostic_manager": session.diagnostic_manager,
            "axis_devices": axis_devices,
            "target_positions": [10],
            "command_authority_owner": None,
        }
        return runtime, state

    def test_bus_disconnect_keeps_topology_but_marks_process_data_stale(self):
        runtime, state = self.connected_feedback_fixture()
        normal = system_feedback_message(runtime, state)
        state["server_session"].set_runtime_state(
            ServerRuntimeState.BUS_DISCONNECTED
        )
        disconnected = system_feedback_message(runtime, state)

        self.assertTrue(normal["process_data_valid"])
        self.assertFalse(disconnected["process_data_valid"])
        self.assertEqual(disconnected["actual_positions"], [12.0])
        self.assertEqual(disconnected["target_positions"], [10.0])
        self.assertEqual(
            disconnected["server_health"]["runtime_state"],
            "bus_disconnected",
        )

    def test_degraded_feedback_has_health_and_invalid_empty_process_data(self):
        cause = InitializationCause.BUS_CONNECTION_FAILED
        definition = INITIALIZATION_CAUSE_DEFINITIONS[cause]
        failure = InitializationFailure(
            stage=definition.stage,
            cause=cause,
            message=definition.message,
            occurred_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
        )
        session = ServerSession(InitializationStatus.failed(failure))
        state = {
            "server_session": session,
            "diagnostic_manager": session.diagnostic_manager,
            "initialization_status": session.initialization_status,
            "command_authority_owner": None,
        }

        feedback = system_feedback_message(None, state, client_id=1)

        self.assertFalse(feedback["process_data_valid"])
        self.assertEqual(feedback["actual_positions"], [])
        self.assertEqual(
            feedback["server_health"]["runtime_state"],
            "initialization_error",
        )
        self.assertEqual(
            feedback["server_health"]["initialization_failure"]["cause"],
            "bus_connection_failed",
        )

    def test_axis_and_io_panels_share_health_projection(self):
        feedback = {
            "process_data_valid": False,
            "server_health": {
                "initialized": True,
                "runtime_state": "bus_disconnected",
                "diagnostic_level": "fault",
                "fault_count": 1,
                "alarm_count": 0,
            },
        }

        health = normalize_server_health(feedback)
        text = format_server_health(feedback)

        self.assertEqual(health["runtime_state"], "bus_disconnected")
        self.assertIn("process data stale", text)
        self.assertIn("faults 1", text)


class IoSimulationFeedbackTest(unittest.TestCase):
    def test_panel_filters_simulation_modules_by_input_kind(self):
        panel = object.__new__(IOControlPanel)
        panel.simulation_device_var = SimpleNamespace(get=lambda: "io0")
        simulation = {
            "devices": [{
                "id": "io0",
                "modules": [
                    {"slot": 1, "inputs": {"digital": [False]}},
                    {"slot": 2, "inputs": {"analog": [0]}},
                    {"slot": 3, "inputs": {"io_link": "0000"}},
                ],
            }],
        }

        self.assertEqual(panel.simulation_input_slots(simulation, "digital"), ["1"])
        self.assertEqual(panel.simulation_input_slots(simulation, "analog"), ["2"])
        self.assertEqual(panel.simulation_input_slots(simulation, "io_link"), ["3"])

    def test_simulation_capability_survives_periodic_feedback(self):
        client = MotionServerClient("127.0.0.1", 15000)
        client._store_message({
            "type": "system/simulation/io/input_read",
            "ok": True,
            "available": True,
            "devices": [{"id": "io0", "modules": []}],
        })
        client._store_message({
            "type": "system/feedback",
            "process_data_valid": True,
            "io": {"devices": [{"id": "io0"}]},
            "server_health": {"runtime_state": "normal"},
        })

        self.assertTrue(client.feedback["simulation"]["available"])

    def test_failed_simulation_probe_marks_feature_unavailable(self):
        client = MotionServerClient("127.0.0.1", 15000)
        client._store_message({
            "type": "system/simulation/io/input_read",
            "ok": False,
            "reason": "unsupported_operation",
            "message": "Simulation API is disabled",
        })

        self.assertFalse(client.feedback["simulation"]["available"])


if __name__ == "__main__":
    unittest.main()
