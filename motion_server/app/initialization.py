from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, IntEnum
import traceback

from device.exceptions import DeviceModelException
from motion_server.failure import ConfigurationException


class InitializationStage(str, Enum):
    CONFIGURATION = "configuration"
    DEVICE_MODEL_BUILD = "device_model_build"
    RUNTIME_CREATION = "runtime_creation"
    BUS_CONNECTION = "bus_connection"
    DEVICE_INITIALIZATION = "device_initialization"


class InitializationCause(str, Enum):
    CONFIGURATION_INVALID = "configuration_invalid"
    CONFIGURATION_FAILED = "configuration_failed"
    DEVICE_PROFILE_INVALID = "device_profile_invalid"
    DEVICE_LAYOUT_INVALID = "device_layout_invalid"
    PDO_CATALOG_MISMATCH = "pdo_catalog_mismatch"
    DEVICE_MODEL_BUILD_FAILED = "device_model_build_failed"
    RUNTIME_CREATION_FAILED = "runtime_creation_failed"
    BUS_CONNECTION_FAILED = "bus_connection_failed"
    REQUIRED_PARAMETER_READ_FAILED = "required_parameter_read_failed"
    DEVICE_INITIALIZATION_FAILED = "device_initialization_failed"


class InitializationException(Exception):
    """Carries a stable cause from a specific initialization check."""

    def __init__(self, cause):
        if not isinstance(cause, InitializationCause):
            raise TypeError("Initialization exception cause is invalid")
        self.cause = cause
        super().__init__(cause.value)


@dataclass(frozen=True)
class InitializationCauseDefinition:
    stage: InitializationStage
    message: str

    def __post_init__(self):
        if not isinstance(self.stage, InitializationStage):
            raise TypeError("Initialization cause stage must be InitializationStage")
        if not str(self.message).strip():
            raise ValueError("Initialization cause message must not be empty")


INITIALIZATION_CAUSE_DEFINITIONS = {
    InitializationCause.CONFIGURATION_INVALID: InitializationCauseDefinition(
        stage=InitializationStage.CONFIGURATION,
        message="Motion Server configuration is invalid.",
    ),
    InitializationCause.CONFIGURATION_FAILED: InitializationCauseDefinition(
        stage=InitializationStage.CONFIGURATION,
        message="Failed to build Motion Server configuration.",
    ),
    InitializationCause.DEVICE_PROFILE_INVALID: InitializationCauseDefinition(
        stage=InitializationStage.DEVICE_MODEL_BUILD,
        message="A configured device profile is invalid.",
    ),
    InitializationCause.DEVICE_LAYOUT_INVALID: InitializationCauseDefinition(
        stage=InitializationStage.DEVICE_MODEL_BUILD,
        message="The configured device layout is invalid.",
    ),
    InitializationCause.PDO_CATALOG_MISMATCH: InitializationCauseDefinition(
        stage=InitializationStage.DEVICE_MODEL_BUILD,
        message=(
            "Configured device layout does not match the device PDO catalog."
        ),
    ),
    InitializationCause.DEVICE_MODEL_BUILD_FAILED: (
        InitializationCauseDefinition(
            stage=InitializationStage.DEVICE_MODEL_BUILD,
            message="Failed to build the configured device model.",
        )
    ),
    InitializationCause.RUNTIME_CREATION_FAILED: InitializationCauseDefinition(
        stage=InitializationStage.RUNTIME_CREATION,
        message="Failed to create the Motion Server runtime.",
    ),
    InitializationCause.BUS_CONNECTION_FAILED: InitializationCauseDefinition(
        stage=InitializationStage.BUS_CONNECTION,
        message="Failed to connect to the configured EtherCAT bus.",
    ),
    InitializationCause.REQUIRED_PARAMETER_READ_FAILED: (
        InitializationCauseDefinition(
            stage=InitializationStage.DEVICE_INITIALIZATION,
            message="Failed to read a required device parameter.",
        )
    ),
    InitializationCause.DEVICE_INITIALIZATION_FAILED: (
        InitializationCauseDefinition(
            stage=InitializationStage.DEVICE_INITIALIZATION,
            message="Failed to initialize the configured devices.",
        )
    ),
}


