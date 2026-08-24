from dataclasses import dataclass
from enum import Enum

from configuration.file_parser import split_indexed_config_list


class DeviceRole(str, Enum):
    AXIS = "axis"
    IO = "io"


@dataclass(frozen=True)
class BusDevice:
    slave_index: int
    configured_index: int
    role: DeviceRole
    profile: str
    logical_id: str | None = None


@dataclass(frozen=True)
class BusConfig:
    devices: tuple[BusDevice, ...]

    @property
    def device_profile_names(self):
        return tuple(device.profile for device in self.devices)

    @property
    def axis_slave_indices(self):
        return tuple(
            device.slave_index
            for device in self.devices
            if device.role is DeviceRole.AXIS
        )

    @property
    def io_devices(self):
        return tuple(
            {
                "id": device.logical_id,
                "profile": device.profile,
                "slave_index": device.slave_index,
            }
            for device in self.devices
            if device.role is DeviceRole.IO
        )

    @property
    def profile_names(self):
        return tuple(dict.fromkeys(self.device_profile_names))


def parse_bus_config(raw_bus, available_profiles=None):
    raw_bus = str(raw_bus or "").strip()
    if not raw_bus:
        raise ValueError("MOTION_SERVER_BUS must not be empty")

    available = None if available_profiles is None else set(available_profiles)
    devices = []
    io_count = 0
    for configured_index, raw_entry in split_indexed_config_list(
        raw_bus,
        default_start=0,
    ):
        entry = raw_entry.strip().lower()
        role_name = "axis"
        profile_name = entry
        logical_id = None
        if ":" in entry:
            parts = [part.strip() for part in entry.split(":")]
            role_name = parts[0]
            profile_name = parts[1].replace("-", "_") if len(parts) > 1 else ""
            logical_id = parts[2] if len(parts) > 2 else None
        else:
            profile_name = profile_name.replace("-", "_")

        if role_name in {"axis", "drive"}:
            role = DeviceRole.AXIS
        elif role_name in {"io", "device", "slave"}:
            role = DeviceRole.IO
        else:
            raise ValueError(
                f"Unsupported MOTION_SERVER_BUS role {role_name!r}; "
                "use axis:<profile> or io:<profile>:<id>"
            )

        if role is DeviceRole.AXIS and profile_name == "cmmt":
            raise ValueError(
                "MOTION_SERVER_BUS must specify the detailed CMMT profile. "
                "Use cmmt_as or cmmt_st instead of cmmt."
            )
        if available is not None and profile_name not in available:
            raise ValueError(
                f"Unsupported MOTION_SERVER_BUS profile {profile_name!r}. "
                f"Supported profiles: {', '.join(sorted(available))}"
            )

        if role is DeviceRole.IO and not logical_id:
            logical_id = f"io{io_count}"
        if role is DeviceRole.IO:
            io_count += 1

        devices.append(
            BusDevice(
                slave_index=len(devices),
                configured_index=configured_index,
                role=role,
                profile=profile_name,
                logical_id=logical_id,
            )
        )

    if not devices:
        raise ValueError("MOTION_SERVER_BUS does not contain any devices")
    return BusConfig(tuple(devices))
