from motion_server.api.decoder import selected_io_device
from motion_server.api.encoder import io_device_snapshot
from motion_server.failure import ResourceNotFoundException, ServerNotReadyException
from motion_server.handlers.status.server_health import process_data_is_valid


def input_read(message, runtime, state, client):
    return input_read_data(message, runtime, process_data_valid=process_data_is_valid(state))


def input_read_data(message, runtime, *, process_data_valid=True):
    selector = message.get("io", message.get("id"))
    try:
        device = selected_io_device(
            runtime,
            io_id=selector,
            slave_index=message.get("slave_index"),
        )
    except AttributeError as exc:
        raise ServerNotReadyException("I/O devices are unavailable") from exc
    except (TypeError, ValueError) as exc:
        raise ResourceNotFoundException("io", selector) from exc

    response = io_device_snapshot(
        device,
        include_raw=bool(message.get("raw", False)),
        process_data_valid=process_data_valid,
    )
    response.pop("type", None)
    response.pop("ok", None)
    return response
