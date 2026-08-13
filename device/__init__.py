from device.cmmt.profile import CMMTDeviceProfile
from device.cpx_ap_i_ec.profile import CPXApIEcDeviceProfile


DEVICE_PROFILES = {
    "cmmt": CMMTDeviceProfile,
    "cpx_ap_i_ec": CPXApIEcDeviceProfile,
}


def available_device_names():
    return sorted(DEVICE_PROFILES)


def get_device_profile(name, **kwargs):
    key = str(name or "cmmt").strip().lower()
    try:
        profile_class = DEVICE_PROFILES[key]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported device profile: {name}. "
            f"Supported profiles: {', '.join(available_device_names())}"
        ) from exc
    return profile_class(**kwargs)
