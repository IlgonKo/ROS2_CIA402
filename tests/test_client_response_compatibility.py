import json
import unittest

from control_panel.axis_control_panel.panel_update_data import (
    initial_feedback,
    merge_axis_status,
)
from motion_server.api.encoder import send_legacy_status_response
from motion_server_client import is_fail_response, normalize_response


class Connection:
    def __init__(self):
        self.messages = []

    def sendall(self, payload):
        self.messages.append(json.loads(payload.decode("utf-8")))


class ClientResponseCompatibilityTest(unittest.TestCase):
    def test_legacy_success_remains_readable(self):
        message = normalize_response(
            {"type": "system/io/status", "ok": True, "devices": []},
        )

        self.assertTrue(message["ok"])
        self.assertEqual(message["devices"], [])

    def test_new_success_is_flattened_for_existing_clients(self):
        message = normalize_response(
            {
                "type": "system/axes/status",
                "request_id": "r1",
                "result": "success",
                "data": {"actual_positions": [1.0]},
            },
        )

        self.assertTrue(message["ok"])
        self.assertEqual(message["type"], "system/axes/status")
        self.assertEqual(message["request_id"], "r1")
        self.assertEqual(message["actual_positions"], [1.0])

    def test_new_fail_has_safe_legacy_view_and_authority_details(self):
        message = normalize_response(
            {
                "type": "system/axis/enable",
                "result": "fail",
                "failure": {
                    "code": "AUTHORITY_BUSY",
                    "message": "Command authority is owned by another client.",
                    "details": {"owner": "client-1", "available": False},
                },
            },
        )

        self.assertTrue(is_fail_response(message))
        self.assertFalse(message["ok"])
        self.assertEqual(message["reason"], "authority_busy")
        self.assertEqual(message["failure_code"], "AUTHORITY_BUSY")
        self.assertEqual(message["owner"], "client-1")
        self.assertNotIn("exception", str(message).lower())

    def test_malformed_response_becomes_safe_failure(self):
        message = normalize_response(["not", "an", "object"])

        self.assertTrue(is_fail_response(message))
        self.assertEqual(message["failure_code"], "MALFORMED_RESPONSE")

    def test_legacy_diagnostics_is_read_as_device_diagnostics(self):
        raw = [{"error_code": 7}]

        message = normalize_response(
            {"type": "system/axes/status", "diagnostics": raw},
        )

        self.assertEqual(message["device_diagnostics"], raw)

    def test_axis_panel_stores_canonical_device_diagnostics(self):
        feedback = initial_feedback(1)
        message = normalize_response(
            {
                "type": "system/axis/status",
                "axis": 0,
                "diagnostics": {"error_code": 9},
            },
        )

        self.assertTrue(merge_axis_status(feedback, message, 1))
        self.assertEqual(
            feedback["device_diagnostics"],
            [{"error_code": 9}],
        )
        self.assertNotIn("diagnostics", feedback)

    def test_legacy_server_response_keeps_diagnostics_alias(self):
        connection = Connection()
        client = {"conn": connection}

        send_legacy_status_response(
            client,
            {
                "type": "system/axes/status",
                "result": "success",
                "data": {"device_diagnostics": [{"error_code": 0}]},
            },
            include_ok=False,
        )

        message = connection.messages[0]
        self.assertEqual(message["device_diagnostics"], message["diagnostics"])


if __name__ == "__main__":
    unittest.main()
