"""Runtime configuration helpers for IO Control Panel."""

import os
from pathlib import Path

from configuration import read_key_value_config


PANEL_CONFIG_ROOT = Path(
    os.environ.get(
        "IO_CONTROL_PANEL_CONFIG_ROOT",
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


def read_runtime_config():
    config = load_panel_config()
    host = os.environ.get(
        "MOTION_SERVER_HOST",
        config.get("MOTION_SERVER_HOST", "127.0.0.1"),
    )
    port = int(
        os.environ.get(
            "MOTION_SERVER_PORT",
            config.get("MOTION_SERVER_PORT", "15000"),
        )
    )
    return host, port
