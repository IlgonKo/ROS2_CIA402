import unittest

import motion_server.failure as failure_api
from motion_server.failure import (
    AuthorityBusyException,
    AuthorityException,
    AuthorityRequiredException,
    CommunicationException,
    CommunicationTimeoutException,
    ConfigurationException,
    DeviceAccessException,
    DeviceException,
    DeviceRejectedException,
    EXCEPTION_FAILURE_MAPPINGS,
    FailureCode,
    InvalidArgumentException,
    InvalidRequestException,
    InvalidStateException,
    ItemFailure,
    LimitViolationException,
    MotionServerException,
    OperationBlockedException,
    OperationConflictException,
    OperationException,
    OperationTimeoutException,
    PartialFailure,
    PermissionDeniedException,
    RequestException,
    ResourceNotFoundException,
    SdoObjectNotFoundException,
    ServerNotReadyException,
    StateException,
    UnknownCommandException,
    UnsupportedOperationException,
    map_exception,
)


EXPECTED_FAILURE_CODES = {
    "INVALID_REQUEST",
    "UNKNOWN_COMMAND",
    "UNSUPPORTED_OPERATION",
    "INVALID_ARGUMENT",
    "RESOURCE_NOT_FOUND",
    "AUTHORITY_REQUIRED",
    "AUTHORITY_BUSY",
    "PERMISSION_DENIED",
    "SERVER_NOT_READY",
    "INVALID_STATE",
    "OPERATION_CONFLICT",
    "OPERATION_BLOCKED",
    "LIMIT_VIOLATION",
    "TIMEOUT",
    "COMMUNICATION_FAILED",
    "DEVICE_ACCESS_FAILED",
    "DEVICE_REJECTED",
    "PARTIAL_FAILURE",
    "OPERATION_FAILED",
    "INTERNAL_FAILURE",
}


EXPECTED_MAPPINGS = {
    ConfigurationException: FailureCode.SERVER_NOT_READY,
    RequestException: FailureCode.INVALID_REQUEST,
    InvalidRequestException: FailureCode.INVALID_REQUEST,
    UnknownCommandException: FailureCode.UNKNOWN_COMMAND,
    UnsupportedOperationException: FailureCode.UNSUPPORTED_OPERATION,
    InvalidArgumentException: FailureCode.INVALID_ARGUMENT,
    ResourceNotFoundException: FailureCode.RESOURCE_NOT_FOUND,
    AuthorityException: FailureCode.PERMISSION_DENIED,
    AuthorityRequiredException: FailureCode.AUTHORITY_REQUIRED,
    AuthorityBusyException: FailureCode.AUTHORITY_BUSY,
    PermissionDeniedException: FailureCode.PERMISSION_DENIED,
    StateException: FailureCode.INVALID_STATE,
    ServerNotReadyException: FailureCode.SERVER_NOT_READY,
    InvalidStateException: FailureCode.INVALID_STATE,
    OperationConflictException: FailureCode.OPERATION_CONFLICT,
    OperationBlockedException: FailureCode.OPERATION_BLOCKED,
    LimitViolationException: FailureCode.LIMIT_VIOLATION,
    CommunicationException: FailureCode.COMMUNICATION_FAILED,
    CommunicationTimeoutException: FailureCode.TIMEOUT,
    DeviceException: FailureCode.DEVICE_ACCESS_FAILED,
    DeviceAccessException: FailureCode.DEVICE_ACCESS_FAILED,
    DeviceRejectedException: FailureCode.DEVICE_REJECTED,
    SdoObjectNotFoundException: FailureCode.RESOURCE_NOT_FOUND,
    OperationException: FailureCode.OPERATION_FAILED,
    OperationTimeoutException: FailureCode.TIMEOUT,
}


class FailureContractTest(unittest.TestCase):
    def test_failure_code_catalog_is_exact(self):
        self.assertEqual({code.value for code in FailureCode}, EXPECTED_FAILURE_CODES)

    def test_all_contract_exception_types_have_expected_mapping(self):
        self.assertEqual(
            {
                exception_type: mapping.code
                for exception_type, mapping in EXCEPTION_FAILURE_MAPPINGS.items()
            },
            EXPECTED_MAPPINGS,
        )

    def test_exact_mapping_wins_over_registered_base_mapping(self):
        result = map_exception(
            CommunicationTimeoutException("sdo_read", timeout_seconds=0.5)
        )

        self.assertEqual(result.code, FailureCode.TIMEOUT)
        self.assertEqual(
            result.details,
            {"operation": "sdo_read", "timeout_seconds": 0.5},
        )

    def test_nearest_registered_base_mapping_supports_new_subclass(self):
        class MailboxCommunicationException(CommunicationException):
            pass

        result = map_exception(MailboxCommunicationException("mailbox"))

        self.assertEqual(result.code, FailureCode.COMMUNICATION_FAILED)
        self.assertEqual(result.details, {"operation": "mailbox"})

    def test_unregistered_exception_uses_safe_internal_failure(self):
        exception = ValueError("secret internal value")
        exception.secret = "must not be exposed"

        result = map_exception(exception)

        self.assertEqual(result.code, FailureCode.INTERNAL_FAILURE)
        self.assertEqual(result.message, "An internal failure occurred.")
        self.assertIsNone(result.details)
        self.assertNotIn("secret", result.message)

    def test_exception_cause_and_unlisted_attributes_are_not_exposed(self):
        try:
            try:
                raise OSError("private adapter path")
            except OSError as cause:
                exception = InvalidArgumentException(
                    "axis",
                    "must be non-negative",
                    public_value=-1,
                )
                exception.private_note = "do not expose"
                raise exception from cause
        except InvalidArgumentException as exception:
            result = map_exception(exception)

        self.assertEqual(result.code, FailureCode.INVALID_ARGUMENT)
        self.assertEqual(
            result.details,
            {
                "field": "axis",
                "reason": "must be non-negative",
                "value": -1,
            },
        )
        self.assertNotIn("private_note", result.details)
        self.assertNotIn("private adapter path", str(result))

    def test_optional_public_detail_is_omitted_when_not_provided(self):
        result = map_exception(
            InvalidArgumentException("axis", "must be an integer")
        )

        self.assertEqual(
            result.details,
            {"field": "axis", "reason": "must be an integer"},
        )

    def test_partial_failure_is_a_result_model_not_an_exception(self):
        item = ItemFailure(
            target={"axis": 1},
            exception=DeviceAccessException("mode_write"),
        )
        result = PartialFailure(succeeded=[{"axis": 0}], failed=[item])

        self.assertNotIsInstance(result, BaseException)
        self.assertEqual(result.succeeded, [{"axis": 0}])
        self.assertEqual(result.failed, [item])

    def test_failure_definition_registry_is_not_public_contract(self):
        self.assertFalse(hasattr(failure_api, "FailureDefinitionRegistry"))
        self.assertFalse(hasattr(failure_api, "FAILURE_DEFINITION_REGISTRY"))


if __name__ == "__main__":
    unittest.main()
