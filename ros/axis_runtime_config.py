import os


DEFAULT_AXIS_CONFIGS = [
    {
        "name": "X",
        "max_velocity": 1000.0,
        "acceleration": 500.0,
        "deceleration": 500.0,
        "kp": 5.0,
    },
    {
        "name": "Y",
        "max_velocity": 500.0,
        "acceleration": 300.0,
        "deceleration": 300.0,
        "kp": 3.0,
    },
    {
        "name": "Z",
        "max_velocity": 2000.0,
        "acceleration": 1000.0,
        "deceleration": 1000.0,
        "kp": 8.0,
    },
]


def get_master_backend():
    backend = os.environ.get("ROS2_CIA402_MASTER")
    if backend:
        return backend.strip().lower()

    if get_pysoem_interface():
        return "pysoem"

    return "mock"


def get_axis_names():
    names = os.environ.get("ROS2_CIA402_AXIS_NAMES")
    if names:
        return [
            name.strip()
            for name in names.split(",")
            if name.strip()
        ]

    if get_master_backend() == "pysoem":
        return ["X"]

    return [
        config["name"]
        for config in DEFAULT_AXIS_CONFIGS
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
                "kp": 5.0,
            }

        configs.append(config)

    return configs


def get_axis_count():
    return len(get_axis_names())


def get_pysoem_interface():
    return os.environ.get("ROS2_CIA402_INTERFACE", "").strip()
