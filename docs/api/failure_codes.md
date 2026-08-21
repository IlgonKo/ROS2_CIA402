# API Failure Code

## 원칙

- failure code는 Python Exception 이름이 아니라 client가 실패 원인과 다음 행동을 판단하는 안정적인 계약이다.
- 값은 `UPPER_SNAKE_CASE`를 사용하고 `failure` 객체 안에 있으므로 `API_` prefix를 붙이지 않는다.
- command나 argument마다 코드를 늘리지 않고 client의 대응이 달라질 때만 분리한다.
- 구체적인 대상과 입력값은 `failure.details`에 기록한다.
- Diagnostic code와 failure code는 서로 다른 namespace와 수명 주기를 갖는다.

## 초기 Code Catalog

### 요청

| Code | 의미 |
| --- | --- |
| `INVALID_REQUEST` | JSON 또는 필수 공통 구조가 잘못됨 |
| `UNKNOWN_COMMAND` | 등록되지 않은 command type |
| `UNSUPPORTED_OPERATION` | 알려진 command를 현재 mode/backend/device에서 지원하지 않음 |
| `INVALID_ARGUMENT` | argument의 형식, 타입 또는 값이 잘못됨 |
| `RESOURCE_NOT_FOUND` | 요청한 Axis, IO, OD object 또는 기타 대상이 존재하지 않음 |

### 권한

| Code | 의미 |
| --- | --- |
| `AUTHORITY_REQUIRED` | command authority가 없음 |
| `AUTHORITY_BUSY` | 다른 client가 authority를 소유함 |
| `PERMISSION_DENIED` | authority와 별개로 해당 작업이 허용되지 않음 |

### 서버 및 동작 상태

| Code | 의미 |
| --- | --- |
| `SERVER_NOT_READY` | 초기화되지 않았거나 요청 처리 준비가 안 됨 |
| `INVALID_STATE` | 현재 상태에서 해당 작업을 수행할 수 없음 |
| `OPERATION_CONFLICT` | 진행 중인 다른 동작과 새 작업이 충돌함 |
| `OPERATION_BLOCKED` | 활성 Fault 등 안전 조건으로 작업이 차단됨 |
| `LIMIT_VIOLATION` | 위치, 속도, 가속도 또는 기타 설정 제한을 위반함 |

### 통신 및 장치 접근

| Code | 의미 |
| --- | --- |
| `TIMEOUT` | 제한 시간 안에 작업이 완료되지 않음 |
| `COMMUNICATION_FAILED` | 연결 또는 transport 통신 실패 |
| `DEVICE_ACCESS_FAILED` | 장치 parameter 또는 OD 접근 실패 |
| `DEVICE_REJECTED` | 장치가 유효한 요청을 명시적으로 거부함 |

### 복합 작업 및 내부 실패

| Code | 의미 |
| --- | --- |
| `PARTIAL_FAILURE` | 여러 대상 중 일부만 실패함 |
| `OPERATION_FAILED` | 다른 code로 구체화할 수 없는 예상 가능한 동작 실패 |
| `INTERNAL_FAILURE` | programming error 또는 예상하지 못한 내부 실패 |

## Details 사용 예

대상 종류별 code를 새로 만들지 않고 `RESOURCE_NOT_FOUND`의 details로 구분한다.

```json
{
  "code": "RESOURCE_NOT_FOUND",
  "message": "Axis 10 does not exist.",
  "details": {
    "resource_type": "axis",
    "index": 10
  }
}
```

Diagnostic 때문에 작업이 차단되면 관련 발생 건을 연결할 수 있다.

```json
{
  "code": "OPERATION_BLOCKED",
  "message": "Motion is blocked by an active axis fault.",
  "details": {
    "diagnostic_ids": ["diag-123"]
  }
}
```

다중 대상 중 일부만 실패하면 항목별 code를 details에 기록한다.

```json
{
  "code": "PARTIAL_FAILURE",
  "message": "The operation completed for only some targets.",
  "details": {
    "succeeded": [0, 1],
    "failed": [
      {
        "target": 2,
        "failure": {
          "code": "DEVICE_ACCESS_FAILED",
          "message": "Device access failed.",
          "details": {
            "operation": "axis_controlword_write"
          }
        }
      }
    ]
  }
}
```

## Exception 변환 원칙

| 내부 실패 | Failure code |
| --- | --- |
| 요청 parsing/validation 실패 | `INVALID_REQUEST` 또는 `INVALID_ARGUMENT` |
| 존재하지 않는 대상 | `RESOURCE_NOT_FOUND` |
| authority 거부 | `AUTHORITY_REQUIRED` 또는 `AUTHORITY_BUSY` |
| 현재 상태에서 실행 불가 | `INVALID_STATE` 또는 `OPERATION_BLOCKED` |
| timeout | `TIMEOUT` |
| transport 연결 실패 | `COMMUNICATION_FAILED` |
| SDO/AP/IOL 접근 실패 | `DEVICE_ACCESS_FAILED` |
| 예상하지 못한 Exception | `INTERNAL_FAILURE` |

예상하지 못한 Exception은 client에 고정된 `INTERNAL_FAILURE`와 안전한 message만 반환한다. 실제
Exception과 stack trace는 서버 log에 기록하며 `str(exc)`를 그대로 외부로 보내지 않는다. 운전 상태에도
영향이 있으면 Fail response와 별도로 Diagnostic을 생성한다.

중앙 mapper 구조는 [Exception과 API Failure Mapping](exception_mapping.md)을 따른다. 구체적인 내부
Exception 하위 계층은 다음 설계 단계에서 확정한다.