@dataclass(frozen=True)
class InitializationFailure:
    stage: InitializationStage
    cause: InitializationCause
    message: str
    occurred_at: datetime

    def __post_init__(self):
        if not isinstance(self.stage, InitializationStage):
            raise TypeError("Initialization failure stage must be InitializationStage")
        if not isinstance(self.cause, InitializationCause):
            raise TypeError("Initialization failure cause must be InitializationCause")
        if not str(self.message).strip():
            raise ValueError("Initialization failure message must not be empty")
        if not isinstance(self.occurred_at, datetime):
            raise TypeError("Initialization failure occurred_at must be datetime")
        definition = INITIALIZATION_CAUSE_DEFINITIONS[self.cause]
        if definition.stage is not self.stage:
            raise ValueError(
                "Initialization failure stage does not match cause definition"
            )
        if self.message != definition.message:
            raise ValueError(
                "Initialization failure message does not match cause definition"
            )


@dataclass(frozen=True)
class InitializationStatus:
    initialized: bool
    failure: InitializationFailure | None

    def __post_init__(self):
        if not isinstance(self.initialized, bool):
            raise TypeError("Initialization status initialized must be boolean")
        if self.initialized and self.failure is not None:
            raise ValueError("Initialized status must not contain a failure")
        if not self.initialized and not isinstance(
            self.failure, InitializationFailure
        ):
            raise ValueError("Failed initialization status requires a failure")

    @classmethod
    def ready(cls):
        return cls(initialized=True, failure=None)

    @classmethod
    def failed(cls, failure):
        return cls(initialized=False, failure=failure)


class InitializationRecoveryScope(IntEnum):
    BUS_RECONNECT = 1
    SERVER_RESTART = 2


INITIALIZATION_RECOVERY_SCOPE = {
    InitializationStage.CONFIGURATION: (
        InitializationRecoveryScope.SERVER_RESTART
    ),
    InitializationStage.DEVICE_MODEL_BUILD: (
        InitializationRecoveryScope.SERVER_RESTART
    ),
    InitializationStage.RUNTIME_CREATION: (
        InitializationRecoveryScope.SERVER_RESTART
    ),
    InitializationStage.BUS_CONNECTION: (
        InitializationRecoveryScope.BUS_RECONNECT
    ),
    InitializationStage.DEVICE_INITIALIZATION: (
        InitializationRecoveryScope.BUS_RECONNECT
    ),
}


def recovery_action_allowed(stage, requested_scope):
    if not isinstance(stage, InitializationStage):
        raise TypeError("Recovery stage must be InitializationStage")
    if not isinstance(requested_scope, InitializationRecoveryScope):
        raise TypeError("Requested recovery scope must be InitializationRecoveryScope")
    return requested_scope >= INITIALIZATION_RECOVERY_SCOPE[stage]


def initialization_cause_from_exception(stage, exception):
    if not isinstance(stage, InitializationStage):
        raise TypeError("Initialization stage must be InitializationStage")
    if not isinstance(exception, Exception):
        raise TypeError("Initialization source error must be Exception")

    if isinstance(exception, InitializationException):
        definition = INITIALIZATION_CAUSE_DEFINITIONS[exception.cause]
        if definition.stage is not stage:
            raise RuntimeError(
                "Initialization exception cause does not match current stage"
            )
        return exception.cause

    if stage is InitializationStage.CONFIGURATION:
        if isinstance(
            exception,
            (ConfigurationException, ValueError, TypeError, OverflowError),
        ):
            return InitializationCause.CONFIGURATION_INVALID
        return InitializationCause.CONFIGURATION_FAILED

    if stage is InitializationStage.DEVICE_MODEL_BUILD:
        if isinstance(exception, (ValueError, TypeError, OverflowError)):
            return InitializationCause.DEVICE_PROFILE_INVALID
        return InitializationCause.DEVICE_MODEL_BUILD_FAILED

    defaults = {
        InitializationStage.RUNTIME_CREATION: (
            InitializationCause.RUNTIME_CREATION_FAILED
        ),
        InitializationStage.BUS_CONNECTION: (
            InitializationCause.BUS_CONNECTION_FAILED
        ),
        InitializationStage.DEVICE_INITIALIZATION: (
            InitializationCause.DEVICE_INITIALIZATION_FAILED
        ),
    }
    return defaults[stage]


