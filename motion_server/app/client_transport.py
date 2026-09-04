import json
import select
import time
from collections.abc import Mapping

from motion_server.api.encoder import (
    ResponseContext,
    fail_response,
    send_client_message,
)
from motion_server.failure import InvalidRequestException, map_exception
from motion_server.handlers.status import system_feedback_message


def service_client(client, runtime, state, dispatch_message):
    conn = client["conn"]
    readable, _, _ = select.select([conn], [], [], 0.0)
    if not readable:
        return True

    try:
        chunk = conn.recv(4096)
    except BlockingIOError:
        return True
    if not chunk:
        return False

    client["buffer"] += chunk.decode("utf-8")
    while "\n" in client["buffer"]:
        line, client["buffer"] = client["buffer"].split("\n", 1)
        if line.strip():
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                _send_invalid_request(client, "malformed_json")
                continue
            if not isinstance(message, Mapping):
                _send_invalid_request(client, "request must be a JSON object")
                continue
            dispatch_message(message, runtime, state, client)

    return True


def _send_invalid_request(client, reason):
    send_client_message(
        client,
        fail_response(
            ResponseContext("invalid_request"),
            map_exception(InvalidRequestException(reason)),
        ),
    )


def flush_client_output(client):
    output_buffer = client.get("output_buffer")
    if not output_buffer:
        return

    try:
        sent = client["conn"].send(output_buffer)
    except BlockingIOError:
        return

    if sent == 0:
        raise ConnectionError("client connection closed while sending")
    del output_buffer[:sent]


def send_feedback_if_due(client, runtime, state, feedback_period):
    now = time.monotonic()
    if now - client["last_feedback_time"] < feedback_period:
        return

    send_client_message(
        client,
        system_feedback_message(runtime, state, client["id"]),
    )
    client["last_feedback_time"] = now


def close_client(client, runtime, state):
    client_id = client["id"]
    if state.get("command_authority_owner") == client_id:
        state["command_authority_owner"] = None
        logger = getattr(runtime, "logger", None)
        if logger is not None:
            logger.status(
                f"Command authority released because client {client_id} disconnected",
            )
    try:
        client["conn"].close()
    except OSError:
        pass
    logger = getattr(runtime, "logger", None)
    if logger is not None:
        logger.status(f"Client disconnected: id={client_id}")


def allocate_client_id(clients):
    next_id = 1
    used_ids = {client["id"] for client in clients}
    while next_id in used_ids:
        next_id += 1
    return next_id
