import json
from pathlib import Path
import queue
import socket
import sys
import threading
import time
import unittest


PYTHON_REFERENCE_ROOT = Path(__file__).parents[1] / "reference_clients" / "python"
sys.path.insert(0, str(PYTHON_REFERENCE_ROOT))

from motion_server_reference_client import (  # noqa: E402
    ConnectionLostError,
    InvalidClientRequestError,
    MotionServerClient,
    NotConnectedError,
    RequestTimeoutError,
)


class JsonLineServer:
    def __init__(self, handler, *, port=0):
        self.handler = handler
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", port))
        self.listener.listen()
        self.port = self.listener.getsockname()[1]
        self.stop_event = threading.Event()
        self.connections = []
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.stop_event.set()
        try:
            self.listener.close()
        except OSError:
            pass
        for connection in self.connections:
            try:
                connection.close()
            except OSError:
                pass
        self.thread.join(timeout=2.0)

    def run(self):
        self.listener.settimeout(0.1)
        while not self.stop_event.is_set():
            try:
                connection, _address = self.listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            self.connections.append(connection)
            threading.Thread(
                target=self.handle_connection,
                args=(connection,),
                daemon=True,
            ).start()

    def handle_connection(self, connection):
        stream = connection.makefile("rb")
        try:
            for line in stream:
                request = json.loads(line.decode("utf-8"))
                self.handler(connection, request)
        except OSError:
            return
        finally:
            stream.close()


def send_message(connection, message, *, split=None):
    payload = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
    if split is None:
        connection.sendall(payload)
        return
    connection.sendall(payload[:split])
    connection.sendall(payload[split:])


