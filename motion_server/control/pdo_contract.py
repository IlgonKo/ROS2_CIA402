COMMON_RXPDO_FIELDS = ("controlword", "mode_of_operation")
COMMON_TXPDO_FIELDS = (
    "statusword",
    "mode_of_operation_display",
    "actual_position",
    "actual_velocity",
)
MODE_RXPDO_FIELDS = {
    "pp": ("target_position", "profile_velocity"),
    "pv": ("target_velocity",),
    "csp": ("target_position",),
    "homing": (),
    "jog": (),
}


def require_pdo_fields_for_mode(runtime, mode_name, axis_index=None):
    axis_indices = range(len(runtime.slaves)) if axis_index is None else [axis_index]
    fields = list(COMMON_RXPDO_FIELDS)
    fields.extend(MODE_RXPDO_FIELDS.get(mode_name, ()))
    if mode_name == "csp" and runtime.csp_velocity_offset_enabled:
        fields.append("velocity_offset")
    for current_axis in axis_indices:
        require_pdo_fields(
            runtime.slaves[current_axis].rxpdo,
            tuple(dict.fromkeys(fields)),
            f"Axis {current_axis} RxPDO {mode_name.upper()}",
        )


def require_txpdo_fields(runtime):
    for axis_index, slave in enumerate(runtime.slaves):
        require_pdo_fields(
            slave.txpdo,
            COMMON_TXPDO_FIELDS,
            f"Axis {axis_index} TxPDO",
        )


def require_pdo_fields(pdo, fields, context):
    missing = [field for field in fields if not pdo.has_field(field)]
    if missing:
        raise RuntimeError(
            f"{context} is missing required PDO field(s): {', '.join(missing)}"
        )
