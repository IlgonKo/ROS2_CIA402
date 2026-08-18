import os
from pathlib import Path
import re
import sys

from config_file import read_key_value_config


INDEXED_LIST_ITEM_RE = re.compile(r"^\s*\d+\s*:\s*(.+)$")


def app_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def read_dotenv(path):
    return read_key_value_config(path)


def read_config(root, filename="config.txt", fallback_filename=".env"):
    root = Path(root)
    config_path = root / filename
    if config_path.exists():
        return read_dotenv(config_path)
    return read_dotenv(root / fallback_filename)


def resolve_config_file(root, raw_path, default_path):
    root = Path(root)
    path = Path(raw_path or default_path)
    if not path.is_absolute():
        path = root / path
    if path.exists():
        return path
    if path.name == ".env":
        config_path = path.with_name("config.txt")
        if config_path.exists():
            return config_path
    return path


def load_axis_env(root):
    root = Path(root)
    values = read_config(root)
    root_config_exists = (root / "config.txt").exists()
    backend = values.get(
        "MOTION_SERVER_BACKEND",
        values.get("AXIS_SERVER_BACKEND", "pysoem"),
    ).strip().lower()

    if backend == "mock":
        default_virtual_env = (
            "device/virtual_servo_drive/config.txt"
            if root_config_exists
            else "device/virtual_servo_drive/.env"
        )
        virtual_env_file = values.get(
            "VIRTUAL_SERVO_DRIVE_ENV_FILE",
            default_virtual_env,
        )
        virtual_env_path = resolve_config_file(
            root,
            virtual_env_file,
            default_virtual_env,
        )
        values.update(read_dotenv(virtual_env_path))

    device_config_root = values.get(
        "MOTION_SERVER_DEVICE_CONFIG_ROOT",
        values.get("PYSOEM_DEVICE_CONFIG_ROOT", "device"),
    )
    device_config_root_path = Path(device_config_root)
    if not device_config_root_path.is_absolute():
        device_config_root_path = root / device_config_root_path
    bus = values.get("MOTION_SERVER_BUS", values.get("PYSOEM_BUS", "cmmt"))
    loaded_profiles = set()
    for raw_entry in bus.split(","):
        entry = strip_index_label(raw_entry).strip().lower()
        if not entry:
            continue
        profile = entry.split(":")[1].strip() if ":" in entry else entry
        if profile in loaded_profiles:
            continue
        loaded_profiles.add(profile)
        device_config_name = "config.txt" if root_config_exists else ".env"
        device_env_path = device_config_root_path / profile / device_config_name
        values.update(read_dotenv(device_env_path))

    for key, value in values.items():
        os.environ[key] = str(value)

    os.environ.setdefault("MOTION_SERVER_PROJECT_ROOT", str(root))
    os.environ.setdefault("AXIS_SERVER_PROJECT_ROOT", str(root))
    return values


def strip_index_label(item):
    match = INDEXED_LIST_ITEM_RE.match(str(item or ""))
    if match:
        return match.group(1).strip()
    return str(item or "").strip()


def add_windows_npcap_dll_paths():
    if not sys.platform.startswith("win"):
        return

    candidates = [
        Path("C:/Windows/System32/Npcap"),
        Path("C:/Program Files/Npcap"),
        Path("C:/Program Files (x86)/Npcap"),
    ]
    for path in candidates:
        if path.exists() and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(path))


def prepare_runtime():
    root = app_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    load_axis_env(root)
    add_windows_npcap_dll_paths()
    return root


def prepare_axis_control_panel_runtime():
    root = app_root()
    root_name = root.name.lower()
    parent_name = root.parent.name.lower()
    package_root = root.parent.parent if (
        root_name == "axis_control_panel"
        and parent_name == "tools"
    ) else root.parent if root_name == "tools" else root
    for path in (root, package_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    config_root = root if root_name == "axis_control_panel" else root / "axis_control_panel"
    os.environ.setdefault(
        "AXIS_CONTROL_PANEL_CONFIG_ROOT",
        str(config_root),
    )
    add_windows_npcap_dll_paths()
    return root
