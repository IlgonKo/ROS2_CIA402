def request_bus_reconnect(message, runtime, state, client):
    state["bus_reconnect_requested"] = True
    return {
        "message": (
            "EtherCAT bus reconnect accepted. "
            "Runtime will be reinitialized with the current configuration."
        ),
    }
