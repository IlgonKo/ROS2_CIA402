import unittest

from control_panel.axis_control_panel.panel_update_data import initial_feedback, merge_axis_status
from motion_server_client import decode_server_message, is_fail_message


class ClientResponseContractTest(unittest.TestCase):
    def test_success_envelope_is_decoded(self):
        message = decode_server_message({
            "type": "system/axes/status", "request_id": "r1", "result": "success",
            "data": {"device_diagnostics": [{"error_code": 0}]},
        })
        self.assertTrue(message["ok"])
        self.assertEqual(message["request_id"], "r1")
        self.assertEqual(message["device_diagnostics"], [{"error_code": 0}])

    def test_fail_envelope_is_decoded(self):
        message = decode_server_message({
            "type": "system/axis/enable", "result": "fail",
            "failure": {"code": "AUTHORITY_BUSY", "message": "Busy.", "details": {"owner": "c1"}},
        })
        self.assertTrue(is_fail_message(message))
        self.assertEqual(message["failure_code"], "AUTHORITY_BUSY")
        self.assertEqual(message["owner"], "c1")

    def test_legacy_response_is_rejected(self):
        message = decode_server_message({"type": "system/axes/status", "ok": True})
        self.assertTrue(is_fail_message(message))
        self.assertEqual(message["failure_code"], "MALFORMED_RESPONSE")

    def test_legacy_diagnostics_is_not_mapped(self):
        message = decode_server_message({
            "type": "system/axes/status", "result": "success",
            "data": {"diagnostics": [{"error_code": 7}]},
        })
        self.assertNotIn("device_diagnostics", message)

    def test_notification_remains_outside_envelope(self):
        notification = {"type": "system/feedback", "actual_positions": [1.0]}
        self.assertEqual(decode_server_message(notification), notification)

    def test_axis_panel_uses_canonical_device_diagnostics(self):
        feedback = initial_feedback(1)
        message = decode_server_message({
            "type": "system/axis/status", "result": "success",
            "data": {"axis": 0, "device_diagnostics": {"error_code": 9}},
        })
        self.assertTrue(merge_axis_status(feedback, message, 1))
        self.assertEqual(feedback["device_diagnostics"], [{"error_code": 9}])


if __name__ == "__main__":
    unittest.main()
