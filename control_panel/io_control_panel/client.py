"""Persistent TCP client used by the IO Control Panel."""

import json
import socket
import threading
import time


RECONNECT_PERIOD = 1.0


class MotionServerClient:
    def __init__(self, host, port, timeout=3.0):
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self.sock = None
        self.stream = None
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.stop_event = threading.Event()
        self.connected = False
        self.last_error = ""
        self.feedback = {}
        self.responses = []
        self.thread = threading.Thread(target=self._connection_loop, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.close()

    def close(self):
        with self.lock:
            if self.stream is not None:
                try:
                    self.stream.close()
                except OSError:
                    pass
                self.stream = None
            if self.sock is not None:
                try:
                    self.sock.close()
                except OSError:
                    pass
                self.sock = None
            self.connected = False
            self.condition.notify_all()

    def _connection_loop(self):
        while not self.stop_event.is_set():
            try:
                self._connect()
                self.send_json({"cmd": "system/io/status"})
                self._read_loop()
            except Exception as exc:
                with self.lock:
                    self.last_error = str(exc)
            finally:
                self.close()
            time.sleep(RECONNECT_PERIOD)

    def _connect(self):
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.settimeout(None)
        stream = sock.makefile("r", encoding="utf-8", newline="\n")
        with self.lock:
            self.sock = sock
            self.stream = stream
            self.connected = True
            self.last_error = ""
            self.condition.notify_all()

    def _read_loop(self):
        while not self.stop_event.is_set():
            line = self.stream.readline()
            if not line:
                raise ConnectionError("Motion Server closed the connection")
            message = json.loads(line)
            self._store_message(message)

    def _store_message(self, message):
        with self.lock:
            message_type = message.get("type")
            if message_type == "system/feedback":
                io_feedback = message.get("io", {})
                if io_feedback:
                    self.feedback = {
                        "type": "system/io/status",
                        "ok": True,
                        "devices": list(io_feedback.get("devices", [])),
                    }
            elif message_type in {
                "system/io/status",
                "system/io/input_read",
                "system/io/output_write",
                "system/io/param_read",
                "system/io/param_write",
                "system/authority/request",
                "system/authority/release",
                "system/authority/status",
                "command_rejected",
            }:
                self.responses.append(message)
                if message_type in {"system/io/status", "system/io/input_read"}:
                    self.feedback = dict(message)
                elif message_type == "system/io/output_write":
                    self.feedback = {
                        "type": "system/io/status",
                        "ok": True,
                        "devices": [dict(message)],
                    }
            self.condition.notify_all()

    def request(self, message, expected_type=None, timeout=None):
        expected_type = expected_type or message.get("cmd")
        self.send_json(message)
        return self.wait_for(expected_type, timeout=timeout)

    def command_with_authority(self, message, expected_type=None, timeout=None):
        expected_type = expected_type or message.get("cmd")
        authority = self.request(
            {"cmd": "system/authority/request"},
            expected_type="system/authority/request",
            timeout=timeout,
        )
        if not authority.get("granted", False):
            return authority
        try:
            self.send_json(message)
            return self.wait_for(expected_type, timeout=timeout)
        finally:
            self.send_json({"cmd": "system/authority/release"})

    def send_json(self, message):
        payload = (json.dumps(message) + "\n").encode("utf-8")
        with self.lock:
            if self.sock is None:
                raise ConnectionError("Motion Server is not connected")
            self.sock.sendall(payload)

    def wait_for(self, expected_type, timeout=None):
        deadline = time.monotonic() + float(timeout or self.timeout)
        with self.condition:
            while True:
                for index, response in enumerate(self.responses):
                    if response.get("type") in {expected_type, "command_rejected"}:
                        return self.responses.pop(index)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Timed out waiting for {expected_type}")
                self.condition.wait(remaining)

    def get_snapshot(self):
        with self.lock:
            return self.connected, self.last_error, dict(self.feedback)
