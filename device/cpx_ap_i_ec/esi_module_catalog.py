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
class EsiPdoEntryInfo:
    index: int
    subindex: int
    bit_length: int
    name: str

    def mapping_entry(self):
        if self.index == 0:
            return self.bit_length & 0xFF
        return (
            ((self.index & 0xFFFF) << 16)
            | ((self.subindex & 0xFF) << 8)
            | (self.bit_length & 0xFF)
        )


@dataclass(frozen=True)
class EsiPdoInfo:
    index: int
    name: str
    entries: tuple[EsiPdoEntryInfo, ...]

    @property
    def byte_size(self):
        return (sum(entry.bit_length for entry in self.entries) + 7) // 8

    def mapping_entries(self):
        return [entry.mapping_entry() for entry in self.entries]


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
    root = ET.parse(esi_path).getroot()
    data_types = parse_data_types(root)
    device = find_device(root)
    modules = parse_esi_modules(root, data_types)
    by_name = {}
    by_ident = {}
    for module in modules:
        by_ident.setdefault(module.ident, module)
        by_name.setdefault(normalized_lookup_key(module.type_name), module)
        by_name.setdefault(normalized_lookup_key(module.display_name), module)
    return EsiCatalog(
        esi_path,
        tuple(modules),
        by_name,
        by_ident,
        objects=parse_device_objects(device, data_types),
        rxpdos=parse_pdos(device, "RxPdo"),
        txpdos=parse_pdos(device, "TxPdo"),
    )


@dataclass(frozen=True)
class EsiCatalog:
    path: Path
    modules: tuple[EsiModuleInfo, ...]
    by_name: dict
    by_ident: dict
    objects: dict
    rxpdos: dict
    txpdos: dict

    def object_info(self, index, subindex=0):
        return self.objects[(int(index), int(subindex))]


def find_esi_file(stem):
    return find_unique_xml_file(ESI_DIR, stem, "CPX-AP-I-EC ESI")


def find_device(root):
    candidates = []
    for device in root.findall(".//Device"):
        type_el = device.find("Type")
        if type_el is None or xml_text(type_el) != "CPX-AP-I-EC-M12":
            continue
        candidates.append(device)
        if device_has_object(device, 0x27F0):
            return device
    if candidates:
        return candidates[0]
    raise ValueError("CPX-AP-I-EC ESI does not contain a Device entry")


def device_has_object(device, index):
    expected = f"#x{int(index):04x}"
    for obj in device.findall("Profile/Dictionary/Objects/Object"):
        index_el = obj.find("Index")
        if index_el is None:
            continue
        if xml_text(index_el).strip().lower() == expected:
            return True
    return False


def parse_esi_modules(root, data_types):
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
    return parse_objects(module.findall(".//Object"), data_types)


def parse_device_objects(device, data_types):
    objects = {}
    for obj in parse_objects(
        device.findall("Profile/Dictionary/Objects/Object"),
        data_types,
    ):
        objects[(obj.index, 0)] = obj
        for subitem in obj.subitems:
            if int(subitem.subindex) == 0:
                continue
            objects[(obj.index, subitem.subindex)] = EsiObjectInfo(
                index=obj.index,
                name=subitem.name,
                data_type=subitem.data_type,
                bit_size=subitem.bit_size,
                access=subitem.access or obj.access,
                depend_on_slot=obj.depend_on_slot,
                subitems=(),
            )
    return objects


def parse_objects(object_elements, data_types):
    objects = []
    for obj in object_elements:
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


def parse_pdos(device, tag):
    pdos = {}
    for pdo in device.findall(tag):
        index = parse_int(xml_text(pdo.find("Index")))
        if index <= 0:
            continue
        pdos[index] = EsiPdoInfo(
            index=index,
            name=xml_text(pdo.find("Name")),
            entries=tuple(parse_pdo_entry(entry) for entry in pdo.findall("Entry")),
        )
    return pdos


def parse_pdo_entry(entry):
    return EsiPdoEntryInfo(
        index=parse_int(xml_text(entry.find("Index"))),
        subindex=parse_int(xml_text(entry.find("SubIndex"))),
        bit_length=parse_int(xml_text(entry.find("BitLen"))),
        name=xml_text(entry.find("Name")),
    )


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
