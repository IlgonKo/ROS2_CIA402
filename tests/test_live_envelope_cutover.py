import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from motion_server.api.router import route_message


class Connection:
    def __init__(self):
        self.messages = []

    def sendall(self, payload):
        self.messages.append(json.loads(payload.decode("utf-8")))


def client(client_id="client-1"):
    return {"id": client_id, "conn": Connection()}


def runtime(**values):
    logger = SimpleNamespace(
        config=SimpleNamespace(command=SimpleNamespace(enabled=False)),
        status=lambda message: None,
        command=lambda message: None,
    )
    return SimpleNamespace(logger=logger, **values)


class LiveEnvelopeCutoverTest(unittest.TestCase):
    def test_status_sends_one_success_envelope_with_request_id(self):
        active_client = client()
        runtime_value = runtime(slaves=[], cycle_time=0.008)

        response = route_message(
            {
                "cmd": "system/server/status",
                "request_id": "status-1",
            },
            runtime_value,
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
            runtime(),
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
            runtime(),
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
                runtime(),
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
            runtime(),
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
                runtime(),
                state,
                active_client,
            )

        self.assertEqual(response["failure"]["code"], "INTERNAL_FAILURE")
        self.assertNotIn("private implementation detail", str(response))


if __name__ == "__main__":
    unittest.main()
