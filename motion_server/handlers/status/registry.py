from motion_server.api.decoder import selected_single_axis
from motion_server.api.encoder import (
    reject_command_message,
    send_client_message,
    legacy_status_request_response,
    status_data,
)
from motion_server.failure import InvalidRequestException
from motion_server.api.specification import status_message_types
from motion_server.app.state import inactive_trajectory_state
from motion_server.handlers.status.axis_parameter_read import read_parameter
from motion_server.handlers.status.io_ethercat_parameter_read import read_io_parameter
from motion_server.handlers.status.io_ap_parameter_read import read_ap_parameter
from motion_server.handlers.status.axis_status import (
    axes_status_message,
    axis_status_message,
)
from motion_server.handlers.status.axis_parameter_catalog import axis_param_catalog
from motion_server.handlers.status.bus_status import bus_status_message
from motion_server.handlers.status.io_ethercat_parameter_catalog import (
    ethercat_param_catalog,
)
from motion_server.handlers.status.io_status import io_status_message
from motion_server.handlers.status.io_iol_parameter_catalog import iol_param_catalog
from motion_server.handlers.status.io_iol_parameter_read import read_iol_parameter
from motion_server.handlers.status.io_input_read import input_read
from motion_server.handlers.status.io_ap_parameter_catalog import (
    reject_ap_parameter_catalog,
)
from motion_server.handlers.status.server_status import server_status_message


def handle_advanced_status_rejection(message_type, runtime, state, client):
    status = axes_status_message(runtime, state, client["id"])
    status["type"] = message_type
    status["trajectory"] = inactive_trajectory_state("advanced_only")
    status["trajectory"]["message"] = (
        f"{message_type} is available only in Motion Server advanced mode."
    )
    send_client_message(client, status)


def handle_server_status(message_type, message, runtime, state, client):
    return send_status_operation(
        message,
        client,
        lambda: status_data(server_status_message(runtime, state)),
    )


def handle_bus_status(message_type, message, runtime, state, client):
    return send_status_operation(
        message,
        client,
        lambda: status_data(bus_status_message(runtime, state)),
    )


def handle_axes_status(message_type, message, runtime, state, client):
    return send_status_operation(
        message,
        client,
        lambda: status_data(axes_status_message(runtime, state, client["id"])),
        include_ok=False,
    )


def handle_io_status(message_type, message, runtime, state, client):
    return send_status_operation(
        message,
        client,
        lambda: status_data(
            io_status_message(
                runtime,
                state,
                include_raw=bool(message.get("raw", False)),
            ),
        ),
    )


def handle_axis_status(message_type, message, runtime, state, client):
    if "axes" in message or "axis" not in message:
        return send_status_operation(
            message,
            client,
            invalid_axis_status_request,
            include_ok=False,
        )
    return send_status_operation(
        message,
        client,
        lambda: status_data(
            axis_status_message(
                runtime,
                state,
                selected_single_axis(message, runtime, message_type),
                client["id"],
            ),
        ),
        include_ok=False,
    )


def invalid_axis_status_request():
    raise InvalidRequestException(
        "Axis status requires axis and does not accept axes",
    )


def send_status_operation(message, client, operation, *, include_ok=True):
    # TECH_DEBT[TD-005]: S10 sends this response directly after client migration.
    return legacy_status_request_response(
        message,
        client,
        operation,
        include_ok=include_ok,
    )


def handle_axis_parameter_read(message_type, message, runtime, state, client):
    read_parameter(message, runtime, client)


def handle_io_parameter_read(message_type, message, runtime, state, client):
    read_io_parameter(message, runtime, client)


def reject_not_implemented(message_type, message, runtime, state, client):
    reject_command_message(
        client,
        message_type,
        f"{message_type} is not implemented yet.",
    )


def handle_io_input_read(message_type, message, runtime, state, client):
    input_read(message, runtime, state, client)


def handle_axis_parameter_catalog(message_type, message, runtime, state, client):
    axis_param_catalog(message, runtime, client)


def handle_ethercat_parameter_catalog(message_type, message, runtime, state, client):
    ethercat_param_catalog(message, runtime, client)


def handle_iol_parameter_catalog(message_type, message, runtime, state, client):
    iol_param_catalog(message, runtime, client)


def handle_ap_parameter_read(message_type, message, runtime, state, client):
    read_ap_parameter(message, runtime, client)


def handle_iol_parameter_read(message_type, message, runtime, state, client):
    read_iol_parameter(message, runtime, client)


STATUS_HANDLERS = {
    "system/server/status": handle_server_status,
    "system/bus/status": handle_bus_status,
    "system/axes/status": handle_axes_status,
    "system/io/status": handle_io_status,
    "system/axis/status": handle_axis_status,
    "system/axis/param_read": handle_axis_parameter_read,
    "system/io/param_read": handle_io_parameter_read,
    "system/io/input_read": handle_io_input_read,
    "system/axis/param_catalog": handle_axis_parameter_catalog,
    "system/io/ethercat/param_catalog": handle_ethercat_parameter_catalog,
    "system/io/ap/param_catalog": reject_ap_parameter_catalog,
    "system/io/iol/param_catalog": handle_iol_parameter_catalog,
    "system/io/ap/param_read": handle_ap_parameter_read,
    "system/io/iol/param_read": handle_iol_parameter_read,
}


def validate_status_registry():
    handler_names = set(STATUS_HANDLERS)
    expected_names = status_message_types()
    missing = sorted(expected_names - handler_names)
    unknown = sorted(handler_names - expected_names)
    if missing or unknown:
        raise RuntimeError(
            "Motion Server status registry/specification mismatch. "
            f"missing={missing} unknown={unknown}"
        )


validate_status_registry()


def handle_status(message_type, message, runtime, state, client):
    handler = STATUS_HANDLERS.get(message_type)
    if handler is None:
        return False
    handler(message_type, message, runtime, state, client)
    return True
