from dataclasses import dataclass

from motion_server.failure.codes import FailureCode
from motion_server.failure.exceptions import (
    AuthorityBusyException,
    AuthorityException,
    AuthorityRequiredException,
    CommunicationException,
    CommunicationTimeoutException,
    ConfigurationException,
    DeviceAccessException,
    DeviceException,
    DeviceRejectedException,
    InvalidArgumentException,
    InvalidRequestException,
    InvalidStateException,
    LimitViolationException,
    OperationBlockedException,
    OperationConflictException,
    OperationException,
    OperationTimeoutException,
    PermissionDeniedException,
    RequestException,
    ResourceNotFoundException,
    SdoObjectNotFoundException,
    ServerNotReadyException,
    StateException,
    UnknownCommandException,
    UnsupportedOperationException,
)
from motion_server.failure.models import Failure


@dataclass(frozen=True)
class ExceptionFailureMapping:
    code: FailureCode
    default_message: str
    detail_fields: tuple[tuple[str, str], ...] = ()


EXCEPTION_FAILURE_MAPPINGS = {
    ConfigurationException: ExceptionFailureMapping(
        FailureCode.SERVER_NOT_READY,
        "Motion Server configuration is invalid.",
    ),
    RequestException: ExceptionFailureMapping(
        FailureCode.INVALID_REQUEST,
        "The request is invalid.",
    ),
    InvalidRequestException: ExceptionFailureMapping(
        FailureCode.INVALID_REQUEST,
        "The request is invalid.",
        (("reason", "reason"),),
    ),
    UnknownCommandException: ExceptionFailureMapping(
        FailureCode.UNKNOWN_COMMAND,
        "The command is unknown.",
        (("command", "command"),),
    ),
    UnsupportedOperationException: ExceptionFailureMapping(
        FailureCode.UNSUPPORTED_OPERATION,
        "The requested operation is not supported.",
        (("operation", "operation"), ("reason", "reason")),
    ),
    InvalidArgumentException: ExceptionFailureMapping(
        FailureCode.INVALID_ARGUMENT,
        "One or more request arguments are invalid.",
        (
            ("field", "field"),
            ("reason", "reason"),
            ("value", "public_value"),
        ),
    ),
    ResourceNotFoundException: ExceptionFailureMapping(
        FailureCode.RESOURCE_NOT_FOUND,
        "The requested resource does not exist.",
        (("resource_type", "resource_type"), ("resource_id", "resource_id")),
    ),
    AuthorityException: ExceptionFailureMapping(
        FailureCode.PERMISSION_DENIED,
        "The operation is not permitted.",
    ),
    AuthorityRequiredException: ExceptionFailureMapping(
        FailureCode.AUTHORITY_REQUIRED,
        "Command authority is required.",
    ),
    AuthorityBusyException: ExceptionFailureMapping(
        FailureCode.AUTHORITY_BUSY,
        "Command authority is held by another client.",
        (("owner", "owner"),),
    ),
    PermissionDeniedException: ExceptionFailureMapping(
        FailureCode.PERMISSION_DENIED,
        "The operation is not permitted.",
        (("operation", "operation"),),
    ),
    StateException: ExceptionFailureMapping(
        FailureCode.INVALID_STATE,
        "The operation is not valid in the current state.",
    ),
    ServerNotReadyException: ExceptionFailureMapping(
        FailureCode.SERVER_NOT_READY,
        "Motion Server is not ready.",
    ),
    InvalidStateException: ExceptionFailureMapping(
        FailureCode.INVALID_STATE,
        "The operation is not valid in the current state.",
        (("operation", "operation"), ("state", "state")),
    ),
    OperationConflictException: ExceptionFailureMapping(
        FailureCode.OPERATION_CONFLICT,
        "The operation conflicts with an active operation.",
        (
            ("operation", "operation"),
            ("active_operation", "active_operation"),
        ),
    ),
    OperationBlockedException: ExceptionFailureMapping(
        FailureCode.OPERATION_BLOCKED,
        "The operation is blocked.",
        (("operation", "operation"), ("diagnostic_ids", "diagnostic_ids")),
    ),
    LimitViolationException: ExceptionFailureMapping(
        FailureCode.LIMIT_VIOLATION,
        "A configured limit would be violated.",
        (
            ("field", "field"),
            ("value", "value"),
            ("minimum", "minimum"),
            ("maximum", "maximum"),
        ),
    ),
    CommunicationException: ExceptionFailureMapping(
        FailureCode.COMMUNICATION_FAILED,
        "Communication failed.",
        (("operation", "operation"),),
    ),
    CommunicationTimeoutException: ExceptionFailureMapping(
        FailureCode.TIMEOUT,
        "Communication timed out.",
        (("operation", "operation"), ("timeout_seconds", "timeout_seconds")),
    ),
    DeviceException: ExceptionFailureMapping(
        FailureCode.DEVICE_ACCESS_FAILED,
        "The device operation failed.",
        (("operation", "operation"),),
    ),
    DeviceAccessException: ExceptionFailureMapping(
        FailureCode.DEVICE_ACCESS_FAILED,
        "Device access failed.",
        (("operation", "operation"),),
    ),
    DeviceRejectedException: ExceptionFailureMapping(
        FailureCode.DEVICE_REJECTED,
        "The device rejected the request.",
        (
            ("operation", "operation"),
            ("device_code", "device_code"),
            ("isdu_step", "isdu_step"),
            ("sdo_index", "sdo_index"),
            ("sdo_subindex", "sdo_subindex"),
            ("sdo_value", "sdo_value"),
        ),
    ),
    SdoObjectNotFoundException: ExceptionFailureMapping(
        FailureCode.RESOURCE_NOT_FOUND,
        "The requested SDO object does not exist.",
        (("index", "index"), ("subindex", "subindex")),
    ),
    OperationException: ExceptionFailureMapping(
        FailureCode.OPERATION_FAILED,
        "The operation failed.",
        (("operation", "operation"),),
    ),
    OperationTimeoutException: ExceptionFailureMapping(
        FailureCode.TIMEOUT,
        "The operation timed out.",
        (("operation", "operation"), ("timeout_seconds", "timeout_seconds")),
    ),
}


_INTERNAL_FAILURE_MAPPING = ExceptionFailureMapping(
    FailureCode.INTERNAL_FAILURE,
    "An internal failure occurred.",
)


def map_exception(exception):
    mapping = _nearest_mapping(type(exception))
    if mapping is None:
        mapping = _INTERNAL_FAILURE_MAPPING
    details = _public_details(exception, mapping)
    return Failure(mapping.code, mapping.default_message, details)


def _nearest_mapping(exception_type):
    for candidate in exception_type.__mro__:
        mapping = EXCEPTION_FAILURE_MAPPINGS.get(candidate)
        if mapping is not None:
            return mapping
    return None


def _public_details(exception, mapping):
    details = {}
    for public_name, attribute_name in mapping.detail_fields:
        if not hasattr(exception, attribute_name):
            continue
        value = getattr(exception, attribute_name)
        if value is not None:
            details[public_name] = value
    return details or None
