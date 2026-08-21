import json
import logging

from motion_server.api.specification import (
    command_spec,
)
from motion_server.config import MOTION_SERVER_COMMAND_LOGS
from motion_server.api.decoder import (
    command_name,
    public_command_name,
)
from motion_server.api.encoder import (
    ResponseContext,
    fail_response,
    partial_fail_response,
    reject_command_message,
    send_client_message,
    success_response,
)
from motion_server.api.validator import validate_command
from motion_server.failure import MotionServerException, PartialFailure, map_exception
from motion_server.failure import Failure, FailureCode


_LOGGER = logging.getLogger(__name__)


def request_response(request, operation, *, logger=None):
    context = ResponseContext.from_request(request)
    try:
        result = operation()
        if isinstance(result, PartialFailure):
            return partial_fail_response(context, result)
        return success_response(context, result)
    except MotionServerException as exception:
        active_logger = logger or _LOGGER
        active_logger.warning(
            "Motion Server request failed: type=%s request_id=%r failure=%s",
            context.response_type,
            context.request_id if context.has_request_id else None,
            type(exception).__name__,
        )
        return fail_response(context, map_exception(exception))
    except Exception as exception:
        active_logger = logger or _LOGGER
        active_logger.exception(
            "Motion Server request failed: type=%s request_id=%r",
            context.response_type,
            context.request_id if context.has_request_id else None,
        )
        return fail_response(context, map_exception(exception))


from motion_server.handlers.authority import (  # noqa: E402
    client_has_command_authority,
    handle_authority,
    reject_command_when_not_initialized,
    reject_command_without_authority,
)
from motion_server.handlers.command.registry import handle_command  # noqa: E402
from motion_server.handlers.status import (  # noqa: E402
    handle_advanced_status_rejection,
    handle_status,
)


def reject_advanced_only_command(client, message, state):
    command = command_name(message)
    send_client_message(
        client,
        {
            "type": "command_rejected",
            "command": command,
            "server_mode": state.get("server_mode"),
            "message": (
                f"{command} is available only in "
                "Motion Server advanced mode."
            ),
        },
    )


class _RequestCaptureConnection:
    # TECH_DEBT[TD-005]: S11 removes this compatibility capture after command
    # handlers return operation data or raise typed Exceptions directly.
    def __init__(self):
        self.messages = []

    def sendall(self, payload):
        for line in payload.decode("utf-8").splitlines():
            if line.strip():
                self.messages.append(json.loads(line))


def route_message(message, runtime, state, client):
    context = ResponseContext.from_request(message)
    capture = _RequestCaptureConnection()
    request_client = dict(client)
    request_client["conn"] = capture

    try:
        _route_message_to_handler(message, runtime, state, request_client)
    except MotionServerException as exception:
        _LOGGER.warning(
            "Motion Server request failed: type=%s request_id=%r failure=%s",
            context.response_type,
            context.request_id if context.has_request_id else None,
            type(exception).__name__,
        )
        request_client["_failure"] = map_exception(exception)
    except Exception as exception:
        _LOGGER.exception(
            "Motion Server request failed: type=%s request_id=%r",
            context.response_type,
            context.request_id if context.has_request_id else None,
        )
        request_client["_failure"] = map_exception(exception)
    response = _live_response(context, request_client, capture.messages)
    send_client_message(client, response)
    return response


def _route_message_to_handler(message, runtime, state, client):
    if MOTION_SERVER_COMMAND_LOGS:
        print(
            "Motion Server received command: "
            f"client={client.get('id')} "
            f"{json.dumps(message, sort_keys=True, ensure_ascii=False)}",
            flush=True,
        )

    raw_message_type = command_name(message)
    message_type = public_command_name(message)
    spec = command_spec(message_type)

    validation_error = validate_command(
        spec,
        client,
        state,
        client_has_command_authority(client, state),
    )
    if validation_error == "unknown":
        client["_failure"] = Failure(
            FailureCode.UNKNOWN_COMMAND,
            "The command is unknown.",
            {"command": raw_message_type},
        )
        if raw_message_type:
            reject_command_message(
                client,
                raw_message_type,
                f"Unknown command: {raw_message_type}",
            )
        return
    if validation_error == "advanced_only":
        client["_failure"] = Failure(
            FailureCode.UNSUPPORTED_OPERATION,
            "The requested operation is not supported.",
            {"operation": message_type, "reason": "advanced_only"},
        )
        if spec and spec.is_status:
            handle_advanced_status_rejection(message_type, runtime, state, client)
        else:
            reject_advanced_only_command(client, message, state)
        return
    if validation_error == "authority_required":
        owner = state.get("command_authority_owner")
        if owner is None:
            client["_failure"] = Failure(
                FailureCode.AUTHORITY_REQUIRED,
                "Command authority is required.",
            )
        else:
            client["_failure"] = Failure(
                FailureCode.AUTHORITY_BUSY,
                "Command authority is held by another client.",
                {"owner": owner},
            )
        reject_command_without_authority(client, message, state)
        return
    if validation_error == "not_initialized":
        client["_failure"] = Failure(
            FailureCode.SERVER_NOT_READY,
            "Motion Server is not ready.",
        )
        reject_command_when_not_initialized(client, message, state)
        return

    if spec.is_authority:
        handle_authority(message_type, client, state)
        return

    if spec.is_status and handle_status(
        message_type,
        message,
        runtime,
        state,
        client,
    ):
        return

    if handle_command(message_type, message, runtime, state, client):
        return

    reject_command_message(
        client,
        raw_message_type,
        f"No handler registered for command: {raw_message_type}",
    )


def _live_response(context, client, captured_messages):
    failure = client.get("_failure")
    result = client.get("_operation_result")
    if isinstance(result, PartialFailure):
        return partial_fail_response(context, result)
    if failure is not None:
        return fail_response(context, failure)
    if len(captured_messages) > 1:
        return fail_response(
            context,
            Failure(
                FailureCode.INTERNAL_FAILURE,
                "An internal failure occurred.",
            ),
        )
    if not captured_messages:
        return success_response(context)

    message = captured_messages[0]
    if message.get("result") in {"success", "fail"}:
        response = dict(message)
        response["type"] = context.response_type
        if context.has_request_id:
            response["request_id"] = context.request_id
        return response
    if _legacy_message_failed(message):
        return fail_response(context, _legacy_failure(message))
    return success_response(context, _legacy_success_data(message))


def _legacy_message_failed(message):
    return message.get("type") == "command_rejected" or message.get("ok") is False


def _legacy_failure(message):
    reason = str(message.get("reason", "")).lower()
    if reason == "authority_required":
        return Failure(FailureCode.AUTHORITY_REQUIRED, "Command authority is required.")
    if reason == "authority_busy":
        details = {"owner": message["owner"]} if message.get("owner") is not None else None
        return Failure(
            FailureCode.AUTHORITY_BUSY,
            "Command authority is held by another client.",
            details,
        )
    return Failure(FailureCode.OPERATION_FAILED, "The operation failed.")


def _legacy_success_data(message):
    data = dict(message)
    data.pop("type", None)
    data.pop("ok", None)
    data.pop("accepted", None)
    if data.get("reason") is None:
        data.pop("reason", None)
    if "device_diagnostics" in data:
        data.pop("diagnostics", None)
    return data


dispatch_message = route_message
