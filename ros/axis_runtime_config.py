import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


DEFAULT_AXIS_CONFIGS = [
    {
        "name": "X",
        "max_velocity": 1000.0,
        "acceleration": 500.0,
        "deceleration": 500.0,
        "jerk": 5000.0,
    },
    {
        "name": "Y",
        "max_velocity": 500.0,
        "acceleration": 300.0,
        "deceleration": 300.0,
        "jerk": 3000.0,
    },
    {
        "name": "Z",
        "max_velocity": 2000.0,
        "acceleration": 1000.0,
        "deceleration": 1000.0,
        "jerk": 10000.0,
    },
]


def load_env_file(path):
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


def runtime_env():
    values = load_env_file(PROJECT_ROOT / ".env")
    values.update(os.environ)
    return values


def get_axis_names():
    env = runtime_env()
    names = env.get("ROS2_CIA402_AXIS_NAMES")
    if names:
        return [
            name.strip()
            for name in names.split(",")
            if name.strip()
        ]

    axis_count = int(env.get("PYSOEM_AXIS_COUNT", "3"))
    base_names = [
        config["name"]
        for config in DEFAULT_AXIS_CONFIGS
    ]
    if axis_count <= len(base_names):
        return base_names[:axis_count]

    return base_names + [
        f"A{index + 1}"
        for index in range(len(base_names), axis_count)
    ]


def get_axis_configs():
    names = get_axis_names()
    configs = []

    for index, name in enumerate(names):
        if index < len(DEFAULT_AXIS_CONFIGS):
            config = dict(DEFAULT_AXIS_CONFIGS[index])
            config["name"] = name
        else:
            config = {
                "name": name,
                "max_velocity": 1000.0,
                "acceleration": 500.0,
                "deceleration": 500.0,
                "jerk": 5000.0,
            }

        configs.append(config)

    return configs


def get_axis_count():
    return len(get_axis_names())


def get_pysoem_interface():
    env = runtime_env()
    return env.get("ROS2_CIA402_INTERFACE", env.get("PYSOEM_INTERFACE", "")).strip()
