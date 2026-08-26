import json
import socket
import threading
import time
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from motion_server.api.router import route_message
from motion_server.app.initialization import (
    INITIALIZATION_CAUSE_DEFINITIONS,
    InitializationCause,
    InitializationFailure,
    InitializationStatus,
)
from motion_server.app.session import ServerRuntimeState, ServerSession
from motion_server.app.state import initial_degraded_state
from motion_server.diagnostic.startup import detect_initialization_fault
from motion_server.server import (
    ServerRestartRequested,
    restart_current_process,
    run_configuration_degraded_once,
)


OCCURRED_AT = datetime(2026, 8, 25, 5, 0, tzinfo=timezone.utc)


class ProcessRestartTest(unittest.TestCase):
    @patch("motion_server.server.subprocess.Popen")
    def test_windows_restart_preserves_arguments_with_spaces(self, popen):
        arguments = [
            r"C:\project\motion_server\__main__.py",
            "--bus",
            "0: axis:cmmt-as,1: axis:cmmt-st",
            "--port",
            "15000",
        ]
        with patch("motion_server.server.os.name", "nt"), patch(
            "motion_server.server.sys.executable", r"C:\Python\python.exe"
        ), patch("motion_server.server.sys.argv", arguments):
            with self.assertRaises(SystemExit) as raised:
                restart_current_process()

        self.assertEqual(raised.exception.code, 0)
        popen.assert_called_once_with(
            [r"C:\Python\python.exe", *arguments],
            close_fds=True,
        )

    @patch("motion_server.server.os.execv")
    def test_posix_restart_replaces_current_python_process(self, execv):
        arguments = ["/project/motion_server/__main__.py", "--port", "15000"]
        with patch("motion_server.server.os.name", "posix"), patch(
            "motion_server.server.sys.executable", "/usr/bin/python3"
        ), patch("motion_server.server.sys.argv", arguments):
            restart_current_process()

        execv.assert_called_once_with(
            "/usr/bin/python3",
            ["/usr/bin/python3", *arguments],
        )


class Connection:
    def __init__(self):
        self.messages = []

    def sendall(self, payload):
        self.messages.append(json.loads(payload.decode("utf-8")))


def failed_session(cause):
    definition = INITIALIZATION_CAUSE_DEFINITIONS[cause]
    failure = InitializationFailure(
        stage=definition.stage,
        cause=cause,
        message=definition.message,
        occurred_at=OCCURRED_AT,
    )
    session = ServerSession(InitializationStatus.failed(failure))
    detect_initialization_fault(session, at=OCCURRED_AT)
    return session


class DegradedApiContractTest(unittest.TestCase):
    def route(self, state, message, client=None):
        client = client or {"id": 1, "conn": Connection()}
        return route_message(message, None, state, client)

    def test_server_and_bus_status_need_no_runtime(self):
        session = failed_session(InitializationCause.BUS_CONNECTION_FAILED)
        state = initial_degraded_state(session)
        server_response = self.route(state, {"cmd": "system/server/status"})
        bus_response = self.route(state, {"cmd": "system/bus/status"})

        server_data = server_response["data"]
        self.assertFalse(server_data["initialized"])
        self.assertEqual(server_data["runtime_state"], "initialization_error")
        self.assertEqual(
            server_data["initialization_failure"]["cause"],
            "bus_connection_failed",
        )
        self.assertNotIn("drive_initialized", server_data)
        self.assertNotIn("initialization_error", server_data)
        self.assertNotIn("axis_count", server_data)
        self.assertEqual(
            server_data["diagnostic_status"]["statuses"][0]["definition"]["code"],
            "SERVER_INITIALIZATION_FAILED",
        )

        bus_data = bus_response["data"]
        self.assertFalse(bus_data["available"])
        self.assertFalse(bus_data["connected"])
        self.assertEqual(bus_data["runtime_state"], "initialization_error")
        for field in (
            "device_count",
            "axis_count",
            "wkc",
            "expected_wkc",
            "wkc_ok",
        ):
            self.assertIsNone(bus_data[field])

    def test_authority_and_matching_recovery_work_without_runtime(self):
        session = failed_session(InitializationCause.BUS_CONNECTION_FAILED)
        state = initial_degraded_state(session)
        state["bus_reconnect_operation"] = lambda: {
            "connected": True,
            "message": "EtherCAT Bus reconnect completed.",
        }
        client = {"id": 7, "conn": Connection()}

        authority = self.route(
            state,
            {"cmd": "system/authority/request"},
            client,
        )
        reconnect = self.route(
            state,
            {"cmd": "system/bus/reconnect"},
            client,
        )

        self.assertEqual(authority["result"], "success")
        self.assertEqual(reconnect["result"], "success")

    def test_device_api_and_bus_rescan_are_not_available(self):
        session = failed_session(InitializationCause.BUS_CONNECTION_FAILED)
        state = initial_degraded_state(session)

        axis = self.route(state, {"cmd": "system/axes/status"})
        rescan = self.route(state, {"cmd": "system/bus/rescan"})

        self.assertEqual(axis["failure"]["code"], "SERVER_NOT_READY")
        self.assertEqual(rescan["failure"]["code"], "SERVER_NOT_READY")

        state["command_authority_owner"] = 1
        rescan = self.route(state, {"cmd": "system/bus/rescan"})
        self.assertEqual(rescan["failure"]["code"], "SERVER_NOT_READY")

    def test_recovery_narrower_than_failure_scope_is_invalid_state(self):
        session = failed_session(InitializationCause.CONFIGURATION_INVALID)
        state = initial_degraded_state(session)
        state["command_authority_owner"] = 1

        reconnect = self.route(state, {"cmd": "system/bus/reconnect"})
        restart = self.route(state, {"cmd": "system/server/restart"})

        self.assertEqual(reconnect["failure"]["code"], "INVALID_STATE")
        self.assertEqual(restart["result"], "success")


