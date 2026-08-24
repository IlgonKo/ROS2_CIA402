import importlib
import os
from pathlib import Path
import re
import subprocess
import sys
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

    def test_fresh_process_import_does_not_load_configuration(self):
        project_root = Path(__file__).resolve().parents[1]
        script = r'''
import os
import sys

before = dict(os.environ)
def audit(event, args):
    if event != "open" or not args:
        return
    path = str(args[0]).replace("\\", "/").lower()
    if path.endswith("/.env") or path.endswith("/config.txt"):
        raise AssertionError(f"module import read configuration file: {path}")
sys.addaudithook(audit)
import motion_server.application
import motion_server.server
assert dict(os.environ) == before
'''
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_windows_script_uses_application_entrypoint(self):
        project_root = Path(__file__).resolve().parents[1]
        script = (project_root / "scripts" / "windows" / "motion_server.ps1")
        text = script.read_text(encoding="utf-8")

        self.assertIn('"-m",', text)
        self.assertIn('"motion_server",', text)
        self.assertNotIn('motion_server\\server.py', text)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell regression test")
    def test_windows_env_loader_works_outside_project_directory(self):
        project_root = Path(__file__).resolve().parents[1]
        env_script = project_root / "scripts" / "windows" / "env.ps1"
        command = (
            f". '{env_script}'; "
            f"$values = Import-AxisServerEnv -ProjectRoot '{project_root}' "
            f"-Python '{sys.executable}'; "
            "Write-Output $values['MOTION_SERVER_BACKEND']"
        )
        with tempfile.TemporaryDirectory() as outside_dir:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                cwd=outside_dir,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mock", result.stdout)

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
