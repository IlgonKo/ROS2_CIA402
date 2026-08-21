from dataclasses import dataclass

from motion_server.failure.exceptions import MotionServerException


@dataclass(frozen=True)
class ItemFailure:
    target: object
    exception: MotionServerException


@dataclass(frozen=True)
class PartialFailure:
    succeeded: list[object]
    failed: list[ItemFailure]
