# Diagnostic 데이터 모델

## 목적과 범위

이 문서는 Motion Server와 장치의 Alarm/Fault를 표현하는 공통 데이터 구조를 정의한다.
API 요청의 Success/Fail과 내부 Python Exception은 이 모델에 포함하지 않는다.

## 객체 구성

하나의 Diagnostic은 `DiagnosticStatus`가 다음 객체와 부가정보를 조합하여 표현한다.

```text
DiagnosticStatus
├─ diagnostic_id
├─ definition: DiagnosticDefinition
├─ source: DiagnosticSource
├─ history: DiagnosticHistory
├─ detail (reserved)
└─ context (reserved)
```

### DiagnosticLevel

```python
class DiagnosticLevel(Enum):
    NORMAL = "normal"
    ALARM = "alarm"
    FAULT = "fault"
```

`NORMAL`은 정의하지만 개별 `DiagnosticStatus`로 생성하지 않는다. 관리 대상 Diagnostic이 없을 때의
정상 상태를 나타내는 계산 결과로만 사용한다.

### DiagnosticDefinition

어떤 Diagnostic이 발생했는지를 나타내는 변경되지 않는 정의다.

```python
@dataclass(frozen=True)
class DiagnosticDefinition:
    code: str
    level: DiagnosticLevel
    title: str
    description: str
    latching: bool
```

- `code`: 로그, 저장 자료와 외부 계약에서 사용하는 안정적인 식별자
- `level`: `ALARM` 또는 `FAULT`. `NORMAL` Definition은 만들지 않는다.
- `title`: 짧고 고정된 표시명
- `description`: Diagnostic의 일반적인 의미
- `latching`: 조건 해제 후 사용자 acknowledge가 있어야 clear되는지 여부

복구 방법은 아직 확정되지 않은 동작 정책이므로 Definition에 `recovery_policy`를 두지 않는다.
RF-005에서 recovery 구조를 설계할 때 Diagnostic code와 별도 recovery handler 또는 정책을 연결한다.

### DiagnosticSource

발생 위치는 논리적 장치 종류와 해당 종류 안에서 설정된 index의 조합으로 식별한다.

```python
class DiagnosticSourceType(Enum):
    SERVER = "server"
    BUS = "bus"
    AXIS = "axis"
    IO = "io"


@dataclass(frozen=True)
class DiagnosticSource:
    type: DiagnosticSourceType
    index: int
```

현재 별도 index가 없는 Server와 Bus도 각각 index `0`을 사용한다. Axis와 IO는 각 장치 종류별
설정 index를 사용하므로 `(AXIS, 0)`과 `(IO, 0)`은 서로 다른 Source다. 새 논리 장치 종류가
추가되면 `DiagnosticSourceType`을 확장한다. 구체적인 제품 모델은 Source에 중복 저장하지 않는다.

### DiagnosticHistory

한 Diagnostic 발생 건의 수명 주기 시각을 기록한다.

```python
@dataclass
class DiagnosticHistory:
    occurred_at: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
```

- `occurred_at`: 최초 발생 시각
- `acknowledged_at`: 사용자가 해당 발생 건을 확인한 시각
- `resolved_at`: 실제 발생 조건이 해제된 시각

반복 검출 시각과 횟수는 저장하지 않는다. `cleared_at`도 중복 저장하지 않고 Status에서 latching과
두 시각을 사용하여 계산한다.

### DiagnosticStatus

현재 Diagnostic 상태를 나타내는 최상위 객체다.

```python
@dataclass
class DiagnosticStatus:
    diagnostic_id: str
    definition: DiagnosticDefinition
    source: DiagnosticSource
    history: DiagnosticHistory
    detail: str | None = None
    context: dict[str, object] | None = None
```

- `diagnostic_id`: clear 후 같은 Diagnostic이 재발했을 때 이전 발생 건과 구분하는 고유 식별자
- `detail`, `context`: 향후 발생 건별 상세정보가 필요할 때 사용하도록 예약한 optional 필드
- `code`와 `level`은 Definition에서, acknowledge와 resolve 여부는 History에서 가져오며 Status에
  중복 저장하지 않는다.

## Acknowledge, Resolve와 Clear

- acknowledge는 사용자가 Diagnostic을 확인했다는 뜻이며 발생 조건 해제를 의미하지 않는다.
- resolve는 실제 Alarm/Fault 발생 조건이 해제되었다는 뜻이다.
- non-latching Diagnostic은 resolve되면 acknowledge 없이 clear된다.
- latching Diagnostic은 resolve와 acknowledge가 모두 완료되어야 clear된다.
- `cleared_at`은 별도 필드가 아니라 clear 조건을 만족시킨 마지막 시각으로 계산한다.

```python
def cleared_at(status):
    resolved_at = status.history.resolved_at
    if resolved_at is None:
        return None
    if not status.definition.latching:
        return resolved_at
    acknowledged_at = status.history.acknowledged_at
    if acknowledged_at is None:
        return None
    return max(resolved_at, acknowledged_at)
```

| 발생 조건 | Latching | Acknowledge | 결과 |
| --- | --- | --- | --- |
| 유지 | 무관 | 무관 | clear되지 않음 |
| 해제 | `false` | 없음 | 자동 clear |
| 해제 | `true` | 없음 | acknowledge 대기 |
| 유지 | `true` | 완료 | 조건 해제 대기 |
| 해제 | `true` | 완료 | clear |

## 반복과 재발

- clear 전에 같은 `(definition.code, source.type, source.index)`가 다시 검출되면 동일 발생 건으로 본다.
- acknowledge 후 조건이 유지되는 동안 다시 검출되어도 동일 발생 건이다.
- resolve 후 acknowledge를 기다리는 동안 조건이 다시 발생하면 동일 발생 건으로 되돌리고
  `resolved_at`을 `None`으로 변경한다.
- clear 후 같은 조건이 재발하면 새로운 `diagnostic_id`를 가진 신규 `DiagnosticStatus`를 만든다.

## 후속 결정 범위

S08A core 구현에서 다음 최소 정책을 사용한다.

- `diagnostic_id`는 외부에서 구조를 해석하지 않는 opaque 문자열이며 기본 생성기는 UUID를 사용한다.
- clear된 Status는 활성 저장소에서 제거하고 clear를 완료한 lifecycle 호출의 반환값으로 제공한다.
- test와 embedding 환경은 clock과 ID factory를 주입할 수 있지만 이는 Diagnostic 데이터 계약에
  포함되지 않는 선택 기능이다.

다음 항목은 데이터 구조에 포함하지 않고 후속 단계에서 결정한다.

- clear된 Status의 메모리·파일 보존 기간
- recovery handler와 reset/reconnect/restart 정책
- 외부 API Success/Fail serialization과 notification 형식
