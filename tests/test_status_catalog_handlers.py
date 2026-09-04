import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from motion_server.api.router import request_response
from motion_server.failure import InvalidRequestException, ResourceNotFoundException
from motion_server.handlers.status.axis_parameter_catalog import (
    axis_param_catalog_data,
)
from motion_server.handlers.status.io_ethercat_parameter_catalog import (
    ethercat_param_catalog_data,
)
from motion_server.handlers.status.io_iol_parameter_catalog import (
    iol_param_catalog_data,
)
from motion_server.handlers.status.registry import (
    handle_axis_status,
    handle_server_status,
)
from motion_server.app.initialization import (
    INITIALIZATION_CAUSE_DEFINITIONS,
    InitializationCause,
    InitializationFailure,
    InitializationStatus,
)
from motion_server.diagnostic import DiagnosticManager
from motion_server.app.session import ServerSession
from datetime import datetime, timezone


class Connection:
    def __init__(self):
        self.messages = []

    def sendall(self, payload):
        self.messages.append(json.loads(payload.decode()))


class IoGroup:
    def __init__(self, device=None):
        self.device = device

    def selected_device(self, io_id=None, slave_index=None):
        if self.device is None or io_id not in (None, self.device["id"]):
            raise ValueError("private lookup detail")
        return self.device


def client():
    return {"id": "test", "conn": Connection()}


def axis_catalog_runtime(catalog):
    profile = SimpleNamespace(name="axis-profile", esi_catalog=catalog)
    device = SimpleNamespace(device_profile=profile)
    axes = SimpleNamespace(
        devices=[device],
        axis_bindings=[SimpleNamespace(slave_index=3)],
    )
    return SimpleNamespace(device_manager=SimpleNamespace(axes=axes))


class StatusBoundaryTest(unittest.TestCase):
    def test_server_status_returns_operation_data(self):
        runtime = SimpleNamespace(slaves=[object()], cycle_time=0.008)
        active_client = client()

        cause = InitializationCause.BUS_CONNECTION_FAILED
        definition = INITIALIZATION_CAUSE_DEFINITIONS[cause]
        status = InitializationStatus.failed(InitializationFailure(
            stage=definition.stage,
            cause=cause,
            message=definition.message,
            occurred_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
        ))
        session = ServerSession(status)
        response = handle_server_status(
            "system/server/status",
            {"type": "system/server/status", "request_id": "r1"},
            runtime,
            {
                "initialization_status": status,
                "diagnostic_manager": DiagnosticManager(),
                "server_session": session,
            },
            active_client,
        )

        self.assertNotIn("type", response)
        self.assertFalse(response["initialized"])
        self.assertEqual(response["runtime_state"], "initialization_error")
        self.assertEqual(
            response["initialization_failure"]["cause"],
            "bus_connection_failed",
        )
        self.assertEqual(active_client["conn"].messages, [])

    def test_axis_status_missing_selector_is_safe_invalid_request(self):
        active_client = client()

        with self.assertRaises(InvalidRequestException):
            handle_axis_status(
                "system/axis/status",
                {"type": "system/axis/status"},
                SimpleNamespace(),
                {},
                active_client,
            )

    def test_axis_status_unknown_axis_is_resource_not_found(self):
        active_client = client()
        runtime = SimpleNamespace(slaves=[])

        with self.assertRaises(ResourceNotFoundException):
            handle_axis_status(
                "system/axis/status",
                {"type": "system/axis/status", "axis": 5},
                runtime,
                {},
                active_client,
            )


