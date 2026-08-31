"""Compile input decoding metadata once, when loading an IODD catalog."""

import math

from device.io_link.process_data import ProcessDataField, ProcessDataLayout


# IO-Link StandardUnitDefinitions1.1 (V1.1.9, 2025-07-03).
# Unknown unit codes deliberately remain null; never infer units from names.
UNIT_SYMBOLS = {1001: "°C", 1062: "mm/s", 1658: "g"}


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _child(element, name):
    if element is not None:
        return next((item for item in element if _local(item.tag) == name), None)
    return None


def _type(element):
    return element.get("{http://www.w3.org/2001/XMLSchema-instance}type", "").split(":")[-1]


class IoddProcessDataCompiler:
    def __init__(self, root):
        self.datatypes = {}
        self.references = {}
        self.texts = {}
        for element in root.iter():
            tag = _local(element.tag)
            if tag == "Datatype" and element.get("id"):
                self.datatypes.setdefault(element.get("id"), []).append(element)
            elif tag == "ProcessDataRef":
                self.references.setdefault(element.get("processDataId"), []).append(element)
            elif tag == "PrimaryLanguage":
                self.texts.update({item.get("id"): item.get("value", "") for item in element})

    def name(self, element, fallback):
        name = _child(element, "Name")
        if name is None:
            return fallback
        text_id = name.get("textId", "")
        return self.texts.get(text_id, text_id) or fallback

    def datatype(self, element):
        inline = _child(element, "Datatype")
        if inline is None:
            inline = _child(element, "SimpleDatatype")
        reference = _child(element, "DatatypeRef")
        if inline is not None and reference is None:
            return inline
        if inline is None and reference is not None:
            matches = self.datatypes.get(reference.get("datatypeId"), ())
            if len(matches) == 1:
                return matches[0]
        raise ValueError("Missing or ambiguous Datatype/DatatypeRef")

    def compile(self, input_element, fallback_name):
        name = self.name(input_element, fallback_name)
        if input_element is None:
            return ProcessDataLayout(name, 0, unsupported_reason="No ProcessDataIn")
        try:
            bits = int(input_element.get("bitLength", "0"))
            if not 1 <= bits <= 256:
                raise ValueError("Unsupported input bit length")
            datatype = self.datatype(input_element)
            refs = self.references.get(input_element.get("id"), ())
            if len(refs) > 1:
                raise ValueError("Ambiguous ProcessDataRef")
            info = {}
            for item in refs[0] if refs else ():
                tag = _local(item.tag)
                if tag not in {"ProcessDataInfo", "ProcessDataRecordItemInfo"}:
                    raise ValueError("Unsupported conversion metadata")
                subindex = int(item.get("subindex", "0"))
                if subindex in info:
                    raise ValueError("Duplicate conversion metadata")
                info[subindex] = item
            fields = []
            if _type(datatype) == "RecordT":
                if int(datatype.get("bitLength", "0")) != bits:
                    raise ValueError("Record and ProcessDataIn lengths differ")
                for item in datatype:
                    if _local(item.tag) != "RecordItem":
                        raise ValueError("Unsupported Record structure")
                    subindex = int(item.get("subindex", "0"))
                    if not 1 <= subindex <= 255:
                        raise ValueError("Invalid record subindex")
                    fields.append(self.field(
                        self.datatype(item), subindex,
                        int(item.get("bitOffset", "-1")),
                        self.name(item, f"subindex_{subindex}"), info.get(subindex),
                    ))
            else:
                fields.append(self.field(datatype, 0, 0, name, info.get(0)))
                if fields[0].bit_length != bits:
                    raise ValueError("Scalar and ProcessDataIn lengths differ")
            used_bits = 0
            subindices = set()
            for field in fields:
                if field.bit_offset < 0 or field.bit_offset + field.bit_length > bits:
                    raise ValueError("Record field exceeds input bounds")
                mask = ((1 << field.bit_length) - 1) << field.bit_offset
                if used_bits & mask or field.subindex in subindices:
                    raise ValueError("Overlapping fields or duplicate subindices")
                used_bits |= mask
                subindices.add(field.subindex)
            if not fields or not set(info).issubset(subindices):
                raise ValueError("Missing field or unmatched conversion metadata")
            return ProcessDataLayout(name, bits, tuple(fields))
        except (ValueError, OverflowError) as exc:
            # Unsupported metadata affects decoding only, never raw access/startup.
            return ProcessDataLayout(name, 0, unsupported_reason=str(exc))

    def field(self, datatype, subindex, bit_offset, name, info):
        kind = _type(datatype)
        if kind == "BooleanT":
            bits = 1
        elif kind == "Float32T":
            bits = 32
        elif kind in {"IntegerT", "UIntegerT"}:
            bits = int(datatype.get("bitLength", "0"))
            if not 1 <= bits <= 64:
                raise ValueError("Unsupported integer width")
        else:
            raise ValueError(f"Unsupported datatype: {kind}")
        attributes = {} if info is None else info.attrib
        gradient = float(attributes.get("gradient", "1"))
        offset = float(attributes.get("offset", "0"))
        if not math.isfinite(gradient) or not math.isfinite(offset):
            raise ValueError("Non-finite conversion metadata")
        if kind == "BooleanT" and (gradient != 1 or offset != 0):
            raise ValueError("Boolean conversion is unsupported")
        unit = UNIT_SYMBOLS.get(int(attributes.get("unitCode", "0")))
        return ProcessDataField(subindex, name, kind, bit_offset, bits, unit, gradient, offset)
