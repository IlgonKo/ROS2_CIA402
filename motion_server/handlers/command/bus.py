from motion_server.app.recovery import reconnect_runtime


def request_bus_reconnect(message, runtime, state, client):
    recovery = state.get("bus_reconnect_operation")
    if recovery is not None:
        return recovery()
    return reconnect_runtime(runtime, state)