class CatalogBoundaryTest(unittest.TestCase):
    def test_axis_catalog_success_preserves_catalog_data(self):
        catalog = SimpleNamespace(
            path=Path("axis.xml"),
            root_object_infos=lambda: [],
        )

        data = axis_param_catalog_data(
            {"axis": 0},
            axis_catalog_runtime(catalog),
        )

        self.assertEqual(data["axis"], 0)
        self.assertEqual(data["profile"], "axis-profile")
        self.assertEqual(data["objects"], [])
        self.assertNotIn("ok", data)

    def test_catalog_runtime_not_ready_is_server_not_ready(self):
        response = request_response(
            {"type": "system/axis/param_catalog"},
            lambda: axis_param_catalog_data({"axis": 0}, SimpleNamespace()),
        )

        self.assertEqual(response["failure"]["code"], "SERVER_NOT_READY")

    def test_unknown_io_is_resource_not_found_without_lookup_detail(self):
        runtime = SimpleNamespace(
            device_manager=SimpleNamespace(io=IoGroup()),
        )

        response = request_response(
            {"type": "system/io/ethercat/param_catalog"},
            lambda: ethercat_param_catalog_data({"io": "missing"}, runtime),
        )

        self.assertEqual(response["failure"]["code"], "RESOURCE_NOT_FOUND")
        self.assertNotIn("private lookup detail", str(response))

    def test_ethercat_catalog_success_has_domain_data_only(self):
        config = SimpleNamespace(layout=SimpleNamespace(modules=[]))
        device = {
            "id": "io0",
            "slave_index": 2,
            "slave": SimpleNamespace(
                device_profile=SimpleNamespace(config=config),
            ),
        }
        runtime = SimpleNamespace(
            device_manager=SimpleNamespace(io=IoGroup(device)),
        )
        catalog = SimpleNamespace(
            path=Path("io.xml"),
            objects={
                (0x1000, 0): SimpleNamespace(
                    index=0x1000,
                    name="Device type",
                    data_type="U32",
                    bit_size=32,
                    access="ro",
                    depend_on_slot=False,
                    subitems=(),
                ),
                (0x1001, 0): SimpleNamespace(
                    index=0x1001,
                    name="Error register",
                    data_type="U8",
                    bit_size=8,
                    access="ro",
                    depend_on_slot=False,
                    subitems=(),
                ),
                (0x1018, 1): SimpleNamespace(
                    index=0x1018,
                    name="Vendor ID",
                    data_type="U32",
                    bit_size=32,
                    access="ro",
                    depend_on_slot=False,
                    subitems=(),
                ),
            },
        )

        with patch(
            "motion_server.handlers.status.io_ethercat_parameter_catalog."
            "esi_module_catalog",
            return_value=catalog,
        ):
            data = ethercat_param_catalog_data({"io": "io0"}, runtime)

        self.assertEqual(data["io"], "io0")
        self.assertEqual(
            [obj["index_hex"] for obj in data["objects"]],
            ["0x1000", "0x1001"],
        )
        self.assertEqual(
            [obj["group"] for obj in data["objects"]],
            ["station", "diagnosis"],
        )
        self.assertEqual(data["scope"], "station")
        self.assertNotIn("module", data)
        self.assertNotIn("type", data)
        self.assertNotIn("ok", data)

    def test_ethercat_catalog_rejects_module_selector(self):
        response = request_response(
            {"type": "system/io/ethercat/param_catalog"},
            lambda: ethercat_param_catalog_data(
                {"io": "io0", "module": 1},
                SimpleNamespace(),
            ),
        )

        self.assertEqual(response["failure"]["code"], "INVALID_ARGUMENT")

    def test_iol_missing_port_is_invalid_argument(self):
        response = request_response(
            {"type": "system/io/iol/param_catalog"},
            lambda: iol_param_catalog_data(
                {"io": "io0", "module": 1},
                SimpleNamespace(),
            ),
        )

        self.assertEqual(response["failure"]["code"], "INVALID_ARGUMENT")

    def test_iol_catalog_uses_configured_module_stride_for_object_index(self):
        binding = SimpleNamespace(
            module=1,
            port=1,
            process_data_size=(2, 1),
            process_data_profile=SimpleNamespace(
                condition_value=2,
                profile_id="P",
            ),
            device=SimpleNamespace(
                key="sensor",
                path=Path("sensor.xml"),
                vendor_id=1,
                device_id=2,
                vendor_name="Vendor",
                device_name="Sensor",
                variables=[],
            ),
        )
        config = SimpleNamespace(
            layout=SimpleNamespace(modules=[]),
            io_link_devices=[binding],
            module_pdo_index_stride=0x10,
        )
        device = {
            "id": "io0",
            "slave_index": 4,
            "slave": SimpleNamespace(
                device_profile=SimpleNamespace(config=config),
            ),
        }
        runtime = SimpleNamespace(
            device_manager=SimpleNamespace(io=IoGroup(device)),
        )
        info = SimpleNamespace(
            has_isdu_access=True,
            type_name="CPX-AP-I-4IOL-M12",
        )
        catalog = SimpleNamespace(path=Path("io.xml"))

        with patch(
            "motion_server.handlers.status.io_iol_parameter_catalog."
            "module_info_for_ap_module",
            return_value=info,
        ), patch(
            "motion_server.handlers.status.io_iol_parameter_catalog."
            "esi_module_catalog",
            return_value=catalog,
        ):
            data = iol_param_catalog_data(
                {"io": "io0", "module": 1, "port": 1},
                runtime,
            )

        self.assertEqual(data["object_index"], "0x2011")

    def test_unexpected_catalog_error_is_hidden(self):
        catalog = SimpleNamespace(
            path=Path("axis.xml"),
            root_object_infos=lambda: (_ for _ in ()).throw(
                RuntimeError("private catalog failure"),
            ),
        )

        response = request_response(
            {"type": "system/axis/param_catalog"},
            lambda: axis_param_catalog_data(
                {"axis": 0},
                axis_catalog_runtime(catalog),
            ),
        )

        self.assertEqual(response["failure"]["code"], "INTERNAL_FAILURE")
        self.assertNotIn("private catalog failure", str(response))


if __name__ == "__main__":
    unittest.main()
