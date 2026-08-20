from motion_server.api import reject_command_message


def reject_ap_parameter_catalog(message_type, message, runtime, state, client):
    reject_command_message(
        client,
        message_type,
        (
            "system/io/ap/param_catalog is not implemented. "
            "AP parameter catalog requires APDD support."
        ),
    )
