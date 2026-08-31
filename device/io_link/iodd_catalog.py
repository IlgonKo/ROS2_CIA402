from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import xml.etree.ElementTree as ET

from device.io_link.iodd_process_data import IoddProcessDataCompiler
from device.io_link.process_data import ProcessDataLayout

from device.io_link.file_matching import (
    find_unique_xml_file,
    normalized_file_key,
)


IODD_DIR = Path(__file__).resolve().parent / "iodd"


@dataclass(frozen=True)
class IoddProcessDataInfo:
    profile_id: str
    input_bytes: int
    output_bytes: int
    condition_value: int | None = None
    input_layout: ProcessDataLayout | None = None


@dataclass(frozen=True)
class IoddVariableInfo:
    variable_id: str
    index: int
    access: str
    data_type: str
    bit_length: int
    name: str
    subindices: tuple = ()


@dataclass(frozen=True)
class IoddDeviceInfo:
    key: str
    path: Path
    vendor_id: int
    device_id: int
    vendor_name: str
    device_name: str
    process_data_profiles: tuple[IoddProcessDataInfo, ...]
    variables: tuple[IoddVariableInfo, ...]

    @property
    def process_data_size(self):
        profile = self.select_process_data_profile()
        return profile.input_bytes, profile.output_bytes

    def select_process_data_profile(self, profile_number=None):
        if not self.process_data_profiles:
            raise ValueError(f"IODD {self.key!r} has no process data profiles")
        if profile_number is None:
            return self.process_data_profiles[0]
        if type(profile_number) is not int or profile_number < 0:
            raise ValueError("IO-Link process data profile must be a non-negative integer")
        matches = [
            profile for profile in self.process_data_profiles
            if profile.condition_value == profile_number
        ]
        if len(matches) != 1:
            available = ", ".join(
                f"{profile.condition_value} ({profile.profile_id})"
                for profile in self.process_data_profiles
                if profile.condition_value is not None
            ) or "none (omit the profile to select the first ProcessData)"
            raise ValueError(
                f"IODD {self.key!r} process data profile {profile_number!r} "
                f"must match exactly one Condition value; available: {available}"
            )
        return matches[0]


def iodd_device_info(device_key):
    key = normalized_file_key(device_key)
    return _iodd_device_info(key)


@lru_cache(maxsize=None)
def _iodd_device_info(device_key):
    path = find_unique_xml_file(IODD_DIR, device_key, "IO-Link IODD")
    return parse_iodd_file(path, device_key)


def parse_iodd_file(path, device_key):
    root = ET.parse(path).getroot()
    namespace = xml_namespace(root)
    ns = {"i": namespace}
    text_map = iodd_text_map(root, ns)
    identity = root.find(".//i:DeviceIdentity", ns)

    return IoddDeviceInfo(
        key=device_key,
        path=path,
        vendor_id=parse_int(attribute(identity, "vendorId")),
        device_id=parse_int(attribute(identity, "deviceId")),
        vendor_name=attribute(identity, "vendorName"),
        device_name=text_value(identity.find("i:DeviceName", ns), text_map),
        process_data_profiles=parse_process_data_profiles(root),
        variables=parse_variables(root, ns, text_map),
    )


def parse_process_data_profiles(root):
    profiles = []
    compiler = IoddProcessDataCompiler(root)
    for process_data in elements_by_local_name(root, "ProcessData"):
        input_el = first_child_by_local_name(process_data, "ProcessDataIn")
        output_el = first_child_by_local_name(process_data, "ProcessDataOut")
        condition = first_child_by_local_name(process_data, "Condition")
        condition_value = attribute(condition, "value")
        profiles.append(IoddProcessDataInfo(
            profile_id=attribute(process_data, "id"),
            input_bytes=bits_to_bytes(attribute(input_el, "bitLength")),
            output_bytes=bits_to_bytes(attribute(output_el, "bitLength")),
            condition_value=int(condition_value, 10) if condition_value else None,
            input_layout=compiler.compile(input_el, attribute(process_data, "id")),
        ))
    return tuple(profiles)


def parse_variables(root, ns, text_map):
    variables = []
    for variable in elements_by_local_name(root, "Variable"):
        datatype = first_child_by_local_name(variable, "Datatype")
        variables.append(IoddVariableInfo(
            variable_id=attribute(variable, "id"),
            index=parse_int(attribute(variable, "index")),
            access=attribute(variable, "accessRights"),
            data_type=xml_datatype(datatype),
            bit_length=parse_int(attribute(datatype, "bitLength")),
            name=text_value(variable.find("i:Name", ns), text_map),
            subindices=parse_record_subindices(variable),
        ))
    return tuple(variables)


def parse_record_subindices(variable):
    return tuple(
        {
            "subindex": parse_int(attribute(item, "subindex")),
            "default": attribute(item, "defaultValue"),
        }
        for item in elements_by_local_name(variable, "RecordItemInfo")
    )


def iodd_text_map(root, ns):
    texts = {}
    for text in root.findall(".//i:Text", ns):
        text_id = attribute(text, "id")
        if text_id:
            texts[text_id] = attribute(text, "value")
    return texts


def text_value(element, text_map):
    text_id = attribute(element, "textId")
    return text_map.get(text_id, text_id)


def xml_datatype(datatype):
    if datatype is None:
        return ""
    return (
        datatype.get("{http://www.w3.org/2001/XMLSchema-instance}type")
        or attribute(datatype, "type")
    )


def xml_namespace(root):
    if root.tag.startswith("{"):
        return root.tag.split("}", 1)[0][1:]
    return ""


def elements_by_local_name(root, name):
    return [
        element
        for element in root.iter()
        if local_name(element.tag) == name
    ]


def first_child_by_local_name(element, name):
    if element is None:
        return None
    for child in element:
        if local_name(child.tag) == name:
            return child
    return None


def local_name(tag):
    return str(tag).split("}", 1)[-1]


def attribute(element, name, default=""):
    if element is None:
        return default
    return element.get(name, default)


def parse_int(value):
    value = str(value or "").strip()
    if not value:
        return 0
    return int(value, 0)


def bits_to_bytes(bit_length):
    return (parse_int(bit_length) + 7) // 8
