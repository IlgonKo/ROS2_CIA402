from dataclasses import dataclass
from datetime import datetime, timezone


SOURCE_TYPES = frozenset({"server", "bus", "axis", "io"})
PARAMETER_DOMAINS = frozenset(
    {
        "ethercat_od",
        "ethercat_od_group",
        "axis_projection",
        "ap_parameter",
        "iol_isdu",
    }
)
READ_ACCESS = "ro"
WRITE_ACCESS = "wo"
READ_WRITE_ACCESS = "rw"
ACCESS_TYPES = frozenset({READ_ACCESS, WRITE_ACCESS, READ_WRITE_ACCESS})


@dataclass(frozen=True)
class RuntimeParameterAddress:
    """Stable runtime address for a device parameter or parameter group."""

    source_type: str
    source_index: int
    domain: str
    index: int | None = None
    subindex: int | None = None
    module: int | None = None
    port: int | None = None
    parameter_id: int | None = None
    instance: int | None = None
    role: str | None = None

    def __post_init__(self):
        source_type = str(self.source_type)
        domain = str(self.domain)
        if source_type not in SOURCE_TYPES:
            raise ValueError(f"Unsupported runtime parameter source: {source_type}")
        if domain not in PARAMETER_DOMAINS:
            raise ValueError(f"Unsupported runtime parameter domain: {domain}")
        if not isinstance(self.source_index, int) or isinstance(
            self.source_index, bool
        ):
            raise TypeError("Runtime parameter source index must be an integer")
        if self.source_index < 0:
            raise ValueError("Runtime parameter source index must not be negative")
        for field in (
            "index",
            "subindex",
            "module",
            "port",
            "parameter_id",
            "instance",
        ):
            value = getattr(self, field)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"Runtime parameter {field} must be a non-negative integer")


@dataclass(frozen=True)
class RuntimeParameterDefinition:
    """Metadata describing why and how Motion Server caches a parameter."""

    key: str
    address: RuntimeParameterAddress
    name: str
    data_type: str
    required: bool = False
    access: str = READ_WRITE_ACCESS
    refresh_on_startup: bool = False
    refresh_on_recovery: bool = False
    used_by: tuple[str, ...] = ()

    def __post_init__(self):
        if not str(self.key).strip():
            raise ValueError("Runtime parameter definition key must not be empty")
        if not isinstance(self.address, RuntimeParameterAddress):
            raise TypeError("Runtime parameter definition address is required")
        if not str(self.name).strip():
            raise ValueError("Runtime parameter definition name must not be empty")
        if not str(self.data_type).strip():
            raise ValueError("Runtime parameter definition data type must not be empty")
        if self.access not in ACCESS_TYPES:
            raise ValueError(f"Unsupported runtime parameter access: {self.access}")


@dataclass(frozen=True)
class RuntimeParameterValue:
    """Cached runtime value plus validity metadata."""

    definition: RuntimeParameterDefinition
    value: object = None
    raw_value: object = None
    valid: bool = True
    updated_at: datetime | None = None
    source: str = "device_readback"
    last_error: str | None = None

    def __post_init__(self):
        if not isinstance(self.definition, RuntimeParameterDefinition):
            raise TypeError("Runtime parameter value definition is required")
        if self.updated_at is not None and not isinstance(self.updated_at, datetime):
            raise TypeError("Runtime parameter updated_at must be datetime")


