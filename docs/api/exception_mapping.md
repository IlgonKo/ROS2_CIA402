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
├─ AuthorityException
├─ StateException
├─ CommunicationException
└─ DeviceAccessException
```

구체적인 하위 Exception 목록은 inventory 분류 전에 별도로 확정한다.

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

## 변환 경계

- 하위 계층은 예상 가능한 실패만 `MotionServerException` 하위 type으로 발생시킨다.
- programming error는 중간 계층의 broad catch로 숨기지 않는다.
- API 최상위 boundary가 Exception을 한 번 catch하여 `FailureMapper`로 변환한다.
- mapper가 허용한 안전한 message와 details만 Fail response에 포함한다.
- 운전 상태에도 영향이 있으면 API Fail과 별도로 Diagnostic을 생성한다.

## 후속 결정

- 상위 범주와 구체 Exception의 최종 계층
- Exception에 포함할 public message/details 데이터 계약
- partial failure를 Exception으로 전달할지 결과 집계 객체로 만들지
- 기존 handler별 catch를 최상위 boundary로 이동하는 migration 범위
