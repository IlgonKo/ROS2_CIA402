_MISSING = object()


class MotionServerException(Exception):
    """Base class for expected Motion Server failures."""


class ConfigurationException(MotionServerException):
    def __init__(self, setting, reason):
        self.setting = str(setting)
        self.reason = str(reason)
        super().__init__(f"{self.setting}: {self.reason}")


class RequestException(MotionServerException):
    pass


class InvalidRequestException(RequestException):
    def __init__(self, reason):
        self.reason = str(reason)
        super().__init__(self.reason)


class UnknownCommandException(RequestException):
    def __init__(self, command):
        self.command = str(command)
        super().__init__(self.command)


class UnsupportedOperationException(RequestException):
    def __init__(self, operation, reason=None):
        self.operation = str(operation)
        self.reason = None if reason is None else str(reason)
        super().__init__(self.operation if self.reason is None else self.reason)


class InvalidArgumentException(RequestException):
    def __init__(self, field, reason, *, public_value=_MISSING):
        self.field = str(field)
        self.reason = str(reason)
        if public_value is not _MISSING:
            self.public_value = public_value
        super().__init__(f"{self.field}: {self.reason}")


class ResourceNotFoundException(RequestException):
    def __init__(self, resource_type, resource_id):
        self.resource_type = str(resource_type)
        self.resource_id = resource_id
        super().__init__(f"{self.resource_type} not found: {self.resource_id}")


class AuthorityException(MotionServerException):
    pass


class AuthorityRequiredException(AuthorityException):
    pass


class AuthorityBusyException(AuthorityException):
    def __init__(self, owner=None):
        self.owner = owner
        super().__init__("Command authority is busy")


class PermissionDeniedException(AuthorityException):
    def __init__(self, operation=None):
        self.operation = None if operation is None else str(operation)
        super().__init__("Permission denied")


class StateException(MotionServerException):
    pass


class ServerNotReadyException(StateException):
    def __init__(self, reason=None):
        self.reason = None if reason is None else str(reason)
        super().__init__("Motion Server is not ready")


class InvalidStateException(StateException):
    def __init__(self, operation=None, state=None):
        self.operation = None if operation is None else str(operation)
        self.state = None if state is None else str(state)
        super().__init__("Operation is not valid in the current state")


class OperationConflictException(StateException):
    def __init__(self, operation=None, active_operation=None):
        self.operation = None if operation is None else str(operation)
        self.active_operation = (
            None if active_operation is None else str(active_operation)
        )
        super().__init__("Operation conflicts with an active operation")


class OperationBlockedException(StateException):
    def __init__(self, operation=None, diagnostic_ids=()):
        self.operation = None if operation is None else str(operation)
        self.diagnostic_ids = tuple(str(item) for item in diagnostic_ids)
        super().__init__("Operation is blocked")


class LimitViolationException(StateException):
    def __init__(self, field, value, *, minimum=None, maximum=None):
        self.field = str(field)
        self.value = value
        self.minimum = minimum
        self.maximum = maximum
        super().__init__(f"{self.field} violates its configured limit")


class CommunicationException(MotionServerException):
    def __init__(self, operation=None):
        self.operation = None if operation is None else str(operation)
        super().__init__("Communication failed")


class CommunicationTimeoutException(CommunicationException):
    def __init__(self, operation=None, timeout_seconds=None):
        self.timeout_seconds = timeout_seconds
        super().__init__(operation)


class DeviceException(MotionServerException):
    def __init__(self, operation=None):
        self.operation = None if operation is None else str(operation)
        super().__init__("Device operation failed")


class DeviceAccessException(DeviceException):
    pass


class DeviceRejectedException(DeviceException):
    def __init__(self, operation=None, device_code=None):
        self.device_code = device_code
        super().__init__(operation)


class SdoObjectNotFoundException(DeviceException):
    def __init__(self, index, subindex=0):
        self.index = int(index)
        self.subindex = int(subindex)
        super().__init__("sdo_access")


class OperationException(MotionServerException):
    def __init__(self, operation=None):
        self.operation = None if operation is None else str(operation)
        super().__init__("Operation failed")


class OperationTimeoutException(OperationException):
    def __init__(self, operation=None, timeout_seconds=None):
        self.timeout_seconds = timeout_seconds
        super().__init__(operation)
