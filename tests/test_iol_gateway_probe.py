from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import unittest
from unittest.mock import Mock

from motion_server.failure import SdoObjectNotFoundException
from scripts.diagnostics.iol_gateway_probe import probe, run_pending_probe


class GatewayProbeTest(unittest.TestCase):
    def runtime(self, reader):
        return SimpleNamespace(
            ethercat_master=SimpleNamespace(read_sdo=reader),
            device_manager=SimpleNamespace(io=SimpleNamespace(slave_index=lambda io: 1)),
        )

    def test_only_two_fixed_reads_and_original_abort(self):
        original = RuntimeError("SDO abort")
        original.abort_code = 0x06090011
        mapped = SdoObjectNotFoundException(0x2001, 2)
        mapped.__cause__ = original
        reader = Mock(side_effect=[mapped, b"\x01"])
        report = probe(self.runtime(reader))
        self.assertEqual(reader.call_args_list[0].args, (1, 0x2001, 2, 1))
        self.assertEqual(reader.call_args_list[1].args, (1, 0x2021, 2, 1))
        self.assertEqual(reader.call_count, 2)
        self.assertEqual(report["reads"][0]["abort_code"], "0x06090011")
        self.assertEqual(report["reads"][1]["value"], 1)

    def test_marker_consumed_once(self):
        with TemporaryDirectory() as directory:
            request = Path(directory) / "request"
            result = Path(directory) / "result.json"
            reader = Mock(return_value=b"\0")
            runtime = self.runtime(reader)
            run_pending_probe(runtime, request_path=request, result_path=result)
            reader.assert_not_called()
            request.touch()
            run_pending_probe(runtime, request_path=request, result_path=result)
            self.assertFalse(request.exists())
            self.assertEqual(len(json.loads(result.read_text())["reads"]), 2)
            run_pending_probe(runtime, request_path=request, result_path=result)
            self.assertEqual(reader.call_count, 2)

    def test_short_response_is_not_success(self):
        report = probe(self.runtime(Mock(return_value=b"")))
        self.assertTrue(all(item["result"] == "invalid_length" for item in report["reads"]))


if __name__ == "__main__":
    unittest.main()
