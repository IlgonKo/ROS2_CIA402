def axis_device_profile(runtime, axis_index):
    profile = getattr(runtime.slaves[int(axis_index)], "device_profile", None)
    if profile is None:
        raise RuntimeError(f"Axis {axis_index} does not expose a device profile")
    return profile


def axis_motion_modes(runtime, axis_index=0):
    return axis_device_profile(runtime, axis_index).MOTION_MODES
