from pathlib import Path
import tempfile
import unittest

from configuration import ConfigurationSource
from motion_server.application import MotionServerApplication


class MotionServerApplicationTest(unittest.TestCase):
    def make_source(self, root, *, port, period):
        root = Path(root)
        (root / ".env").write_text(
            "MOTION_SERVER_BACKEND=mock\n"
            "MOTION_SERVER_BUS=axis:cmmt_as\n"
            f"MOTION_SERVER_PORT={port}\n"
            f"PYSOEM_CYCLE_TIME={period}\n",
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


if __name__ == "__main__":
    unittest.main()
