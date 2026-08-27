from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import math
import queue
import secrets
import socket
import threading

from motion_server_reference_client.exceptions import (
    ConnectionLostError,
    InvalidClientRequestError,
    NotConnectedError,
    RequestTimeoutError,
)


RECONNECT_PERIOD = 1.0
CONNECT_TIMEOUT = 5.0
RECEIVE_SIZE = 65536


@dataclass
class _PendingRequest:
    event: threading.Event = field(default_factory=threading.Event)
    response: dict | None = None
    error: Exception | None = None


class MotionServerClient:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        request_timeout: float = 5.0,
        feedback_queue_size: int = 100,
    ):
        self.host = str(host).strip()
        if not self.host:
            raise InvalidClientRequestError("host must not be empty")
        try:
            self.port = int(port)
        except (TypeError, ValueError) as exc:
            raise InvalidClientRequestError("port must be an integer") from exc
        if not 1 <= self.port <= 65535:
            raise InvalidClientRequestError("port must be in 1..65535")
        self.request_timeout = positive_number(request_timeout, "request_timeout")
        if (
            isinstance(feedback_queue_size, bool)
            or not isinstance(feedback_queue_size, int)
            or feedback_queue_size <= 0
        ):
            raise InvalidClientRequestError(
                "feedback_queue_size must be a positive integer"
            )
        self.feedback_queue_size = feedback_queue_size

        self._state_lock = threading.RLock()
        self._send_lock = threading.Lock()
        self._connected_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self._pending: dict[str, _PendingRequest] = {}
        self._feedback: queue.Queue[dict] = queue.Queue(
            maxsize=self.feedback_queue_size
        )
        self._session_prefix = f"python-{secrets.token_hex(3)}"
        self._request_sequence = 0
        self._last_error = ""

    @property
    def is_connected(self) -> bool:
        return self._connected_event.is_set()

    @property
    def last_error(self) -> str:
        with self._state_lock:
            return self._last_error

    def start(self) -> None:
        with self._state_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._connection_loop,
                name="motion-server-reference-client",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._disconnect(ConnectionLostError("Motion Server client stopped"))
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=CONNECT_TIMEOUT + 1.0)

    def wait_connected(self, timeout: float | None = None) -> bool:
        return self._connected_event.wait(timeout)

    def request(self, message: Mapping, *, timeout: float | None = None) -> dict:
        request = validated_request(message)
        timeout_value = self.request_timeout if timeout is None else positive_number(
            timeout,
            "timeout",
        )
        with self._state_lock:
            sock = self._socket
            if sock is None or not self._connected_event.is_set():
                raise NotConnectedError("Motion Server is not connected")
            request_id = self._next_request_id()
            request["request_id"] = request_id
            try:
                payload = (
                    json.dumps(request, separators=(",", ":")) + "\n"
                ).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise InvalidClientRequestError(
                    f"request is not JSON serializable: {exc}"
                ) from exc
            pending = _PendingRequest()
            self._pending[request_id] = pending

        try:
            with self._send_lock:
                sock.sendall(payload)
        except OSError as exc:
            error = ConnectionLostError(f"Motion Server connection lost: {exc}")
            self._disconnect(error)
            raise error from exc

        if not pending.event.wait(timeout_value):
            with self._state_lock:
                if self._pending.get(request_id) is pending:
                    self._pending.pop(request_id, None)
                    raise RequestTimeoutError(
                        f"Motion Server request timed out after {timeout_value:g}s"
                    )
            pending.event.wait()

        if pending.error is not None:
            raise pending.error
        if pending.response is None:
            raise ConnectionLostError("Motion Server request ended without a response")
        return pending.response

    def get_feedback(self, timeout: float | None = None) -> dict:
        return self._feedback.get(timeout=timeout)

    def _next_request_id(self) -> str:
        self._request_sequence += 1
        return f"{self._session_prefix}-{self._request_sequence}"

    def _connection_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._connect()
                self._receive_loop()
            except OSError as exc:
                self._disconnect(
                    ConnectionLostError(f"Motion Server connection lost: {exc}")
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self._disconnect(
                    ConnectionLostError(f"Motion Server protocol error: {exc}")
                )
            finally:
                if self._socket is not None:
                    self._disconnect(ConnectionLostError("Motion Server disconnected"))
            self._stop_event.wait(RECONNECT_PERIOD)

    def _connect(self) -> None:
        sock = socket.create_connection(
            (self.host, self.port),
            timeout=CONNECT_TIMEOUT,
        )
        sock.settimeout(None)
        with self._state_lock:
            if self._stop_event.is_set():
                sock.close()
                return
            self._socket = sock
            self._last_error = ""
            self._connected_event.set()

    def _receive_loop(self) -> None:
        buffer = bytearray()
        while not self._stop_event.is_set():
            with self._state_lock:
                sock = self._socket
            if sock is None:
                return
            chunk = sock.recv(RECEIVE_SIZE)
            if not chunk:
                raise ConnectionResetError("server closed the connection")
            buffer.extend(chunk)
            while True:
                newline = buffer.find(b"\n")
                if newline < 0:
                    break
                line = bytes(buffer[:newline])
                del buffer[:newline + 1]
                if not line.strip():
                    continue
                message = json.loads(line.decode("utf-8"))
                if not isinstance(message, dict):
                    raise ValueError("Motion Server message must be a JSON object")
                self._route_message(message)

    def _route_message(self, message: dict) -> None:
        if message.get("type") == "system/feedback" and "request_id" not in message:
            self._put_latest_feedback(message)
            return
        request_id = message.get("request_id")
        if request_id is None:
            return
        with self._state_lock:
            pending = self._pending.pop(str(request_id), None)
        if pending is None:
            return
        pending.response = message
        pending.event.set()

    def _put_latest_feedback(self, message: dict) -> None:
        while True:
            try:
                self._feedback.put_nowait(message)
                return
            except queue.Full:
                try:
                    self._feedback.get_nowait()
                except queue.Empty:
                    continue

    def _disconnect(self, error: ConnectionLostError) -> None:
        with self._state_lock:
            sock = self._socket
            self._socket = None
            was_connected = self._connected_event.is_set()
            self._connected_event.clear()
            if not self._stop_event.is_set() or was_connected:
                self._last_error = str(error)
            pending = list(self._pending.values())
            self._pending.clear()
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        self._clear_feedback()
        for request in pending:
            request.error = error
            request.event.set()

    def _clear_feedback(self) -> None:
        while True:
            try:
                self._feedback.get_nowait()
            except queue.Empty:
                return


def validated_request(message: Mapping) -> dict:
    if not isinstance(message, Mapping):
        raise InvalidClientRequestError("request must be a mapping")
    request = dict(message)
    command = request.get("cmd")
    if not isinstance(command, str) or not command.strip():
        raise InvalidClientRequestError("request cmd must be a non-empty string")
    if "request_id" in request:
        raise InvalidClientRequestError("request_id is managed by the client")
    return request


def positive_number(value, field: str) -> float:
    if isinstance(value, bool):
        raise InvalidClientRequestError(f"{field} must be > 0")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidClientRequestError(f"{field} must be a number") from exc
    if not math.isfinite(number) or number <= 0:
        raise InvalidClientRequestError(f"{field} must be > 0")
    return number
