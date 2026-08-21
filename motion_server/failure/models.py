from dataclasses import dataclass

from motion_server.failure.codes import FailureCode


@dataclass(frozen=True)
class Failure:
    code: FailureCode
    message: str
    details: dict[str, object] | None = None
