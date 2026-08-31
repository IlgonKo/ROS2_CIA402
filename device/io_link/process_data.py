"""Decode IO-Link input bytes using immutable, precompiled IODD metadata."""

from dataclasses import dataclass
import math
import struct


@dataclass(frozen=True)
class ProcessDataField:
    subindex: int
    name: str
    datatype: str
    bit_offset: int
    bit_length: int
    unit: str | None = None
    gradient: float = 1.0
    offset: float = 0.0


@dataclass(frozen=True)
class ProcessDataLayout:
    name: str
    bit_length: int
    fields: tuple[ProcessDataField, ...] = ()
    unsupported_reason: str | None = None


def decode_process_data(profile, payload, *, data_valid=True):
    """Return (status, decoded); never perform I/O or alter a port's profile."""
    if profile is None:
        return "not_configured", None
    if not data_valid or len(payload) < profile.input_bytes:
        return "invalid_data", None
    layout = profile.input_layout
    if layout is None or layout.unsupported_reason is not None:
        return "unsupported", None

    # IO-Link is big endian; RecordItem bitOffset is relative to the LSB.
    # Only the selected profile's bytes participate, not module variant padding.
    raw = int.from_bytes(payload[:profile.input_bytes], "big")
    values = []
    status_bits = []
    for field in layout.fields:
        bits = (raw >> field.bit_offset) & ((1 << field.bit_length) - 1)
        if field.datatype == "BooleanT":
            status_bits.append({
                "subindex": field.subindex,
                "bit_offset": field.bit_offset,
                "name": field.name,
                "active": bool(bits),
            })
            continue
        value = bits
        if field.datatype == "IntegerT" and bits & (1 << (field.bit_length - 1)):
            value -= 1 << field.bit_length
        elif field.datatype == "Float32T":
            value = struct.unpack(">f", bits.to_bytes(4, "big"))[0]
        if field.gradient != 1.0 or field.offset != 0.0:
            value = value * field.gradient + field.offset
        if isinstance(value, float) and not math.isfinite(value):
            return "invalid_data", None
        values.append({
            "subindex": field.subindex,
            "name": field.name,
            "value": value,
            "unit": field.unit,
        })
    return "ok", {
        "profile": profile.condition_value,
        "profile_name": layout.name,
        "values": values,
        "status_bits": status_bits,
    }
