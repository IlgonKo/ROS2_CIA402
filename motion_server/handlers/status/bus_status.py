from motion_server.diagnostic.models import DiagnosticSourceType
from motion_server.diagnostic.serialization import diagnostic_status_snapshot


def bus_status_message(runtime, state):
    expected_wkc = runtime.expected_wkc()
    actual_wkc = int(getattr(runtime, "wkc", 0))
    return {
        "type": "system/bus/status",
        "drive_initialized": bool(state.get("drive_initialized", True)),
        "initialization_error": state.get("initialization_error", ""),
        "device_count": len(runtime.ethercat_devices),
        "axis_count": len(runtime.slaves),
        "wkc": actual_wkc,
        "expected_wkc": expected_wkc,
        "wkc_ok": actual_wkc == expected_wkc,
        "statuswords": [
            int(slave.txpdo.statusword)
            for slave in runtime.slaves
        ],
        "mode_displays": [
            int(slave.txpdo.mode_of_operation_display)
            for slave in runtime.slaves
        ],
        "diagnostic_status": diagnostic_status_snapshot(
            runtime,
            source_type=DiagnosticSourceType.BUS,
        ),
    }
