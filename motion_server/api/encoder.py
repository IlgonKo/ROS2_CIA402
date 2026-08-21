import json
from dataclasses import dataclass
from typing import Mapping

from device.cpx_ap_i_ec.module_resolver import module_display_name
from device.cpx_ap_i_ec.pdo import (
    flattened_analog_inputs,
    flattened_analog_outputs,
    flattened_digital_inputs,
    flattened_digital_outputs,
)
from motion_server.control.axis_units import (
    axis_position_drive_to_api,
    motion_limits_drive_to_api,
    profile_settings_drive_to_api,
)
from motion_server.failure import Failure, PartialFailure, map_exception
from motion_server.failure.codes import FailureCode


@dataclass(frozen=True)
class ResponseContext:
    response_type: str
    request_id: object | None = None
    has_request_id: bool = False

    @classmethod
    def from_request(cls, request: Mapping[str, object]):
        response_type = str(
            request.get("cmd", request.get("type", "")),
        ).strip()
        if not response_type:
            raise ValueError("request requires cmd or type")
        return cls(
            response_type=response_type,
            request_id=request.get("request_id"),
            has_request_id="request_id" in request,
        )


def success_response(context, data=None):
    response = {
        "type": context.response_type,
        "result": "success",
        "data": {} if data is None else data,
    }
    _add_request_id(response, context)
    return response


def fail_response(context, failure):
    response = {
        "type": context.response_type,
        "result": "fail",
        "failure": failure_value(failure),
    }
    _add_request_id(response, context)
    return response


def partial_fail_response(context, result: PartialFailure):
    failure = Failure(
        FailureCode.PARTIAL_FAILURE,
        "The operation completed for only some targets.",
        {
            "succeeded": list(result.succeeded),
            "failed": [
                {
                    "target": item.target,
                    "failure": failure_value(map_exception(item.exception)),
                }
                for item in result.failed
            ],
        },
    )
    return fail_response(context, failure)


def failure_value(failure: Failure):
    value = {
        "code": failure.code.value,
        "message": failure.message,
    }
    if failure.details is not None:
        value["details"] = failure.details
    return value


def _add_request_id(response, context):
    if context.has_request_id:
        response["request_id"] = context.request_id


def send_client_message(client, message):
    client["conn"].sendall((json.dumps(message) + "\n").encode("utf-8"))


def status_data(message):
    data = dict(message)
    data.pop("type", None)
    data.pop("ok", None)
    return data


def command_name(message):
    return str(message.get("cmd", message.get("type", ""))).strip()


def public_command_name(message):
    return command_name(message)


def reject_command_message(client, command, message):
    send_client_message(
        client,
        {
            "type": "command_rejected",
            "command": command,
            "message": message,
        },
    )


def axis_list_value(values, axis_index, default=None):
    return values[axis_index] if axis_index < len(values) else default


def motion_limits_api_values(motion_limits, state=None):
    return [
        float(
            motion_limits_drive_to_api(state, axis_index, axis_limits)[field_index]
            if state is not None
            else value
        )
        for axis_index, axis_limits in enumerate(motion_limits)
        for field_index, value in enumerate(axis_limits)
    ]


def profile_settings_api_values(profile_settings, state=None):
    return [
        float(
            profile_settings_drive_to_api(state, axis_index, axis_settings)[field_index]
            if state is not None
            else value
        )
        for axis_index, axis_settings in enumerate(profile_settings)
        for field_index, value in enumerate(axis_settings)
    ]


def software_position_limits_api_values(software_position_limits, state=None):
    return [
        float(
            axis_position_drive_to_api(state, axis_index, value)
            if state is not None
            else value
        )
        for axis_index, axis_limits in enumerate(software_position_limits)
        for value in axis_limits
    ]


def public_trajectory_state(state):
    trajectory = dict(state.get("trajectory", {}))
    axes = trajectory.get("axes", [])
    points = []
    for point in trajectory.get("points", []) or []:
        converted_point = dict(point)
        converted_point["positions"] = [
            axis_position_drive_to_api(state, axis_index, position)
            for axis_index, position in zip(axes, point.get("positions", []))
        ]
        points.append(converted_point)
    trajectory["points"] = points
    return trajectory


