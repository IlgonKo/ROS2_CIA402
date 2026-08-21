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


def collect_target_results(targets, operation):
    succeeded = []
    failed = []
    for target in targets:
        try:
            operation(target)
        except MotionServerException as exception:
            failed.append(ItemFailure(target=target, exception=exception))
        else:
            succeeded.append(target)

    if not failed:
        return succeeded
    if not succeeded:
        raise failed[0].exception
    return PartialFailure(succeeded=succeeded, failed=failed)
