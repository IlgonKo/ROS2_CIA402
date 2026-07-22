import os
from pathlib import Path
import sys


def app_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def read_dotenv(path):
    values = {}
    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


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

    device_env_file = values.get("PYSOEM_DEVICE_ENV_FILE", "")
    bus = values.get("PYSOEM_BUS", "cmmt")
    bus_entries = [entry.strip().lower() for entry in bus.split(",")]
    has_cmmt = "cmmt" in bus_entries or any(
        entry.endswith(":cmmt") for entry in bus_entries
    )
    if not device_env_file and has_cmmt:
        device_env_file = (
            "device/cmmt/config.txt"
            if root_config_exists
            else "device/cmmt/.env"
        )

    if device_env_file:
        device_env_path = resolve_config_file(root, device_env_file, "")
        values.update(read_dotenv(device_env_path))

    for key, value in values.items():
        os.environ[key] = str(value)

    os.environ.setdefault("MOTION_SERVER_PROJECT_ROOT", str(root))
    os.environ.setdefault("AXIS_SERVER_PROJECT_ROOT", str(root))
    return values


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
