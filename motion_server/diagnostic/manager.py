from datetime import datetime, timezone
from uuid import uuid4

from motion_server.diagnostic.models import (
    DiagnosticDefinition,
    DiagnosticHistory,
    DiagnosticLevel,
    DiagnosticSource,
    DiagnosticStatus,
    cleared_at,
)


class DiagnosticManager:
    def __init__(self, *, clock=None, id_factory=None):
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._by_key = {}
        self._by_id = {}
        self._used_ids = set()

    def detect(
        self,
        definition: DiagnosticDefinition,
        source: DiagnosticSource,
        *,
        detail=None,
        context=None,
        at=None,
    ):
        key = self._key(definition.code, source)
        active = self._by_key.get(key)
        if active is not None:
            if active.definition != definition:
                raise ValueError(
                    "An active Diagnostic code cannot change its definition",
                )
            active.history.resolved_at = None
            return active

        status = DiagnosticStatus(
            diagnostic_id=str(self._id_factory()),
            definition=definition,
            source=source,
            history=DiagnosticHistory(occurred_at=at or self._clock()),
            detail=detail,
            context=None if context is None else dict(context),
        )
        if not status.diagnostic_id:
            raise ValueError("Diagnostic ID must not be empty")
        if status.diagnostic_id in self._used_ids:
            raise ValueError("Diagnostic ID must be unique")
        self._used_ids.add(status.diagnostic_id)
        self._by_key[key] = status
        self._by_id[status.diagnostic_id] = status
        return status

    def acknowledge(self, diagnostic_id, *, at=None):
        status = self._required_status(diagnostic_id)
        if status.history.acknowledged_at is None:
            status.history.acknowledged_at = at or self._clock()
        return self._clear_if_ready(status)

    def resolve(self, code, source: DiagnosticSource, *, at=None):
        key = self._key(code, source)
        status = self._by_key.get(key)
        if status is None:
            raise KeyError(key)
        if status.history.resolved_at is None:
            status.history.resolved_at = at or self._clock()
        return self._clear_if_ready(status)

    def status(self, diagnostic_id):
        return self._by_id.get(str(diagnostic_id))

    def active_statuses(self, source=None):
        statuses = tuple(self._by_key.values())
        if source is None:
            return statuses
        return tuple(status for status in statuses if status.source == source)

    def current_level(self, source=None):
        levels = {
            status.definition.level
            for status in self.active_statuses(source)
        }
        if DiagnosticLevel.FAULT in levels:
            return DiagnosticLevel.FAULT
        if DiagnosticLevel.ALARM in levels:
            return DiagnosticLevel.ALARM
        return DiagnosticLevel.NORMAL

    def _required_status(self, diagnostic_id):
        key = str(diagnostic_id)
        status = self._by_id.get(key)
        if status is None:
            raise KeyError(key)
        return status

    def _clear_if_ready(self, status):
        if cleared_at(status) is None:
            return status
        key = self._key(status.definition.code, status.source)
        del self._by_key[key]
        del self._by_id[status.diagnostic_id]
        return status

    @staticmethod
    def _key(code, source):
        return str(code), source.type, int(source.index)
