from collections import deque
import logging
import sys


class RuntimeLogger:
    """Runtime-owned logging policy and optional pre-event history."""

    def __init__(self, config, *, logger=None):
        self.config = config
        self._logger = logger or self._default_logger()
        self._history = (
            deque(maxlen=config.pre_logging.length)
            if config.pre_logging.enabled
            else None
        )

    @staticmethod
    def _default_logger():
        logger = logging.getLogger("motion_server.runtime")
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        return logger

    @property
    def history_enabled(self):
        return self._history is not None

    @property
    def history(self):
        return () if self._history is None else tuple(self._history)

    def record_snapshot(self, snapshot):
        if self._history is not None:
            self._history.append(snapshot)

    def info(self, message):
        self._logger.info(message)

    def status(self, message):
        if self.config.status.enabled:
            self.event(message)

    def command(self, message):
        if self.config.command.enabled:
            self.info(message)

    def event(self, message, *, include_history=True):
        if include_history and self._history:
            message = f"{message} PRE_HISTORY={list(self._history)}"
        self.info(message)
