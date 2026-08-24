import importlib
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import motion_server.application
import motion_server.server
from configuration import ConfigurationSource
from motion_server.application import MotionServerApplication


class ImportIsolationTest(unittest.TestCase):
    def test_legacy_global_configuration_symbols_are_absent(self):
        project_root = Path(__file__).resolve().parents[1]
        self.assertFalse((project_root / "motion_server" / "config.py").exists())
        patterns = (
            r"\bactive_configuration\b",
            r"\bset_active_configuration\b",
            r"\bDEVICE_PROFILE\b",
            r"motion_server\.config",
        )
        violations = []
        for root_name in ("configuration", "motion_server", "packaging"):
            for path in (project_root / root_name).rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                for pattern in patterns:
                    if re.search(pattern, text):
                        violations.append(
                            f"{path.relative_to(project_root)}: {pattern}"
                        )
        self.assertEqual(violations, [])

    def test_motion_server_module_reload_does_not_load_files_or_mutate_environment(self):
        before = dict(os.environ)
        with patch(
            "configuration.file_parser.read_key_value_config",
            side_effect=AssertionError("module import must not load configuration files"),
        ):
            importlib.reload(motion_server.application)
            importlib.reload(motion_server.server)
        self.assertEqual(dict(os.environ), before)

    def test_cli_only_overrides_explicit_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".env").write_text(
                "MOTION_SERVER_BACKEND=mock\n"
                "MOTION_SERVER_BUS=axis:cmmt_as\n"
                "MOTION_SERVER_PORT=15001\n"
                "PYSOEM_CYCLE_TIME=0.01\n",
                encoding="utf-8",
            )
            application = MotionServerApplication.from_source(
                ConfigurationSource(project_root=root),
                argv=["--port", "16001"],
                environ={},
            )

        self.assertEqual(application.config.server.port, 16001)
        self.assertEqual(application.config.ethercat.cycle.period, 0.01)
        self.assertEqual(application.config.ethercat.backend.value, "mock")


if __name__ == "__main__":
    unittest.main()
