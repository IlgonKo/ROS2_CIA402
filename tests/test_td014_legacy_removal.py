from dataclasses import fields
from pathlib import Path
import unittest

from configuration.bus import BusDevice


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    PROJECT_ROOT / "configuration",
    PROJECT_ROOT / "control_panel",
    PROJECT_ROOT / "device",
    PROJECT_ROOT / "motion_server",
)
FORBIDDEN_IDENTIFIERS = (
    "derived_velocity",
    "MOTION_SERVER_DERIVED_VELOCITY_ALPHA",
    "MOCK_AXIS_TYPES",
    "MOCK_AXIS_USER_UNITS",
    "mock_axis_types",
    "mock_axis_user_units",
    "configured_index",
)


class Td014LegacyRemovalTest(unittest.TestCase):
    def test_removed_runtime_and_configuration_identifiers_do_not_return(self):
        paths = [
            path
            for root in SOURCE_ROOTS
            for path in root.rglob("*.py")
        ]
        paths.extend((
            PROJECT_ROOT / ".env.example",
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "motion_server" / "start_server.sh",
            PROJECT_ROOT / "scripts" / "host" / "start.sh",
        ))

        violations = []
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for identifier in FORBIDDEN_IDENTIFIERS:
                if identifier in text:
                    violations.append(f"{path.relative_to(PROJECT_ROOT)}: {identifier}")
        self.assertEqual(violations, [])

    def test_bus_device_keeps_only_runtime_slave_index(self):
        self.assertEqual(
            [field.name for field in fields(BusDevice)],
            ["slave_index", "role", "profile", "logical_id"],
        )


if __name__ == "__main__":
    unittest.main()
