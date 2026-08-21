from enum import Enum


class DeviceCapability(Enum):
    AXIS_RESTART = "axis_restart"


_CAPABILITY_METHODS = {
    DeviceCapability.AXIS_RESTART: (
        "request_axis_restart",
        "clear_axis_restart_request",
    ),
}


def validate_device_capabilities(profile):
    capabilities = frozenset(profile.capabilities)
    for capability in capabilities:
        required_methods = _CAPABILITY_METHODS[capability]
        missing = [
            name
            for name in required_methods
            if not callable(getattr(profile, name, None))
        ]
        if missing:
            raise TypeError(
                f"Device profile {profile.name!r} declares {capability.name} "
                f"but is missing methods: {', '.join(missing)}"
            )
    return capabilities