class ServerSessionTest(unittest.TestCase):
    def test_runtime_receives_session_manager_and_can_be_detached(self):
        session = failed_session(InitializationCause.RUNTIME_CREATION_FAILED)
        runtime = SimpleNamespace(diagnostic_manager=None)

        session.attach_runtime(runtime)
        detached = session.detach_runtime()

        self.assertIs(runtime.diagnostic_manager, session.diagnostic_manager)
        self.assertIs(detached, runtime)
        self.assertIsNone(session.runtime)

    def test_runtime_state_is_typed_and_requires_runtime_when_connected(self):
        session = failed_session(InitializationCause.RUNTIME_CREATION_FAILED)
        self.assertIs(
            session.runtime_state,
            ServerRuntimeState.INITIALIZATION_ERROR,
        )
        with self.assertRaises(RuntimeError):
            session.set_runtime_state(ServerRuntimeState.BUS_DISCONNECTED)

        runtime = SimpleNamespace(diagnostic_manager=None)
        session.attach_runtime(runtime)
        session.mark_ready()
        session.set_runtime_state(ServerRuntimeState.FAULT)
        self.assertIs(session.runtime_state, ServerRuntimeState.FAULT)

        with self.assertRaises(TypeError):
            session.set_runtime_state("normal")


class ConfigurationDegradedListenerTest(unittest.TestCase):
    @staticmethod
    def read_type(stream, expected_type):
        for _ in range(20):
            message = json.loads(stream.readline().decode("utf-8"))
            if message.get("type") == expected_type:
                return message
        raise AssertionError(f"No {expected_type} response received")

    def test_listener_serves_status_and_restart_without_runtime(self):
        session = failed_session(InitializationCause.CONFIGURATION_INVALID)
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        result = []

        def run_server():
            try:
                run_configuration_degraded_once(
                    session,
                    SimpleNamespace(port=port),
                )
            except ServerRestartRequested:
                result.append("restart")

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        for _ in range(50):
            try:
                client.connect(("127.0.0.1", port))
                break
            except ConnectionRefusedError:
                time.sleep(0.01)
        else:
            self.fail("degraded listener did not start")

        stream = client.makefile("rwb")
        stream.write(b'{"cmd":"system/server/status"}\n')
        stream.flush()
        status = self.read_type(stream, "system/server/status")
        stream.write(b'{"cmd":"system/authority/request"}\n')
        stream.flush()
        authority = self.read_type(stream, "system/authority/request")
        stream.write(b'{"cmd":"system/server/restart"}\n')
        stream.flush()
        restart = self.read_type(stream, "system/server/restart")
        client.close()
        thread.join(timeout=2.0)

        self.assertEqual(status["result"], "success")
        self.assertEqual(authority["result"], "success")
        self.assertEqual(restart["result"], "success")
        self.assertEqual(result, ["restart"])


if __name__ == "__main__":
    unittest.main()
