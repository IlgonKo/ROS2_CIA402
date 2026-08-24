import unittest
from types import SimpleNamespace
from unittest.mock import patch

from motion_server.api.router import request_response
from motion_server.failure import (
    AuthorityRequiredException,
    DeviceAccessException,
    InvalidStateException,
    ItemFailure,
    LimitViolationException,
    PartialFailure,
    OperationTimeoutException,
)
from motion_server.handlers.command.axis_state import enable, set_axes_controlword
from motion_server.handlers.command.io_output_write import write_outputs
from motion_server.control.setpoint_output import pp_setpoint_handshake


class ControlwordPdo:
    def __init__(self, exception=None):
        self._controlword = 0
        self.exception = exception

    @property
    def controlword(self):
        return self._controlword

    @controlword.setter
    def controlword(self, value):
        if self.exception is not None:
            raise self.exception
        self._controlword = value


class DigitalOutputPdo:
    def __init__(self, failing_channels=()):
        self.failing_channels = set(failing_channels)
        self.values = {}

    def set_module_digital_output(self, slot, channel, value):
        if channel in self.failing_channels:
            raise OSError("private device detail")
        self.values[(slot, channel)] = value


class IoGroup:
    def __init__(self, rxpdo):
        self.device = {
            "id": "io0",
            "slave_index": 2,
            "profile": "test",
            "slave": SimpleNamespace(rxpdo=rxpdo),
        }

    def selected_device(self, io_id=None, slave_index=None):
        if io_id not in (None, "io0") and slave_index != 2:
            raise ValueError("unknown")
        return self.device


def axis_runtime(*exceptions):
    return SimpleNamespace(
        slaves=[
            SimpleNamespace(rxpdo=ControlwordPdo(exception))
            for exception in exceptions
        ],
    )


def io_runtime(rxpdo):
    return SimpleNamespace(
        device_manager=SimpleNamespace(io=IoGroup(rxpdo)),
    )


class AxisCommandFailureTest(unittest.TestCase):
    def test_all_axes_success_preserves_order(self):
        runtime = axis_runtime(None, None)

        result = set_axes_controlword(runtime, [1, 0], 0x000F)

        self.assertEqual(result, [1, 0])
        self.assertEqual(runtime.slaves[0].rxpdo.controlword, 0x000F)
        self.assertEqual(runtime.slaves[1].rxpdo.controlword, 0x000F)

    def test_all_axes_fail_maps_first_expected_failure(self):
        runtime = axis_runtime(OSError("axis zero"), OSError("axis one"))

        with self.assertRaises(DeviceAccessException):
            set_axes_controlword(runtime, [0, 1], 0x000F)

    def test_partial_axis_failure_uses_safe_target_failures(self):
        runtime = axis_runtime(None, OSError("secret"), None)

        response = request_response(
            {"type": "system/axes/enable"},
            lambda: set_axes_controlword(runtime, [0, 1, 2], 0x000F),
        )

        self.assertEqual(response["failure"]["code"], "PARTIAL_FAILURE")
        details = response["failure"]["details"]
        self.assertEqual(details["succeeded"], [0, 2])
        self.assertEqual(details["failed"][0]["target"], 1)
        self.assertEqual(
            details["failed"][0]["failure"]["code"],
            "DEVICE_ACCESS_FAILED",
        )
        self.assertNotIn("secret", str(response))

    def test_live_enable_preserves_partial_failure_result(self):
        result = PartialFailure(
            succeeded=[0],
            failed=[ItemFailure(1, DeviceAccessException("controlword_write"))],
        )
        runtime = SimpleNamespace(slaves=[object(), object()])

        with patch(
            "motion_server.handlers.command.axis_state.set_axes_controlword",
            return_value=result,
        ):
            response = request_response(
                {"type": "system/axes/enable"},
                lambda: enable(
                    {"type": "system/axes/enable", "axes": [0, 1]},
                    runtime,
                    {},
                    {"id": "client-1"},
                ),
            )

        self.assertEqual(response["failure"]["code"], "PARTIAL_FAILURE")
        self.assertEqual(response["failure"]["details"]["succeeded"], [0])

    def test_whole_request_failures_keep_their_contract_codes(self):
        cases = (
            (AuthorityRequiredException(), "AUTHORITY_REQUIRED"),
            (InvalidStateException("axis_move", "disabled"), "INVALID_STATE"),
            (LimitViolationException("position", 11, maximum=10), "LIMIT_VIOLATION"),
        )
        for exception, code in cases:
            with self.subTest(code=code):
                response = request_response(
                    {"type": "system/axis/move_abs"},
                    lambda exception=exception: (_ for _ in ()).throw(exception),
                )
                self.assertEqual(response["failure"]["code"], code)

    def test_pp_handshake_timeout_uses_timeout_contract(self):
        runtime = SimpleNamespace(
            cycle_time=0.008,
            slaves=[SimpleNamespace(
                rxpdo=ControlwordPdo(),
                txpdo=SimpleNamespace(statusword=0),
            )],
        )

        with patch(
            "motion_server.control.setpoint_output.wait_pp_setpoint_ack",
            return_value=False,
        ), patch(
            "motion_server.control.setpoint_output.diagnostics_summary",
            return_value={},
        ):
            with self.assertRaises(OperationTimeoutException):
                pp_setpoint_handshake(runtime, [0])


class IoCommandFailureTest(unittest.TestCase):
    def batch_message(self):
        return {
            "type": "system/io/output_write",
            "io": "io0",
            "kind": "digital",
            "slot": 1,
            "writes": [
                {"channel": 0, "value": True},
                {"channel": 1, "value": False},
                {"channel": 2, "value": True},
            ],
        }

    def test_multiple_outputs_succeed_in_request_order(self):
        pdo = DigitalOutputPdo()

        result = write_outputs(self.batch_message(), io_runtime(pdo))

        self.assertEqual([target["channel"] for target in result], [0, 1, 2])
        self.assertEqual(pdo.values[(1, 1)], False)

    def test_all_outputs_fail_as_one_expected_failure(self):
        pdo = DigitalOutputPdo({0, 1, 2})

        with self.assertRaises(DeviceAccessException):
            write_outputs(self.batch_message(), io_runtime(pdo))

    def test_partial_output_failure_is_safe_and_target_specific(self):
        pdo = DigitalOutputPdo({1})

        response = request_response(
            self.batch_message(),
            lambda: write_outputs(self.batch_message(), io_runtime(pdo)),
        )

        self.assertEqual(response["failure"]["code"], "PARTIAL_FAILURE")
        details = response["failure"]["details"]
        self.assertEqual(
            [target["channel"] for target in details["succeeded"]],
            [0, 2],
        )
        self.assertEqual(details["failed"][0]["target"]["channel"], 1)
        self.assertNotIn("private device detail", str(response))


if __name__ == "__main__":
    unittest.main()
