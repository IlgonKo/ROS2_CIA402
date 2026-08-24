from motion_server.failure import UnsupportedOperationException


def reject_ap_parameter_catalog(message_type, message, runtime, state, client):
    raise UnsupportedOperationException(
        message_type,
        "AP parameter catalog requires APDD support",
    )
