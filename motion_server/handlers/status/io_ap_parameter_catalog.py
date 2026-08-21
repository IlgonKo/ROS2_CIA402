from motion_server.api import raise_operation_rejected


def reject_ap_parameter_catalog(message_type, message, runtime, state, client):
    raise_operation_rejected(
        client,
        message_type,
        (
            "system/io/ap/param_catalog is not implemented. "
            "AP parameter catalog requires APDD support."
        ),
    )
