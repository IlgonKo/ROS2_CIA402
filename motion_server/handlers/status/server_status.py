def server_status_message(runtime, state):
    return {
        "type": "system/server/status",
        "ok": True,
        "server_mode": state.get("server_mode", "basic"),
        "drive_initialized": bool(state.get("drive_initialized", True)),
        "initialization_error": state.get("initialization_error", ""),
        "axis_count": len(runtime.slaves),
        "cycle_time": float(runtime.cycle_time),
        "feedback_type": "system/feedback",
    }
