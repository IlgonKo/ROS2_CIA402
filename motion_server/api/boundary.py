import logging

from motion_server.api.response import (
    ResponseContext,
    fail_response,
    success_response,
)
from motion_server.failure import map_exception


_LOGGER = logging.getLogger(__name__)


def request_response(request, operation, *, logger=None):
    context = ResponseContext.from_request(request)
    try:
        return success_response(context, operation())
    except Exception as exception:
        active_logger = logger or _LOGGER
        active_logger.exception(
            "Motion Server request failed: type=%s request_id=%r",
            context.response_type,
            context.request_id if context.has_request_id else None,
        )
        return fail_response(context, map_exception(exception))

