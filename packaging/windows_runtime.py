import os
from pathlib import Path
import sys

def app_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


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


def prepare_io_control_panel_runtime():
    root = app_root()
    root_name = root.name.lower()
    parent_name = root.parent.name.lower()
    package_root = root.parent.parent if (
        root_name == "io_control_panel"
        and parent_name == "tools"
    ) else root.parent if root_name == "tools" else root
    for path in (root, package_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    config_root = root if root_name == "io_control_panel" else root / "io_control_panel"
    os.environ.setdefault(
        "IO_CONTROL_PANEL_CONFIG_ROOT",
        str(config_root),
    )
    add_windows_npcap_dll_paths()
    return root
