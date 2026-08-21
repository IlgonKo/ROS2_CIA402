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
    send_client_message,
    success_response,
)
from motion_server.api.validator import validate_command
from motion_server.failure import (
    AuthorityBusyException,
    AuthorityRequiredException,
    MotionServerException,
    PartialFailure,
    ServerNotReadyException,
    UnknownCommandException,
    UnsupportedOperationException,
    map_exception,
)


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
)
from motion_server.handlers.command.registry import handle_command  # noqa: E402
from motion_server.handlers.status import handle_status  # noqa: E402


def route_message(message, runtime, state, client):
    response = request_response(
        message,
        lambda: _route_message_to_handler(message, runtime, state, client),
    )
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
        raise UnknownCommandException(raw_message_type)
    if validation_error == "advanced_only":
        raise UnsupportedOperationException(message_type, "advanced_only")
    if validation_error == "authority_required":
        owner = state.get("command_authority_owner")
        if owner is None:
            raise AuthorityRequiredException()
        raise AuthorityBusyException(owner)
    if validation_error == "not_initialized":
        raise ServerNotReadyException(state.get("initialization_error"))

    if spec.is_authority:
        return handle_authority(message_type, client, state)

    if spec.is_status:
        return handle_status(message_type, message, runtime, state, client)

    return handle_command(message_type, message, runtime, state, client)


dispatch_message = route_message
