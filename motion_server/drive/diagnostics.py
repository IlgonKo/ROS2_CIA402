def format_diagnostics(diagnostics):
    def format_value(value, width=None):
        if isinstance(value, int) and width is not None:
            return f"0x{value:0{width}X}"

        return str(value)

    return (
        f"SDO_SW={format_value(diagnostics['statusword'], 4)} "
        f"ERR={diagnostics['error_code_text']} "
        f"MODE_DISP={diagnostics['mode_display']}"
    )


def format_axis_diagnostics(diagnostics_list):
    return " | ".join(
        f"A{index}:{format_diagnostics(diagnostics)}"
        for index, diagnostics in enumerate(diagnostics_list)
    )


def read_drive_diagnostics(runtime, axis_index, device_profile):
    return device_profile.read_diagnostics(runtime, axis_index)


def read_all_diagnostics(runtime, device_profile):
    return [
        read_drive_diagnostics(runtime, axis_index, device_profile)
        for axis_index in range(len(runtime.slaves))
    ]


def diagnostics_summary(runtime, axis_indices, device_profile):
    summaries = []
    for axis_index in axis_indices:
        try:
            diagnostics = read_drive_diagnostics(
                runtime,
                axis_index,
                device_profile,
            )
        except Exception as exc:
            summaries.append(f"axis {axis_index}: diagnostics read failed: {exc}")
            continue
        statusword = diagnostics.get("statusword")
        error_code = diagnostics.get("error_code")
        status_text = (
            f"0x{statusword:04X}" if isinstance(statusword, int) else str(statusword)
        )
        error_text = (
            f"0x{error_code:08X}" if isinstance(error_code, int) else str(error_code)
        )
        summaries.append(
            f"axis {axis_index}: statusword={status_text} "
            f"error_code={error_text} "
            f"mode_display={diagnostics.get('mode_display')} "
            f"error={diagnostics.get('error_code_text')}"
        )
    return summaries


def default_diagnostics(axis_count_value, error_message=""):
    text = error_message or "not initialized"
    return [
        {
            "statusword": 0,
            "error_code": 0,
            "mode_display": 0,
            "manufacturer_status": 0,
            "error_code_text": text,
        }
        for _ in range(axis_count_value)
    ]
