from types import SimpleNamespace
import unittest

from motion_server.runtime_logging import RuntimeLogger


class MemoryLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(message)


def logging_config(*, pre_enabled, length=3, command=True, status=True):
    return SimpleNamespace(
        pre_logging=SimpleNamespace(enabled=pre_enabled, length=length),
        command=SimpleNamespace(enabled=command),
        status=SimpleNamespace(enabled=status),
    )


class RuntimeLoggingTest(unittest.TestCase):
    def test_disabled_pre_logging_does_not_create_or_record_history(self):
        sink = MemoryLogger()
        logger = RuntimeLogger(
            logging_config(pre_enabled=False),
            logger=sink,
        )

        logger.record_snapshot({"sequence": 1})
        logger.event("fault")

        self.assertFalse(logger.history_enabled)
        self.assertEqual(logger.history, ())
        self.assertEqual(sink.messages, ["fault"])

    def test_enabled_pre_logging_keeps_bounded_history_for_events(self):
        sink = MemoryLogger()
        logger = RuntimeLogger(
            logging_config(pre_enabled=True, length=2),
            logger=sink,
        )

        logger.record_snapshot({"sequence": 1})
        logger.record_snapshot({"sequence": 2})
        logger.record_snapshot({"sequence": 3})
        logger.event("anomaly")

        self.assertEqual(
            logger.history,
            ({"sequence": 2}, {"sequence": 3}),
        )
        self.assertIn("PRE_HISTORY", sink.messages[0])
        self.assertNotIn("sequence': 1", sink.messages[0])

    def test_command_log_excludes_pre_history(self):
        sink = MemoryLogger()
        logger = RuntimeLogger(
            logging_config(pre_enabled=True),
            logger=sink,
        )
        logger.record_snapshot({"sequence": 1})

        logger.command("request")

        self.assertEqual(sink.messages, ["request"])


if __name__ == "__main__":
    unittest.main()