def initialization_failure_from_exception(stage, exception, *, occurred_at):
    cause = initialization_cause_from_exception(stage, exception)
    definition = INITIALIZATION_CAUSE_DEFINITIONS[cause]
    return InitializationFailure(
        stage=stage,
        cause=cause,
        message=definition.message,
        occurred_at=occurred_at,
    )


def initialization_failure_data(failure):
    if failure is None:
        return None
    if not isinstance(failure, InitializationFailure):
        raise TypeError("Initialization failure value is invalid")
    occurred_at = failure.occurred_at
    if occurred_at.tzinfo is not None:
        occurred_at = occurred_at.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    else:
        occurred_at = occurred_at.isoformat()
    return {
        "stage": failure.stage.value,
        "cause": failure.cause.value,
        "message": failure.message,
        "occurred_at": occurred_at,
    }


def log_initialization_failure(failure, exception):
    if not isinstance(failure, InitializationFailure):
        raise TypeError("Initialization log requires InitializationFailure")
    if not isinstance(exception, Exception):
        raise TypeError("Initialization log requires source Exception")
    print(
        "Motion Server initialization failed: "
        f"stage={failure.stage.value} cause={failure.cause.value} "
        f"message={failure.message}",
        flush=True,
    )
    if should_log_initialization_detail(exception):
        print(f"Initialization failure detail:\n{exception}", flush=True)
    elif should_log_initialization_traceback(exception):
        traceback.print_exception(exception)


def should_log_initialization_detail(exception):
    if not isinstance(exception, Exception):
        raise TypeError("Initialization log policy requires source Exception")
    detailed_expected_exceptions = (
        InitializationException,
        ConfigurationException,
        DeviceModelException,
        ValueError,
        TypeError,
        OverflowError,
    )
    return isinstance(exception, detailed_expected_exceptions) and bool(
        str(exception).strip()
    )


def should_log_initialization_traceback(exception):
    if not isinstance(exception, Exception):
        raise TypeError("Initialization log policy requires source Exception")
    expected_exceptions = (
        InitializationException,
        ConfigurationException,
        DeviceModelException,
        ValueError,
        TypeError,
        OverflowError,
    )
    return not isinstance(exception, expected_exceptions)


def validate_initialization_catalog():
    missing_causes = set(InitializationCause) - set(
        INITIALIZATION_CAUSE_DEFINITIONS
    )
    extra_causes = set(INITIALIZATION_CAUSE_DEFINITIONS) - set(
        InitializationCause
    )
    if missing_causes or extra_causes:
        raise ValueError(
            "Initialization cause definition catalog mismatch: "
            f"missing={sorted(item.value for item in missing_causes)} "
            f"extra={sorted(str(item) for item in extra_causes)}"
        )

    missing_stages = set(InitializationStage) - set(
        INITIALIZATION_RECOVERY_SCOPE
    )
    extra_stages = set(INITIALIZATION_RECOVERY_SCOPE) - set(
        InitializationStage
    )
    if missing_stages or extra_stages:
        raise ValueError(
            "Initialization recovery scope catalog mismatch: "
            f"missing={sorted(item.value for item in missing_stages)} "
            f"extra={sorted(str(item) for item in extra_stages)}"
        )

    for cause, definition in INITIALIZATION_CAUSE_DEFINITIONS.items():
        if not isinstance(cause, InitializationCause):
            raise TypeError("Initialization cause definition key is invalid")
        if not isinstance(definition, InitializationCauseDefinition):
            raise TypeError("Initialization cause definition value is invalid")

    for stage, scope in INITIALIZATION_RECOVERY_SCOPE.items():
        if not isinstance(stage, InitializationStage):
            raise TypeError("Initialization recovery stage is invalid")
        if not isinstance(scope, InitializationRecoveryScope):
            raise TypeError("Initialization recovery scope is invalid")

    return True


validate_initialization_catalog()
