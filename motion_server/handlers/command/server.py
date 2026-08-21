def request_server_reset(message, runtime, state, client):
    state["server_reset_requested"] = True
    return {
        "message": (
            "Motion Server reset accepted. "
            "Runtime and EtherCAT bus will be reinitialized."
        ),
    }


def request_server_restart(message, runtime, state, client):
    state["server_restart_requested"] = True
    return {"message": "Motion Server restart accepted. Process will restart."}
