import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from motion_server.app.client_transport import service_client
from motion_server.api.router import route_message


class Connection:
    def __init__(self):
        self.messages = []

    def sendall(self, payload):
        self.messages.append(json.loads(payload.decode("utf-8")))


class ReceivingConnection(Connection):
    def __init__(self, payload):
        super().__init__()
        self.payload = payload

    def recv(self, size):
        payload, self.payload = self.payload, b""
        return payload


def client(client_id="client-1"):
    return {"id": client_id, "conn": Connection()}


class LiveEnvelopeCutoverTest(unittest.TestCase):
    def test_status_sends_one_success_envelope_with_request_id(self):
        active_client = client()
        runtime = SimpleNamespace(slaves=[], cycle_time=0.008)

        response = route_message(
            {
                "cmd": "system/server/status",
                "request_id": "status-1",
            },
            runtime,
            {},
            active_client,
        )

        self.assertEqual(active_client["conn"].messages, [response])
        self.assertEqual(response["type"], "system/server/status")
        self.assertEqual(response["result"], "success")
        self.assertEqual(response["request_id"], "status-1")
        self.assertNotIn("ok", response)
        self.assertNotIn("accepted", response)

    def test_unknown_command_sends_stable_fail_envelope(self):
        active_client = client()

        response = route_message(
            {"cmd": "system/unknown"},
            SimpleNamespace(),
            {},
            active_client,
        )

        self.assertEqual(response["result"], "fail")
        self.assertEqual(response["failure"]["code"], "UNKNOWN_COMMAND")
        self.assertEqual(
            response["failure"]["details"],
            {"command": "system/unknown"},
        )
        self.assertNotIn("command_rejected", str(response))

    def test_authority_rejection_uses_request_type_and_failure_code(self):
        active_client = client("client-2")

        response = route_message(
            {"cmd": "system/axis/enable", "axis": 0},
            SimpleNamespace(),
            {"command_authority_owner": "client-1"},
            active_client,
        )

        self.assertEqual(response["type"], "system/axis/enable")
        self.assertEqual(response["failure"]["code"], "AUTHORITY_BUSY")
        self.assertEqual(response["failure"]["details"], {"owner": "client-1"})

    def test_command_without_legacy_payload_gets_empty_success(self):
        active_client = client()
        state = {"command_authority_owner": "client-1"}

        with patch.dict(
            "motion_server.handlers.command.registry.COMMAND_HANDLERS",
            {"system/io/reset": lambda message, runtime, state, client: None},
        ):
            response = route_message(
                {"cmd": "system/io/reset"},
                SimpleNamespace(),
                state,
                active_client,
            )

        self.assertEqual(
            response,
            {
                "type": "system/io/reset",
                "result": "success",
                "data": {},
            },
        )

    def test_authority_status_success_is_enveloped(self):
        active_client = client()

        response = route_message(
            {"cmd": "system/authority/status"},
            SimpleNamespace(),
            {"command_authority_owner": None},
            active_client,
        )

        self.assertEqual(response["result"], "success")
        self.assertTrue(response["data"]["available"])
        self.assertNotIn("ok", response["data"])
        self.assertNotIn("reason", response["data"])

    def test_unexpected_handler_error_is_hidden_in_fail_envelope(self):
        active_client = client()
        state = {"command_authority_owner": "client-1"}

        def fail_handler(message, runtime, state, client):
            raise RuntimeError("private implementation detail")

        with patch.dict(
            "motion_server.handlers.command.registry.COMMAND_HANDLERS",
            {"system/io/reset": fail_handler},
        ), patch("motion_server.api.router._LOGGER"):
            response = route_message(
                {"cmd": "system/io/reset"},
                SimpleNamespace(),
                state,
                active_client,
            )

        self.assertEqual(response["failure"]["code"], "INTERNAL_FAILURE")
        self.assertNotIn("private implementation detail", str(response))

    def test_missing_command_type_is_invalid_request_and_echoes_request_id(self):
        active_client = client()

        response = route_message(
            {"request_id": "missing-type"},
            SimpleNamespace(),
            {},
            active_client,
        )

        self.assertEqual(response["type"], "invalid_request")
        self.assertEqual(response["request_id"], "missing-type")
        self.assertEqual(response["failure"]["code"], "INVALID_REQUEST")

    def test_non_object_request_is_invalid_request(self):
        active_client = client()

        response = route_message([], SimpleNamespace(), {}, active_client)

        self.assertEqual(response["type"], "invalid_request")
        self.assertEqual(response["failure"]["code"], "INVALID_REQUEST")

    def test_malformed_json_returns_fail_without_closing_client(self):
        connection = ReceivingConnection(b'{"cmd": invalid}\n')
        active_client = {
            "id": "client-1",
            "conn": connection,
            "buffer": "",
            "last_feedback_time": 0.0,
        }

        with patch(
            "motion_server.app.client_transport.select.select",
            return_value=([connection], [], []),
        ):
            keep_connection = service_client(
                active_client,
                SimpleNamespace(),
                {},
                route_message,
            )

        self.assertTrue(keep_connection)
        self.assertEqual(connection.messages[0]["type"], "invalid_request")
        self.assertEqual(
            connection.messages[0]["failure"]["code"],
            "INVALID_REQUEST",
        )

    def test_invalid_utf8_returns_fail_without_closing_client(self):
        connection = ReceivingConnection(b"\xff\n")
        active_client = {
            "id": "client-1",
            "conn": connection,
            "buffer": "",
            "last_feedback_time": 0.0,
        }

        with patch(
            "motion_server.app.client_transport.select.select",
            return_value=([connection], [], []),
        ):
            keep_connection = service_client(
                active_client,
                SimpleNamespace(),
                {},
                route_message,
            )

        self.assertTrue(keep_connection)
        self.assertEqual(
            connection.messages[0]["failure"]["code"],
            "INVALID_REQUEST",
        )

    def test_axis_selector_failure_preserves_resource_not_found(self):
        active_client = client()
        state = {
            "command_authority_owner": "client-1",
            "drive_initialized": True,
        }

        response = route_message(
            {"cmd": "system/axis/move_abs", "axis": 3, "position": 1},
            SimpleNamespace(slaves=[]),
            state,
            active_client,
        )

        self.assertEqual(response["failure"]["code"], "RESOURCE_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
