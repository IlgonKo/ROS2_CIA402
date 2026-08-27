class MotionServerClientError(Exception):
    """Base class for failures created by the reference client itself."""


class NotConnectedError(MotionServerClientError):
    """Raised when a request is made without a live server connection."""


class ConnectionLostError(MotionServerClientError):
    """Raised when a pending request loses its TCP connection."""


class RequestTimeoutError(MotionServerClientError):
    """Raised when a correlated response does not arrive before its timeout."""


class InvalidClientRequestError(MotionServerClientError):
    """Raised when the caller violates the reference-client request contract."""
