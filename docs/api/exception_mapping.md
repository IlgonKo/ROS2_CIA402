# Exception과 API Failure Mapping

## 목적

예상 가능한 내부 실패는 의미가 명확한 Exception으로 전달하고 API 최상위 boundary에서 공통
Failure로 변환한다. 내부 계층은 API code 문자열을 직접 알지 않는다.

## 구성

```text
MotionServerException 계층
          ↓
ExceptionFailureMapping table
          ↓
FailureMapper
          ↓
API Fail response
```

### Exception 명명

내부 예외 class는 `Error`가 아니라 `Exception` suffix를 사용한다.

```text
MotionServerException
├─ RequestException
│  ├─ InvalidRequestException
│  ├─ UnknownCommandException
│  ├─ UnsupportedOperationException
│  ├─ InvalidArgumentException
│  └─ ResourceNotFoundException
├─ AuthorityException
│  ├─ AuthorityRequiredException
│  ├─ AuthorityBusyException
│  └─ PermissionDeniedException
├─ StateException
│  ├─ ServerNotReadyException
│  ├─ InvalidStateException
│  ├─ OperationConflictException
│  ├─ OperationBlockedException
│  └─ LimitViolationException
├─ CommunicationException
│  └─ CommunicationTimeoutException
├─ DeviceException
│  ├─ DeviceAccessException
│  └─ DeviceRejectedException
└─ OperationException
   └─ OperationTimeoutException
```

상위 Exception은 catch와 fallback mapping 경계다. 발생 위치에서 의미를 구분할 수 있으면 구체
Exception을 사용하고, 모든 failure code를 기계적으로 Exception과 1:1로 만들지는 않는다.

### FailureCode

`FailureCode`는 [Failure Code](failure_codes.md)의 안정적인 code를 나타내는 string Enum이다.
유효한 code 집합은 Enum이 보장한다.

### ExceptionFailureMapping

Exception type과 failure code 및 안전한 기본 message를 하나의 중앙 table에서 연결한다.

```python
@dataclass(frozen=True)
class ExceptionFailureMapping:
    code: FailureCode
    default_message: str


EXCEPTION_FAILURE_MAPPINGS = {
    InvalidRequestException: ExceptionFailureMapping(
        code=FailureCode.INVALID_REQUEST,
        default_message="The request is invalid.",
    ),
    CommunicationException: ExceptionFailureMapping(
        code=FailureCode.COMMUNICATION_FAILED,
        default_message="Communication failed.",
    ),
}
```

| Exception | FailureCode |
| --- | --- |
| `RequestException` | `INVALID_REQUEST` |
| `InvalidRequestException` | `INVALID_REQUEST` |
| `UnknownCommandException` | `UNKNOWN_COMMAND` |
| `UnsupportedOperationException` | `UNSUPPORTED_OPERATION` |
| `InvalidArgumentException` | `INVALID_ARGUMENT` |
| `ResourceNotFoundException` | `RESOURCE_NOT_FOUND` |
| `AuthorityException` | `PERMISSION_DENIED` |
| `AuthorityRequiredException` | `AUTHORITY_REQUIRED` |
| `AuthorityBusyException` | `AUTHORITY_BUSY` |
| `PermissionDeniedException` | `PERMISSION_DENIED` |
| `StateException` | `INVALID_STATE` |
| `ServerNotReadyException` | `SERVER_NOT_READY` |
| `InvalidStateException` | `INVALID_STATE` |
| `OperationConflictException` | `OPERATION_CONFLICT` |
| `OperationBlockedException` | `OPERATION_BLOCKED` |
| `LimitViolationException` | `LIMIT_VIOLATION` |
| `CommunicationException` | `COMMUNICATION_FAILED` |
| `CommunicationTimeoutException` | `TIMEOUT` |
| `DeviceException` | `DEVICE_ACCESS_FAILED` |
| `DeviceAccessException` | `DEVICE_ACCESS_FAILED` |
| `DeviceRejectedException` | `DEVICE_REJECTED` |
| `OperationException` | `OPERATION_FAILED` |
| `OperationTimeoutException` | `TIMEOUT` |
| 미등록 Exception | `INTERNAL_FAILURE` |

별도의 `FailureDefinitionRegistry`는 두지 않는다. 현재 필요한 유효 code 검증은 `FailureCode`가,
기본 message는 mapping table이 담당한다. retry 가능 여부나 localization 같은 공통 metadata가
실제로 필요해질 때만 별도 registry 도입을 다시 검토한다.

### FailureMapper

mapper는 다음 우선순위로 mapping을 선택한다.

```text
정확한 Exception type
→ 가장 가까운 등록 상위 Exception type
→ INTERNAL_FAILURE
```

예상하지 못한 Exception은 고정된 `INTERNAL_FAILURE`와 안전한 message로 변환한다. 원래 Exception,
stack trace와 외부에 노출하면 안 되는 상세정보는 서버 log에만 남긴다.

## Exception 데이터와 원인 보존

공통 base에 자유 형식의 public `message`, `details` 또는 `cause`를 두지 않는다. 구체 Exception은
해당 실패에 필요한 구조화 속성만 명시하고 mapper가 허용한 속성만 API details로 변환한다.

```python
class ResourceNotFoundException(RequestException):
    def __init__(self, resource_type: str, resource_id: object):
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(f"{resource_type} not found: {resource_id}")
```

저수준 원인은 별도 필드가 아니라 Python exception chaining으로 보존한다.

```python
try:
    ...
except OSError as exc:
    raise CommunicationException() from exc
```

`__cause__`와 내부 Exception 문자열은 log에만 사용하고 API에 직접 노출하지 않는다.

## Partial Failure

`PARTIAL_FAILURE`와 `INTERNAL_FAILURE`에 대응하는 Exception class는 만들지 않는다.

여러 대상 중 일부만 실패한 경우는 하나의 예외가 아니라 실행 결과 집계이므로 별도 객체로 표현한다.

```python
@dataclass
class ItemFailure:
    target: object
    exception: MotionServerException


@dataclass
class PartialFailure:
    succeeded: list[object]
    failed: list[ItemFailure]
```

상위 작업은 대상별 성공과 실패를 모두 수집한다. mapper는 각 `ItemFailure.exception`을 개별 code로
변환하고 전체 Fail response의 code를 `PARTIAL_FAILURE`로 설정한다. `INTERNAL_FAILURE`는 미등록
Exception의 fallback으로만 생성한다.

## 변환 경계

- 하위 계층은 예상 가능한 실패만 `MotionServerException` 하위 type으로 발생시킨다.
- programming error는 중간 계층의 broad catch로 숨기지 않는다.
- API 최상위 boundary가 Exception을 한 번 catch하여 `FailureMapper`로 변환한다.
- mapper가 허용한 안전한 message와 details만 Fail response에 포함한다.
- 운전 상태에도 영향이 있으면 API Fail과 별도로 Diagnostic을 생성한다.

## 후속 구현 범위

- 기존 handler별 catch를 최상위 boundary로 이동하는 migration 범위
- Exception별 구조화 속성과 API details allowlist
- mapping table의 누락·중복·상속 우선순위 자동 검증
