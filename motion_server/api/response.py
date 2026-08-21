from dataclasses import dataclass
from typing import Mapping

from motion_server.failure import Failure


@dataclass(frozen=True)
class ResponseContext:
    response_type: str
    request_id: object | None = None
    has_request_id: bool = False

    @classmethod
    def from_request(cls, request: Mapping[str, object]):
        response_type = str(
            request.get("cmd", request.get("type", "")),
        ).strip()
        if not response_type:
            raise ValueError("request requires cmd or type")
        return cls(
            response_type=response_type,
            request_id=request.get("request_id"),
            has_request_id="request_id" in request,
        )


def success_response(context, data=None):
    response = {
        "type": context.response_type,
        "result": "success",
        "data": {} if data is None else data,
    }
    _add_request_id(response, context)
    return response


def fail_response(context, failure):
    response = {
        "type": context.response_type,
        "result": "fail",
        "failure": failure_value(failure),
    }
    _add_request_id(response, context)
    return response


def failure_value(failure: Failure):
    value = {
        "code": failure.code.value,
        "message": failure.message,
    }
    if failure.details is not None:
        value["details"] = failure.details
    return value


def _add_request_id(response, context):
    if context.has_request_id:
        response["request_id"] = context.request_id
