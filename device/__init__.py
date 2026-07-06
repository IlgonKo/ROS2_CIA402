from device.cmmt.profile import CMMTDeviceProfile


DEVICE_PROFILES = {
    "cmmt": CMMTDeviceProfile,
}


def available_device_names():
    return sorted(DEVICE_PROFILES)


def get_device_profile(name):
    key = str(name or "cmmt").strip().lower()
    try:
        profile_class = DEVICE_PROFILES[key]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported device profile: {name}. "
            f"Supported profiles: {', '.join(available_device_names())}"
        ) from exc
    return profile_class()
