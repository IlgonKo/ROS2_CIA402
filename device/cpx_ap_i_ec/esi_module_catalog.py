from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import xml.etree.ElementTree as ET

from device.cpx_ap_i_ec.file_matching import (
    find_unique_xml_file,
    normalized_file_key,
)


ESI_DIR = Path(__file__).resolve().parent / "esi"
DEFAULT_ESI_STEM = "festo_cpx_ap_i_ec"


@dataclass(frozen=True)
class EsiModuleInfo:
    ident: int
    type_name: str
    display_name: str
    rxpdo_bytes: int
    txpdo_bytes: int
    has_isdu_access: bool = False
    objects: tuple = ()


@dataclass(frozen=True)
class EsiObjectInfo:
    index: int
    name: str
    data_type: str
    bit_size: int
    access: str
    depend_on_slot: bool = False
    subitems: tuple = ()


@dataclass(frozen=True)
class EsiSubItemInfo:
    subindex: int
    name: str
    data_type: str
    bit_size: int
    bit_offset: int
    access: str


def module_info_by_name(name):
    key = normalized_lookup_key(name)
    try:
        return esi_module_catalog().by_name[key]
    except KeyError as exc:
        raise KeyError(f"CPX AP module not found in ESI: {name!r}") from exc


def module_info_by_ident(ident):
    ident = int(ident)
    try:
        return esi_module_catalog().by_ident[ident]
    except KeyError as exc:
        raise KeyError(f"CPX AP module ident not found in ESI: 0x{ident:08X}") from exc


def interface_module_info():
    return module_info_by_name("CPX-AP-I-EC-M12")


@lru_cache(maxsize=1)
def esi_module_catalog():
    esi_path = find_esi_file(DEFAULT_ESI_STEM)
    modules = parse_esi_modules(esi_path)
    by_name = {}
    by_ident = {}
    for module in modules:
        by_ident.setdefault(module.ident, module)
        by_name.setdefault(normalized_lookup_key(module.type_name), module)
        by_name.setdefault(normalized_lookup_key(module.display_name), module)
    return EsiCatalog(esi_path, tuple(modules), by_name, by_ident)


@dataclass(frozen=True)
class EsiCatalog:
    path: Path
    modules: tuple[EsiModuleInfo, ...]
    by_name: dict
    by_ident: dict


def find_esi_file(stem):
    return find_unique_xml_file(ESI_DIR, stem, "CPX-AP-I-EC ESI")


def parse_esi_modules(path):
    root = ET.parse(path).getroot()
    data_types = parse_data_types(root)
    modules = []
    for module in root.findall(".//Module"):
        type_el = module.find("Type")
        if type_el is None:
            continue
        ident_text = type_el.get("ModuleIdent")
        if not ident_text:
            continue
        type_name = xml_text(type_el)
        if not type_name.startswith("CPX-AP-I-"):
            continue
        modules.append(EsiModuleInfo(
            ident=parse_int(ident_text),
            type_name=type_name,
            display_name=english_name(module) or type_name,
            rxpdo_bytes=module_pdo_bytes(module, "RxPdo"),
            txpdo_bytes=module_pdo_bytes(module, "TxPdo"),
            has_isdu_access=module_has_isdu_access(module),
            objects=parse_module_objects(module, data_types),
        ))
    return modules


def parse_data_types(root):
    data_types = {}
    for data_type in root.findall(".//DataType"):
        name = xml_text(data_type.find("Name"))
        if not name:
            continue
        bit_size = parse_int(xml_text(data_type.find("BitSize")))
        key = (name, bit_size)
        data_types.setdefault(key, []).append(parse_data_type_subitems(data_type))
    return data_types


def parse_data_type_subitems(data_type):
    return tuple(
        EsiSubItemInfo(
            subindex=parse_int(xml_text(subitem.find("SubIdx"))),
            name=english_display_name(subitem) or xml_text(subitem.find("Name")),
            data_type=xml_text(subitem.find("Type")),
            bit_size=parse_int(xml_text(subitem.find("BitSize"))),
            bit_offset=parse_int(xml_text(subitem.find("BitOffs"))),
            access=access_text(subitem),
        )
        for subitem in data_type.findall("SubItem")
    )


def parse_module_objects(module, data_types):
    objects = []
    for obj in module.findall(".//Object"):
        index_el = obj.find("Index")
        index = parse_int(xml_text(index_el))
        if index <= 0:
            continue
        data_type = xml_text(obj.find("Type"))
        bit_size = parse_int(xml_text(obj.find("BitSize")))
        subitems = object_subitems(obj, data_type, bit_size, data_types)
        objects.append(EsiObjectInfo(
            index=index,
            name=xml_text(obj.find("Name")),
            data_type=data_type,
            bit_size=bit_size,
            access=access_text(obj),
            depend_on_slot=bool(index_el is not None and index_el.get("DependOnSlot")),
            subitems=subitems,
        ))
    return tuple(objects)


def object_subitems(obj, data_type, bit_size, data_types):
    info_names = [
        xml_text(subitem.find("Name"))
        for subitem in obj.findall("Info/SubItem")
    ]
    candidates = data_types.get((data_type, bit_size), [])
    if not candidates:
        return tuple(
            EsiSubItemInfo(
                subindex=index,
                name=name,
                data_type="",
                bit_size=0,
                bit_offset=0,
                access="",
            )
            for index, name in enumerate(info_names)
        )

    for candidate in candidates:
        candidate_names = [item.name for item in candidate]
        if same_subitem_names(info_names, candidate_names):
            return candidate
    return candidates[0]


def same_subitem_names(left, right):
    if len(left) != len(right):
        return False
    return [
        normalized_lookup_key(value)
        for value in left
    ] == [
        normalized_lookup_key(value)
        for value in right
    ]


def english_name(module):
    for name_el in module.findall("Name"):
        if name_el.get("LcId") == "1033":
            return xml_text(name_el)
    return xml_text(module.find("Name"))


def english_display_name(element):
    for name_el in element.findall("DisplayName"):
        if name_el.get("LcId") == "1033":
            return xml_text(name_el)
    return ""


def module_pdo_bytes(module, tag):
    bits = 0
    for pdo in module.findall(tag):
        bits += sum(
            parse_int(xml_text(entry.find("BitLen")))
            for entry in pdo.findall("Entry")
        )
    return (bits + 7) // 8


def module_has_isdu_access(module):
    for obj in module.findall(".//Object"):
        index = xml_text(obj.find("Index"))
        name = xml_text(obj.find("Name"))
        if index == "#x2001" or "ISDU Access" in name:
            return True
    return False


def normalized_lookup_key(value):
    return normalized_file_key(value)


def parse_int(value):
    value = str(value or "").strip()
    if not value:
        return 0
    if value.startswith("#x"):
        return int(value[2:], 16)
    return int(value, 0)


def access_text(element):
    access = xml_text(element.find("Flags/Access"))
    return access.strip().lower()


def xml_text(element):
    if element is None:
        return ""
    return "".join(element.itertext()).strip()
