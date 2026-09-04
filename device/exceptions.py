class DeviceModelException(Exception):
    """Base class for expected device model construction failures."""


class DeviceLayoutInvalidException(DeviceModelException):
    pass


class DeviceIdentityMismatchException(DeviceModelException):
    pass


class PdoCatalogMismatchException(DeviceModelException):
    pass
