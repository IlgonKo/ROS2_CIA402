from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import xml.etree.ElementTree as ET

from device.cpx_ap_i_ec.file_matching import find_unique_xml_file


ESI_DIR = Path(__file__).resolve().parent / "esi"
CMMT_VARIANT_STEMS = {
    "as": "festo_cmmt_as",
    "st": "festo_cmmt_st",
}


@dataclass(frozen=True)
class CMMTEsiSubItemInfo:
    subindex: int
    name: str
    data_type: str
    bit_size: int
    bit_offset: int
    access: str


@dataclass(frozen=True)
class CMMTEsiObjectInfo:
    index: int
    name: str
    data_type: str
    bit_size: int
    access: str
    subitems: tuple[CMMTEsiSubItemInfo, ...] = ()


@dataclass(frozen=True)
class CMMTEsiPdoEntryInfo:
    index: int
    subindex: int
    bit_length: int
    name: str
    data_type: str

    def mapping_entry(self):
        if self.index == 0:
            return self.bit_length & 0xFF
        return (
            ((self.index & 0xFFFF) << 16)
            | ((self.subindex & 0xFF) << 8)
            | (self.bit_length & 0xFF)
        )


@dataclass(frozen=True)
class CMMTEsiPdoInfo:
    index: int
    name: str
    entries: tuple[CMMTEsiPdoEntryInfo, ...]

    def mapping_entries(self):
        return [entry.mapping_entry() for entry in self.entries]


@dataclass(frozen=True)
class CMMTEsiCatalog:
    variant: str
    path: Path
    type_name: str
    display_name: str
    product_code: int
    revision: int
    root_objects: dict
    objects: dict
    rxpdos: dict
    txpdos: dict

    def object_info(self, index, subindex=0):
        return self.objects[(int(index), int(subindex))]

    def root_object_infos(self):
        return [
            self.root_objects[index]
            for index in sorted(self.root_objects)
        ]

    def rxpdo_mapping_entries(self, pdo_index=0x1600):
        return self.rxpdos[int(pdo_index)].mapping_entries()

    def txpdo_mapping_entries(self, pdo_index=0x1A00):
        return self.txpdos[int(pdo_index)].mapping_entries()


def normalize_cmmt_variant(value):
    key = str(value or "").strip().lower().replace("-", "_")
    if key in {"as", "cmmt_as"}:
        return "as"
    if key in {"st", "cmmt_st"}:
        return "st"
    raise ValueError(
        f"Unsupported CMMT variant {value!r}. Use cmmt_as or cmmt_st."
    )


def cmmt_profile_name_for_variant(value):
    variant = normalize_cmmt_variant(value)
    return f"cmmt_{variant}"


def cmmt_catalog_by_profile_name(profile_name):
    return cmmt_esi_catalog(normalize_cmmt_variant(profile_name))


def cmmt_catalog_by_product_code(product_code):
    product_code = int(product_code)
    for catalog in cmmt_esi_catalogs().values():
        if catalog.product_code == product_code:
            return catalog
    raise KeyError(f"No CMMT ESI catalog for product code {product_code}")


@lru_cache(maxsize=1)
def cmmt_esi_catalogs():
    return {
        variant: parse_cmmt_esi_catalog(variant, find_cmmt_esi_file(variant))
        for variant in CMMT_VARIANT_STEMS
    }


def cmmt_esi_catalog(variant):
    return cmmt_esi_catalogs()[normalize_cmmt_variant(variant)]


def find_cmmt_esi_file(variant):
    return find_unique_xml_file(
        ESI_DIR,
        CMMT_VARIANT_STEMS[normalize_cmmt_variant(variant)],
        "CMMT ESI",
    )


def parse_cmmt_esi_catalog(variant, path):
    root = ET.parse(path).getroot()
    device = find_device(root)
    type_el = device.find("Type")
    type_name = xml_text(type_el)
    data_types = parse_data_types(root)
    root_objects, objects = parse_objects(device, data_types)
    return CMMTEsiCatalog(
        variant=normalize_cmmt_variant(variant),
        path=Path(path),
        type_name=type_name,
        display_name=english_name(device) or type_name,
        product_code=parse_int(type_el.get("ProductCode")),
        revision=parse_int(type_el.get("RevisionNo")),
        root_objects=root_objects,
        objects=objects,
        rxpdos=parse_pdos(device, "RxPdo"),
        txpdos=parse_pdos(device, "TxPdo"),
    )


def find_device(root):
    for device in root.findall(".//Device"):
        type_el = device.find("Type")
        if type_el is not None and type_el.get("ProductCode"):
            return device
    raise ValueError("CMMT ESI does not contain a concrete Device entry")


def parse_data_types(root):
    array_types = parse_array_data_types(root)
    data_types = {}
    for data_type in root.findall(".//DataType"):
        name = xml_text(data_type.find("Name"))
        if not name:
            continue
        bit_size = parse_int(xml_text(data_type.find("BitSize")))
        data_types.setdefault(name, []).append((
            bit_size,
            parse_data_type_subitems(data_type, array_types),
        ))
    return data_types


def parse_array_data_types(root):
    result = {}
    for data_type in root.findall(".//DataType"):
        array_info = data_type.find("ArrayInfo")
        if array_info is None:
            continue
        name = xml_text(data_type.find("Name"))
        elements = parse_int(xml_text(array_info.find("Elements")))
        if not name or elements <= 0:
            continue
        total_bits = parse_int(xml_text(data_type.find("BitSize")))
        result.setdefault(name, (
            xml_text(data_type.find("BaseType")),
            parse_int(xml_text(array_info.find("LBound"))),
            elements,
            total_bits // elements,
        ))
    return result


