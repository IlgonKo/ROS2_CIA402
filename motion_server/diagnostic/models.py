from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DiagnosticLevel(str, Enum):
    NORMAL = "normal"
    ALARM = "alarm"
    FAULT = "fault"


class DiagnosticSourceType(str, Enum):
    SERVER = "server"
    BUS = "bus"
    AXIS = "axis"
    IO = "io"


@dataclass(frozen=True)
class DiagnosticDefinition:
    code: str
    level: DiagnosticLevel
    title: str
    description: str
    latching: bool

    def __post_init__(self):
        if not str(self.code).strip():
            raise ValueError("Diagnostic definition code must not be empty")
        if not isinstance(self.level, DiagnosticLevel):
            raise TypeError("Diagnostic definition level must be DiagnosticLevel")
        if self.level is DiagnosticLevel.NORMAL:
            raise ValueError("NORMAL does not have a Diagnostic definition")


@dataclass(frozen=True)
class DiagnosticSource:
    type: DiagnosticSourceType
    index: int

    def __post_init__(self):
        if not isinstance(self.type, DiagnosticSourceType):
            raise TypeError("Diagnostic source type must be DiagnosticSourceType")
        if not isinstance(self.index, int) or isinstance(self.index, bool):
            raise TypeError("Diagnostic source index must be an integer")
        if self.index < 0:
            raise ValueError("Diagnostic source index must not be negative")
        if self.type in {
            DiagnosticSourceType.SERVER,
            DiagnosticSourceType.BUS,
        } and self.index != 0:
            raise ValueError("Server and Bus Diagnostic source index must be zero")


@dataclass
class DiagnosticHistory:
    occurred_at: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None


@dataclass
class DiagnosticStatus:
    diagnostic_id: str
    definition: DiagnosticDefinition
    source: DiagnosticSource
    history: DiagnosticHistory
    detail: str | None = None
    context: dict[str, object] | None = None


def cleared_at(status: DiagnosticStatus):
    resolved_at = status.history.resolved_at
    if resolved_at is None:
        return None
    if not status.definition.latching:
        return resolved_at
    acknowledged_at = status.history.acknowledged_at
    if acknowledged_at is None:
        return None
    return max(resolved_at, acknowledged_at)
