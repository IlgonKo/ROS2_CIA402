from datetime import timezone

from motion_server.diagnostic.models import (
    DiagnosticLevel,
    DiagnosticSourceType,
)


def diagnostic_status_snapshot(runtime, *, source=None, source_type=None):
    manager = getattr(runtime, "diagnostic_manager", None)
    if manager is None:
        return {
            "level": DiagnosticLevel.NORMAL.value,
            "statuses": [],
        }

    statuses = manager.active_statuses(source)
    if source_type is not None:
        source_type = DiagnosticSourceType(source_type)
        statuses = tuple(
            status
            for status in statuses
            if status.source.type is source_type
        )

    statuses = tuple(sorted(statuses, key=_status_sort_key))
    return {
        "level": _current_level(statuses).value,
        "statuses": [diagnostic_status_data(status) for status in statuses],
    }


def diagnostic_status_data(status):
    history = status.history
    data = {
        "diagnostic_id": status.diagnostic_id,
        "definition": {
            "code": status.definition.code,
            "level": status.definition.level.value,
            "title": status.definition.title,
            "description": status.definition.description,
            "latching": status.definition.latching,
        },
        "source": {
            "type": status.source.type.value,
            "index": status.source.index,
        },
        "history": {
            "occurred_at": _timestamp(history.occurred_at),
            "acknowledged_at": _timestamp(history.acknowledged_at),
            "resolved_at": _timestamp(history.resolved_at),
        },
    }
    return data


def _timestamp(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat()
    utc_value = value.astimezone(timezone.utc)
    return utc_value.isoformat().replace("+00:00", "Z")


def _current_level(statuses):
    levels = {status.definition.level for status in statuses}
    if DiagnosticLevel.FAULT in levels:
        return DiagnosticLevel.FAULT
    if DiagnosticLevel.ALARM in levels:
        return DiagnosticLevel.ALARM
    return DiagnosticLevel.NORMAL


def _status_sort_key(status):
    level_order = {
        DiagnosticLevel.FAULT: 0,
        DiagnosticLevel.ALARM: 1,
    }
    return (
        level_order[status.definition.level],
        status.source.type.value,
        status.source.index,
        status.definition.code,
        status.diagnostic_id,
    )
