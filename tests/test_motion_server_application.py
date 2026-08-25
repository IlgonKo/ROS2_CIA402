from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from configuration import ConfigurationSource
from motion_server.app.initialization import InitializationCause
from motion_server.application import MotionServerApplication
from tests.configuration_fixtures import TEST_NON_PDO_SELECTION


class MotionServerApplicationTest(unittest.TestCase):
    def make_source(self, root, *, port, period):
        root = Path(root)
        (root / ".env").write_text(
            "MOTION_SERVER_BACKEND=mock\n"
            "MOTION_SERVER_BUS=axis:cmmt_as\n"
            f"MOTION_SERVER_PORT={port}\n"
            f"PYSOEM_CYCLE_TIME={period}\n"
            f"{TEST_NON_PDO_SELECTION}",
            encoding="utf-8",
        )
        return ConfigurationSource(project_root=root)

    def test_two_applications_keep_independent_typed_configurations(self):
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = MotionServerApplication.from_source(
                self.make_source(first_dir, port=15001, period=0.01),
                environ={},
            )
            second = MotionServerApplication.from_source(
                self.make_source(second_dir, port=15002, period=0.02),
                environ={},
            )

        self.assertEqual(first.config.server.port, 15001)
        self.assertEqual(second.config.server.port, 15002)
        self.assertEqual(first.config.ethercat.cycle.period, 0.01)
        self.assertEqual(second.config.ethercat.cycle.period, 0.02)

    def test_run_delegates_without_passing_application_to_runner(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            application = MotionServerApplication.from_source(
                self.make_source(temp_dir, port=15003, period=0.01),
                environ={},
            )

        received = {}

        def runner(*, diagnostic_manager, **dependencies):
            received.update(dependencies)
            received["diagnostic_manager"] = diagnostic_manager
            return "stopped"

        self.assertEqual(application.run(runner=runner), "stopped")
        self.assertEqual(received["server_config"].port, 15003)
        self.assertNotIn("config", received)
        self.assertNotIn("application", received)

    def test_invalid_full_configuration_keeps_bootstrap_port_and_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self.make_source(temp_dir, port=15123, period=0.01)
            with (Path(temp_dir) / ".env").open("a", encoding="utf-8") as stream:
                stream.write("MOTION_SERVER_CSP_VELOCITY_OFFSET=invalid\n")

            application = MotionServerApplication.from_source(source, environ={})

        self.assertEqual(application.bootstrap_config.port, 15123)
        self.assertIsNone(application.config)
        self.assertFalse(application.initialization_status.initialized)
        self.assertIs(
            application.initialization_status.failure.cause,
            InitializationCause.CONFIGURATION_INVALID,
        )
        self.assertIsInstance(application.initialization_exception, ValueError)

        received = {}

        def degraded_runner(**dependencies):
            received.update(dependencies)
            return "degraded"

        self.assertEqual(application.run(runner=degraded_runner), "degraded")
        self.assertEqual(received["bootstrap_config"].port, 15123)
        self.assertIs(
            received["initialization_status"],
            application.initialization_status,
        )
        self.assertNotIn("server_config", received)

    def test_invalid_bootstrap_port_fails_before_application_is_created(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self.make_source(temp_dir, port=70000, period=0.01)

            with self.assertRaisesRegex(ValueError, "port must be in range"):
                MotionServerApplication.from_source(source, environ={})

    def test_application_reads_project_configuration_file_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self.make_source(temp_dir, port=15004, period=0.01)
            project_path = (Path(temp_dir) / ".env").resolve()
            from configuration import loader

            original = loader.read_key_value_config
            project_reads = []

            def tracked_read(path):
                if Path(path).resolve() == project_path:
                    project_reads.append(Path(path).resolve())
                return original(path)

            with patch(
                "configuration.loader.read_key_value_config",
                side_effect=tracked_read,
            ):
                application = MotionServerApplication.from_source(
                    source,
                    environ={},
                )

        self.assertIsNotNone(application.config)
        self.assertEqual(project_reads, [project_path])

    def test_bootstrap_and_full_config_use_same_port_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self.make_source(temp_dir, port=15005, period=0.01)
            application = MotionServerApplication.from_source(
                source,
                argv=["--port", "16005"],
                environ={},
            )

        self.assertEqual(application.bootstrap_config.port, 16005)
        self.assertEqual(application.config.server.port, 16005)


if __name__ == "__main__":
    unittest.main()
