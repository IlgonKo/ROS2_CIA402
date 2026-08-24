"""Runtime configuration helpers for Axis Control Panel."""

import os
from pathlib import Path

from configuration import read_key_value_config
from control_panel.axis_control_panel.client import (
    axis_count_from_status,
    request_initial_system_status,
)

PANEL_CONFIG_ROOT = Path(
    os.environ.get(
        "AXIS_CONTROL_PANEL_CONFIG_ROOT",
        Path(__file__).resolve().parent,
    )
).resolve()
PANEL_CONFIG_FILE = PANEL_CONFIG_ROOT / "config.txt"
PANEL_ENV_FILE = PANEL_CONFIG_ROOT / ".env"

def load_env_file(path):
    return read_key_value_config(path)

def load_panel_config():
    if PANEL_CONFIG_FILE.exists():
        return load_env_file(PANEL_CONFIG_FILE)
    return load_env_file(PANEL_ENV_FILE)

def default_axis_names(axis_count):
    base_names = ["X", "Y", "Z", "U", "V", "W"]
    return [
        base_names[index] if index < len(base_names) else f"A{index + 1}"
        for index in range(axis_count)
    ]

def parse_axis_names(text):
    return [
        name.strip()
        for name in str(text or "").split(",")
        if name.strip()
    ]

def read_runtime_config():
    env_file = load_panel_config()
    host = os.environ.get(
        "MOTION_SERVER_HOST",
        env_file.get("MOTION_SERVER_HOST", "127.0.0.1"),
    )
    port = int(
        os.environ.get(
            "MOTION_SERVER_PORT",
            env_file.get("MOTION_SERVER_PORT", "15000"),
        )
    )
    status = request_initial_system_status(host, port)
    axis_count = axis_count_from_status(status) or 1
    axis_names = parse_axis_names(
        os.environ.get(
            "AXIS_CONTROL_PANEL_AXIS_NAMES",
            env_file.get("AXIS_CONTROL_PANEL_AXIS_NAMES", ""),
        )
    )
    auto_sdo_reads = str(
        os.environ.get(
            "AXIS_PANEL_AUTO_SDO_READS",
            env_file.get("AXIS_PANEL_AUTO_SDO_READS", "0"),
        )
    ).strip() == "1"
    if not axis_names:
        axis_names = default_axis_names(axis_count)

    if len(axis_names) < axis_count:
        axis_names.extend(default_axis_names(axis_count)[len(axis_names):])

    return host, port, axis_names[:axis_count], auto_sdo_reads
