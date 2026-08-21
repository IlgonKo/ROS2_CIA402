import unittest
from pathlib import Path
from unittest.mock import Mock

from motion_server.api import (
    ResponseContext,
    fail_response,
    success_response,
)
from motion_server.api.router import request_response
from motion_server.failure import (
    Failure,
    FailureCode,
    ResourceNotFoundException,
)


class ApiResponseContractTests(unittest.TestCase):
    def test_success_contains_data_only(self):
        response = success_response(
            ResponseContext("system/status"),
            {"ready": True},
        )

        self.assertEqual(
            response,
            {
                "type": "system/status",
                "result": "success",
                "data": {"ready": True},
            },
        )
        self.assertNotIn("failure", response)

    def test_empty_success_has_empty_data_object(self):
        response = success_response(ResponseContext("axis/stop"))

        self.assertEqual(response["data"], {})

    def test_fail_contains_failure_only_and_omits_absent_details(self):
        response = fail_response(
            ResponseContext("axis/stop"),
            Failure(FailureCode.INVALID_STATE, "Invalid state."),
        )

        self.assertEqual(
            response,
            {
                "type": "axis/stop",
                "result": "fail",
                "failure": {
                    "code": "INVALID_STATE",
                    "message": "Invalid state.",
                },
            },
        )
        self.assertNotIn("data", response)

    def test_fail_includes_allowlisted_details(self):
        response = fail_response(
            ResponseContext("axis/status"),
            Failure(
                FailureCode.RESOURCE_NOT_FOUND,
                "Axis not found.",
                {"axis": 9},
            ),
        )

        self.assertEqual(response["failure"]["details"], {"axis": 9})

    def test_request_id_is_echoed_only_when_present(self):
        present = ResponseContext.from_request({
            "type": "system/status",
            "request_id": None,
        })
        absent = ResponseContext.from_request({"type": "system/status"})

        self.assertIn("request_id", success_response(present))
        self.assertIsNone(success_response(present)["request_id"])
        self.assertNotIn("request_id", success_response(absent))

    def test_legacy_cmd_is_adapted_to_response_type(self):
        context = ResponseContext.from_request({"cmd": "axis/stop"})

        self.assertEqual(context.response_type, "axis/stop")

    def test_request_without_command_type_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "requires cmd or type"):
            ResponseContext.from_request({"request_id": "r-1"})

    def test_internal_response_helper_is_not_public_contract(self):
        import motion_server.api as api

        self.assertFalse(hasattr(api, "_add_request_id"))

    def test_response_contract_uses_existing_api_modules(self):
        import motion_server.api as api
        import motion_server.api.encoder as encoder
        import motion_server.api.router as router

        self.assertIs(ResponseContext, encoder.ResponseContext)
        self.assertIs(request_response, router.request_response)
        self.assertFalse(hasattr(api, "request_response"))
        api_directory = Path(encoder.__file__).parent
        self.assertFalse((api_directory / "response.py").exists())
        self.assertFalse((api_directory / "boundary.py").exists())


class RequestBoundaryTests(unittest.TestCase):
    def test_operation_result_becomes_success(self):
        response = request_response(
            {"type": "system/status", "request_id": "r-1"},
            lambda: {"ready": True},
        )

        self.assertEqual(response["result"], "success")
        self.assertEqual(response["request_id"], "r-1")
        self.assertEqual(response["data"], {"ready": True})

    def test_expected_exception_becomes_mapped_fail(self):
        logger = Mock()

        def operation():
            raise ResourceNotFoundException("axis", 3)

        response = request_response(
            {"type": "axis/status"},
            operation,
            logger=logger,
        )

        self.assertEqual(response["result"], "fail")
        self.assertEqual(
            response["failure"],
            {
                "code": "RESOURCE_NOT_FOUND",
                "message": "The requested resource does not exist.",
                "details": {"resource_type": "axis", "resource_id": 3},
            },
        )
        logger.warning.assert_called_once()
        logger.exception.assert_not_called()

    def test_unexpected_exception_is_logged_and_hidden(self):
        logger = Mock()

        def operation():
            raise RuntimeError("secret internal state")

        response = request_response(
            {"type": "system/status"},
            operation,
            logger=logger,
        )

        self.assertEqual(
            response["failure"],
            {
                "code": "INTERNAL_FAILURE",
                "message": "An internal failure occurred.",
            },
        )
        self.assertNotIn("secret", str(response))
        logger.exception.assert_called_once()

    def test_transport_send_is_outside_request_boundary(self):
        response = request_response(
            {"type": "system/status"},
            lambda: {"ready": True},
        )
        connection = Mock()
        connection.sendall.side_effect = OSError("disconnected")

        with self.assertRaises(OSError):
            connection.sendall((str(response) + "\n").encode())


if __name__ == "__main__":
    unittest.main()
