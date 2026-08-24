from motion_server.api.decoder import io_devices
from motion_server.api.encoder import io_device_snapshot
from motion_server.diagnostic.models import DiagnosticSourceType
from motion_server.diagnostic.serialization import diagnostic_status_snapshot


def io_status_message(runtime, state, include_raw=False):
    return {
        "type": "system/io/status",
        "drive_initialized": bool(state.get("drive_initialized", True)),
        "initialization_error": state.get("initialization_error", ""),
        "io_count": len(io_devices(runtime)),
        "devices": [
            io_device_snapshot(device, include_raw=include_raw)
            for device in io_devices(runtime)
        ],
        "diagnostic_status": diagnostic_status_snapshot(
            runtime,
            source_type=DiagnosticSourceType.IO,
        ),
    }