class ReferencePythonClientTest(unittest.TestCase):
    def tearDown(self):
        for resource in getattr(self, "resources", []):
            resource.stop()

    def track(self, resource):
        if not hasattr(self, "resources"):
            self.resources = []
        self.resources.append(resource)
        return resource

    def client(self, server, **kwargs):
        client = self.track(MotionServerClient("127.0.0.1", server.port, **kwargs))
        client.start()
        self.assertTrue(client.wait_connected(2.0))
        return client

    def test_raw_success_and_fail_envelopes_are_correlated(self):
        def handler(connection, request):
            result = "fail" if request["cmd"] == "fail" else "success"
            response = {
                "type": request["cmd"],
                "request_id": request["request_id"],
                "result": result,
            }
            response["failure" if result == "fail" else "data"] = (
                {"code": "TEST_FAILURE", "message": "failed"}
                if result == "fail"
                else {"value": 1}
            )
            send_message(connection, response)

        server = self.track(JsonLineServer(handler).start())
        client = self.client(server)

        success = client.request({"cmd": "status"})
        failure = client.request({"cmd": "fail"})

        self.assertEqual(success["result"], "success")
        self.assertEqual(failure["result"], "fail")
        self.assertRegex(success["request_id"], r"^python-[0-9a-f]{6}-1$")
        self.assertRegex(failure["request_id"], r"^python-[0-9a-f]{6}-2$")

    def test_concurrent_requests_match_out_of_order_responses(self):
        received = []
        lock = threading.Lock()

        def handler(connection, request):
            with lock:
                received.append(request)
                if len(received) != 2:
                    return
                for item in reversed(received):
                    send_message(connection, {
                        "type": item["cmd"],
                        "request_id": item["request_id"],
                        "result": "success",
                        "data": {"value": item["value"]},
                    })

        server = self.track(JsonLineServer(handler).start())
        client = self.client(server)
        results = {}

        threads = [
            threading.Thread(
                target=lambda value=value: results.update({
                    value: client.request({"cmd": "echo", "value": value})
                })
            )
            for value in (1, 2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2.0)

        self.assertEqual(results[1]["data"]["value"], 1)
        self.assertEqual(results[2]["data"]["value"], 2)

    def test_feedback_uses_bounded_oldest_drop_queue_and_split_utf8(self):
        def handler(connection, request):
            for value in range(3):
                message = {
                    "type": "system/feedback",
                    "label": "축",
                    "value": value,
                }
                payload = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
                split = payload.find("축".encode("utf-8")) + 1
                connection.sendall(payload[:split])
                connection.sendall(payload[split:])
            send_message(connection, {
                "type": request["cmd"],
                "request_id": request["request_id"],
                "result": "success",
                "data": {},
            })

        server = self.track(JsonLineServer(handler).start())
        client = self.client(server, feedback_queue_size=2)
        client.request({"cmd": "trigger"})

        self.assertEqual(client.get_feedback(1.0)["value"], 1)
        self.assertEqual(client.get_feedback(1.0)["value"], 2)
        with self.assertRaises(queue.Empty):
            client.get_feedback(0.01)

    def test_timeout_removes_pending_and_late_response_is_ignored(self):
        delayed = threading.Event()

        def handler(connection, request):
            if request["cmd"] == "slow":
                delayed.wait(0.2)
            send_message(connection, {
                "type": request["cmd"],
                "request_id": request["request_id"],
                "result": "success",
                "data": {},
            })

        server = self.track(JsonLineServer(handler).start())
        client = self.client(server, request_timeout=0.03)
        with self.assertRaises(RequestTimeoutError):
            client.request({"cmd": "slow"})
        delayed.set()
        time.sleep(0.05)
        self.assertEqual(
            client.request({"cmd": "next"}, timeout=1.0)["type"],
            "next",
        )
        self.assertTrue(client.is_connected)

    def test_disconnect_fails_pending_clears_feedback_and_reconnects(self):
        calls = 0

        def handler(connection, request):
            nonlocal calls
            calls += 1
            if calls == 1:
                send_message(connection, {"type": "system/feedback", "value": 1})
                connection.shutdown(socket.SHUT_RDWR)
                connection.close()
                return
            send_message(connection, {
                "type": request["cmd"],
                "request_id": request["request_id"],
                "result": "success",
                "data": {},
            })

        server = self.track(JsonLineServer(handler).start())
        client = self.client(server)
        with self.assertRaises(ConnectionLostError):
            client.request({"cmd": "disconnect"})
        self.assertFalse(client.is_connected)
        with self.assertRaises(queue.Empty):
            client.get_feedback(0.01)
        with self.assertRaises(NotConnectedError):
            client.request({"cmd": "not-retried"})
        self.assertTrue(client.wait_connected(2.5))
        response = client.request({"cmd": "after-reconnect"})
        self.assertEqual(response["type"], "after-reconnect")
        self.assertTrue(response["request_id"].endswith("-2"))
        self.assertEqual(calls, 2)

    def test_invalid_requests_are_rejected_without_mutating_message(self):
        client = MotionServerClient("127.0.0.1", 15000)
        self.track(client)
        with self.assertRaises(NotConnectedError):
            client.request({"cmd": "status"})
        with self.assertRaises(InvalidClientRequestError):
            client.request({"cmd": "status", "request_id": "caller"})
        with self.assertRaises(InvalidClientRequestError):
            client.request({"axis": 0})
        with self.assertRaises(InvalidClientRequestError):
            MotionServerClient(
                "127.0.0.1",
                15000,
                feedback_queue_size=1.5,
            )
        message = {"cmd": "status"}
        with self.assertRaises(NotConnectedError):
            client.request(message)
        self.assertEqual(message, {"cmd": "status"})

    def test_non_json_request_fails_without_poisoning_correlation(self):
        def handler(connection, request):
            send_message(connection, {
                "type": request["cmd"],
                "request_id": request["request_id"],
                "result": "success",
                "data": {},
            })

        server = self.track(JsonLineServer(handler).start())
        client = self.client(server)
        with self.assertRaises(InvalidClientRequestError):
            client.request({"cmd": "invalid", "value": object()})
        response = client.request({"cmd": "valid"})
        self.assertEqual(response["type"], "valid")
        self.assertTrue(response["request_id"].endswith("-2"))

    def test_start_retries_until_an_initially_absent_server_appears(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        client = self.track(MotionServerClient("127.0.0.1", port))
        client.start()
        self.assertFalse(client.wait_connected(0.2))

        server = self.track(JsonLineServer(lambda _socket, _request: None, port=port).start())
        self.assertTrue(client.wait_connected(2.5), client.last_error)
        self.assertTrue(client.is_connected)


if __name__ == "__main__":
    unittest.main()