class RuntimeParameterCache:
    """In-memory cache for runtime device parameters."""

    def __init__(self, *, clock=None):
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._definitions = {}
        self._values = {}

    def register(self, definition):
        if not isinstance(definition, RuntimeParameterDefinition):
            raise TypeError("Runtime parameter definition is required")
        existing = self._definitions.get(definition.key)
        if existing is not None and existing != definition:
            raise ValueError(f"Runtime parameter definition already exists: {definition.key}")
        self._definitions[definition.key] = definition
        return definition

    def ensure(self, definition):
        return self.register(definition)

    def definition(self, key):
        return self._definitions[str(key)]

    def definitions(self, *, source_type=None, source_index=None):
        definitions = tuple(self._definitions.values())
        if source_type is None and source_index is None:
            return definitions
        return tuple(
            definition
            for definition in definitions
            if (source_type is None or definition.address.source_type == source_type)
            and (
                source_index is None
                or definition.address.source_index == int(source_index)
            )
        )

    def update(
        self,
        key,
        value,
        *,
        raw_value=None,
        source="device_readback",
        updated_at=None,
    ):
        definition = self.definition(key)
        cached = RuntimeParameterValue(
            definition=definition,
            value=value,
            raw_value=raw_value,
            valid=True,
            updated_at=updated_at or self._clock(),
            source=str(source),
        )
        self._values[definition.key] = cached
        return cached

    def invalidate(self, key, error, *, value=None, source="readback_failed", updated_at=None):
        definition = self.definition(key)
        previous = self._values.get(definition.key)
        cached = RuntimeParameterValue(
            definition=definition,
            value=previous.value if value is None and previous is not None else value,
            raw_value=None if previous is None else previous.raw_value,
            valid=False,
            updated_at=updated_at or self._clock(),
            source=str(source),
            last_error=str(error),
        )
        self._values[definition.key] = cached
        return cached

    def get(self, key, default=None):
        return self._values.get(str(key), default)

    def values(self, *, source_type=None, source_index=None, valid=None):
        values = tuple(self._values.values())
        if source_type is None and source_index is None and valid is None:
            return values
        return tuple(
            value
            for value in values
            if (source_type is None or value.definition.address.source_type == source_type)
            and (
                source_index is None
                or value.definition.address.source_index == int(source_index)
            )
            and (valid is None or value.valid is bool(valid))
        )

    def snapshot(self, *, source_type=None, source_index=None, valid=None):
        return tuple(
            {
                "key": value.definition.key,
                "name": value.definition.name,
                "address": value.definition.address,
                "data_type": value.definition.data_type,
                "value": value.value,
                "raw_value": value.raw_value,
                "valid": value.valid,
                "updated_at": value.updated_at,
                "source": value.source,
                "last_error": value.last_error,
            }
            for value in self.values(
                source_type=source_type,
                source_index=source_index,
                valid=valid,
            )
        )


def runtime_parameter_key(address):
    if not isinstance(address, RuntimeParameterAddress):
        raise TypeError("Runtime parameter address is required")
    parts = [address.source_type, str(address.source_index), address.domain]
    if address.domain == "iol_isdu":
        if address.module is not None:
            parts.append(f"module{address.module}")
        if address.port is not None:
            parts.append(f"port{address.port}")
        if address.parameter_id is not None:
            parts.append(f"parameter0x{address.parameter_id:04X}")
        if address.subindex is not None:
            parts.append(f"subindex0x{address.subindex:02X}")
    elif address.domain == "ap_parameter":
        if address.module is not None:
            parts.append(f"module{address.module}")
        if address.parameter_id is not None:
            parts.append(f"parameter0x{address.parameter_id:08X}")
        if address.instance is not None:
            parts.append(f"instance{address.instance}")
    else:
        if address.index is not None:
            parts.append(f"0x{address.index:04X}")
        if address.subindex is not None:
            parts.append(f"0x{address.subindex:02X}")
        if address.module is not None:
            parts.append(f"module{address.module}")
        if address.port is not None:
            parts.append(f"port{address.port}")
        if address.parameter_id is not None:
            parts.append(f"parameter0x{address.parameter_id:08X}")
        if address.instance is not None:
            parts.append(f"instance{address.instance}")
    if address.role:
        parts.append(str(address.role))
    return ".".join(parts)


def runtime_parameter_name(address):
    if address.domain in {"ethercat_od", "ethercat_od_group"}:
        if address.index is None:
            return str(address.role or address.domain)
        if address.subindex is None:
            return f"EtherCAT OD 0x{address.index:04X}"
        return f"EtherCAT OD 0x{address.index:04X}:0x{address.subindex:02X}"
    if address.domain == "ap_parameter":
        return (
            f"AP parameter module {address.module} "
            f"id 0x{address.parameter_id:08X} instance {address.instance}"
        )
    if address.domain == "iol_isdu":
        return (
            f"IO-Link ISDU module {address.module} port {address.port} "
            f"index 0x{address.parameter_id:04X}:0x{address.subindex or 0:02X}"
        )
    return str(address.role or address.domain)


def runtime_parameter_definition(
    address,
    *,
    data_type,
    access=READ_WRITE_ACCESS,
    name=None,
    required=False,
    refresh_on_startup=False,
    refresh_on_recovery=False,
    used_by=(),
):
    return RuntimeParameterDefinition(
        key=runtime_parameter_key(address),
        address=address,
        name=name or runtime_parameter_name(address),
        data_type=str(data_type),
        required=bool(required),
        access=access,
        refresh_on_startup=bool(refresh_on_startup),
        refresh_on_recovery=bool(refresh_on_recovery),
        used_by=tuple(used_by),
    )


def update_runtime_parameter_cache(
    runtime,
    address,
    value,
    *,
    data_type,
    access=READ_WRITE_ACCESS,
    raw_value=None,
    source="device_readback",
):
    cache = getattr(runtime, "parameter_cache", None)
    if cache is None:
        return None
    definition = runtime_parameter_definition(
        address,
        data_type=data_type,
        access=access,
    )
    cache.register(definition)
    return cache.update(
        definition.key,
        value,
        raw_value=raw_value,
        source=source,
    )