def public_axis_trajectory_state(state, axis_index):
    trajectory = dict(public_trajectory_state(state))
    axes = list(trajectory.get("axes", []))
    axis_index = int(axis_index)
    active_for_axis = bool(trajectory.get("active", False) and axis_index in axes)
    trajectory["axis"] = axis_index
    trajectory["active"] = active_for_axis

    if axis_index not in axes:
        trajectory["points"] = []
        return trajectory

    local_index = axes.index(axis_index)
    points = []
    for point in trajectory.get("points", []) or []:
        axis_point = dict(point)
        positions = list(point.get("positions", []))
        axis_point["position"] = (
            positions[local_index]
            if local_index < len(positions)
            else None
        )
        axis_point.pop("positions", None)
        points.append(axis_point)
    trajectory["points"] = points
    return trajectory


def public_homing_state(state):
    homing = dict(state["homing"])
    homing.pop("original_motion_modes", None)
    homing.pop("initial_referenced", None)
    homing.pop("referenced_seen_low", None)
    return homing


def public_axis_homing_state(state, axis_index):
    homing = dict(public_homing_state(state))
    axes = list(homing.get("axes", []))
    axis_index = int(axis_index)
    homing["axis"] = axis_index
    homing["active"] = bool(homing.get("active", False) and axis_index in axes)

    per_axis = {}
    for axis_state in homing.get("per_axis", []) or []:
        if int(axis_state.get("axis", -1)) == axis_index:
            per_axis = dict(axis_state)
            break
    homing["per_axis"] = per_axis
    return homing


def io_device_snapshot(device, include_raw=False):
    slave = device["slave"]
    rxpdo = slave.rxpdo
    txpdo = slave.txpdo
    config = rxpdo.config
    snapshot = {
        "id": device["id"],
        "slave_index": device["slave_index"],
        "profile": device["profile"],
        "input_bytes": txpdo.mapping_size(),
        "output_bytes": rxpdo.mapping_size(),
        "digital_inputs": flattened_digital_inputs(txpdo),
        "digital_outputs": flattened_digital_outputs(rxpdo),
        "analog_inputs": flattened_analog_inputs(txpdo),
        "analog_outputs": flattened_analog_outputs(rxpdo),
        "modules": [
            io_module_snapshot(module, rxpdo, txpdo)
            for module in config.layout.modules
        ],
    }
    if include_raw:
        snapshot["input_image"] = bytes(txpdo.payload).hex()
        snapshot["output_image"] = bytes(rxpdo.payload).hex()
    return snapshot


def io_module_snapshot(module, rxpdo, txpdo):
    data = module.to_dict()
    data["name"] = module_display_name(module)
    if module.input_bytes:
        data["inputs"] = io_module_input_values(module, txpdo)
    if module.output_bytes:
        data["outputs"] = io_module_output_values(module, rxpdo)
    return data


def io_module_input_values(module, txpdo):
    values = {}
    module_data = txpdo.module_inputs[module.slot]
    if module.digital_inputs:
        values["digital"] = list(module_data["digital"])
    if module.analog_inputs:
        values["analog"] = list(module_data["analog"])
    if module.module_type == "iol":
        payload = bytes(module_data["io_link"])
        values["io_link"] = payload.hex()
        values["io_link_channels"] = io_link_channel_payloads(
            payload,
            module.io_link_ports,
            module.io_link_input_data_bytes,
        )
        values["io_link_qualifiers"] = io_link_qualifiers(
            payload,
            module.io_link_input_data_bytes,
            module.io_link_ports,
        )
    return values


def io_module_output_values(module, rxpdo):
    values = {}
    module_data = rxpdo.module_outputs[module.slot]
    if module.digital_outputs:
        values["digital"] = list(module_data["digital"])
    if module.analog_outputs:
        values["analog"] = list(module_data["analog"])
    if module.module_type == "iol":
        payload = bytes(module_data["io_link"])
        values["io_link"] = payload.hex()
        values["io_link_channels"] = io_link_channel_payloads(
            payload,
            module.io_link_ports,
            module.io_link_output_data_bytes,
        )
    return values


def io_link_channel_payloads(payload, ports, data_bytes):
    ports = int(ports)
    data_bytes = int(data_bytes)
    if ports <= 0:
        return []
    bytes_per_port = data_bytes // ports
    channels = []
    for port in range(ports):
        start = port * bytes_per_port
        end = start + bytes_per_port
        channels.append({
            "port": port,
            "data": bytes(payload[start:end]).hex(),
        })
    return channels


def io_link_qualifiers(payload, data_bytes, ports):
    data_bytes = int(data_bytes)
    ports = int(ports)
    return [
        int(payload[data_bytes + port])
        if data_bytes + port < len(payload)
        else 0
        for port in range(ports)
    ]