def parse_data_type_subitems(data_type, array_types):
    result = []
    for subitem in data_type.findall("SubItem"):
        item_type = xml_text(subitem.find("Type"))
        array_type = array_types.get(item_type)
        if array_type is None:
            result.append(CMMTEsiSubItemInfo(
                subindex=parse_int(xml_text(subitem.find("SubIdx"))),
                name=(
                    english_display_name(subitem)
                    or xml_text(subitem.find("Name"))
                ),
                data_type=item_type,
                bit_size=parse_int(xml_text(subitem.find("BitSize"))),
                bit_offset=parse_int(xml_text(subitem.find("BitOffs"))),
                access=access_text(subitem),
            ))
            continue

        base_type, lower_bound, elements, element_bits = array_type
        base_offset = parse_int(xml_text(subitem.find("BitOffs")))
        base_name = english_display_name(subitem) or xml_text(subitem.find("Name"))
        for element_offset in range(elements):
            subindex = lower_bound + element_offset
            result.append(CMMTEsiSubItemInfo(
                subindex=subindex,
                name=f"{base_name} {subindex:03d}",
                data_type=base_type,
                bit_size=element_bits,
                bit_offset=base_offset + element_offset * element_bits,
                access=access_text(subitem),
            ))
    return tuple(result)


def parse_objects(device, data_types):
    root_objects = {}
    objects = {}
    for obj in device.findall(".//Object"):
        index = parse_int(xml_text(obj.find("Index")))
        if index <= 0:
            continue
        data_type = xml_text(obj.find("Type"))
        bit_size = parse_int(xml_text(obj.find("BitSize")))
        subitems = object_subitems(obj, data_type, bit_size, data_types)
        info = CMMTEsiObjectInfo(
            index=index,
            name=xml_text(obj.find("Name")),
            data_type=data_type,
            bit_size=bit_size,
            access=access_text(obj),
            subitems=subitems,
        )
        root_objects[index] = info
        if not subitems:
            objects[(index, 0)] = info
        for subitem in info.subitems:
            objects[(index, subitem.subindex)] = CMMTEsiObjectInfo(
                index=index,
                name=subitem.name,
                data_type=subitem.data_type,
                bit_size=subitem.bit_size,
                access=subitem.access or info.access,
                subitems=(),
            )
    return root_objects, objects


def object_subitems(obj, data_type, bit_size, data_types):
    candidates = data_types.get(data_type, [])
    if not candidates:
        return info_subitems(obj)

    same_size = [
        subitems
        for candidate_bit_size, subitems in candidates
        if int(candidate_bit_size) == int(bit_size)
    ]
    if len(same_size) == 1:
        return same_size[0]

    info_names = [
        xml_text(subitem.find("Name"))
        for subitem in obj.findall("Info/SubItem")
    ]
    for _candidate_bit_size, subitems in candidates:
        if same_subitem_names(info_names, [item.name for item in subitems]):
            return subitems

    if same_size:
        return same_size[0]
    return candidates[0][1]


def info_subitems(obj):
    names = [
        xml_text(subitem.find("Name"))
        for subitem in obj.findall("Info/SubItem")
    ]
    return tuple(
        CMMTEsiSubItemInfo(
            subindex=index,
            name=name,
            data_type="",
            bit_size=0,
            bit_offset=0,
            access="",
        )
        for index, name in enumerate(names)
    )


def same_subitem_names(left, right):
    left = [normalize_name(name) for name in left if normalize_name(name)]
    right = [normalize_name(name) for name in right if normalize_name(name)]
    return bool(left) and left == right


def normalize_name(value):
    return " ".join(str(value or "").strip().lower().split())


def parse_pdos(device, tag):
    pdos = {}
    for pdo in device.findall(tag):
        index = parse_int(xml_text(pdo.find("Index")))
        if index <= 0:
            continue
        pdos[index] = CMMTEsiPdoInfo(
            index=index,
            name=xml_text(pdo.find("Name")),
            entries=tuple(parse_pdo_entry(entry) for entry in pdo.findall("Entry")),
        )
    return pdos


def parse_pdo_entry(entry):
    return CMMTEsiPdoEntryInfo(
        index=parse_int(xml_text(entry.find("Index"))),
        subindex=parse_int(xml_text(entry.find("SubIndex"))),
        bit_length=parse_int(xml_text(entry.find("BitLen"))),
        name=xml_text(entry.find("Name")),
        data_type=xml_text(entry.find("DataType")),
    )


def english_name(element):
    for name_el in element.findall("Name"):
        if name_el.get("LcId") == "1033":
            return xml_text(name_el)
    return xml_text(element.find("Name"))


def english_display_name(element):
    for name_el in element.findall("DisplayName"):
        if name_el.get("LcId") == "1033":
            return xml_text(name_el)
    return ""


def parse_int(value):
    value = str(value or "").strip()
    if not value:
        return 0
    if value.lower().startswith("#x"):
        return int(value[2:], 16)
    return int(value, 0)


def access_text(element):
    return xml_text(element.find("Flags/Access")).strip().lower()


def xml_text(element):
    if element is None:
        return ""
    return "".join(element.itertext()).strip()
