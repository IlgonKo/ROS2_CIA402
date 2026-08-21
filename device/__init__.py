from device.cmmt.profile import (
    CMMTASDeviceProfile,
    CMMTDeviceProfile,
    CMMTSTDeviceProfile,
)
from device.cpx_ap_i_ec.profile import CPXApIEcDeviceProfile
from device.capabilities import validate_device_capabilities


DEVICE_PROFILES = {
    "cmmt": CMMTDeviceProfile,
    "cmmt_as": CMMTASDeviceProfile,
    "cmmt_st": CMMTSTDeviceProfile,
    "cpx_ap_i_ec": CPXApIEcDeviceProfile,
}


def available_device_names():
    return sorted(DEVICE_PROFILES)


def get_device_profile(name, **kwargs):
    key = str(name or "cmmt").strip().lower().replace("-", "_")
    try:
        profile_class = DEVICE_PROFILES[key]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported device profile: {name}. "
            f"Supported profiles: {', '.join(available_device_names())}"
        ) from exc
    profile = profile_class(**kwargs)
    validate_device_capabilities(profile)
    return profile
