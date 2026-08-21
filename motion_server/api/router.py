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


def route_message(message, runtime, state, client):
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
        if raw_message_type:
            reject_command_message(
                client,
                raw_message_type,
                f"Unknown command: {raw_message_type}",
            )
        return
    if validation_error == "advanced_only":
        if spec and spec.is_status:
            handle_advanced_status_rejection(message_type, runtime, state, client)
        else:
            reject_advanced_only_command(client, message, state)
        return
    if validation_error == "authority_required":
        reject_command_without_authority(client, message, state)
        return
    if validation_error == "not_initialized":
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


dispatch_message = route_message
