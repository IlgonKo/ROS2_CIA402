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


def load_axis_env(root):
    root = Path(root)
    values = read_dotenv(root / ".env")

    device_env_file = values.get("PYSOEM_DEVICE_ENV_FILE", "")
    bus = values.get("PYSOEM_BUS", "cmmt")
    bus_entries = [entry.strip().lower() for entry in bus.split(",")]
    has_cmmt = "cmmt" in bus_entries or any(
        entry.endswith(":cmmt") for entry in bus_entries
    )
    if not device_env_file and has_cmmt:
        device_env_file = "device/cmmt/.env"

    if device_env_file:
        device_env_path = Path(device_env_file)
        if not device_env_path.is_absolute():
            device_env_path = root / device_env_path
        values.update(read_dotenv(device_env_path))

    for key, value in values.items():
        os.environ.setdefault(key, str(value))

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
