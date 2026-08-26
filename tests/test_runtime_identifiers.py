from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RuntimeIdentifierTest(unittest.TestCase):
    def test_systemd_unit_defers_compose_env_path_to_runtime_shell(self):
        service_script = (
            PROJECT_ROOT / "scripts" / "host" / "service.sh"
        ).read_text(encoding="utf-8")

        self.assertNotIn(r'"\${COMPOSE_ENV_FILE}"', service_script)
        self.assertEqual(
            service_script.count(r'"\$(prepare_compose_env_file ${PROJECT_ROOT})"'),
            2,
        )


if __name__ == "__main__":
    unittest.main()
