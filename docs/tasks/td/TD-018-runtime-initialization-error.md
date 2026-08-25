# TD-018 Runtime 생성 단계 Initialization Error 처리

## 배경 및 현재 구조

- `motion_server/server.py`는 `initialize_drive()` 실패만 degraded server loop로 전환한다.
- runtime 생성 중 device profile/config/ESI 검증 오류는 degraded 경계 밖에서 발생해 process가 종료된다.
- CPX module layout과 ESI PDO size mismatch가 발생하면 client가 진단과 복구 API에 연결할 수 없다.

## 문제와 위험

설정 오류와 ESI mismatch가 server startup failure로만 노출되며, 운전 중 복구 가능한 오류와
runtime 생성 오류의 진단 경험이 서로 다르다.

## 관련 위치

- `motion_server/server.py`
- `motion_server/app/startup.py`
- `device/cpx_ap_i_ec/io_config.py`
- `device/cpx_ap_i_ec/module_resolver.py`

## 목표 구조 및 구현 범위

- configuration/profile/catalog 검증 실패를 initialization-error state로 표현한다.
- 최소 degraded runtime 또는 별도 degraded server state에서도 TCP server를 기동한다.
- `system/server/status`, `system/bus/status`, reset/restart/reconnect API를 제공한다.
- API response와 server log에 동일한 원인 식별자와 메시지를 사용한다.

## 확정 설계

- 설정은 같은 raw configuration snapshot을 사용하는 bootstrap parsing과 전체 typed
  configuration parsing의 두 단계로 구성한다.
- `BootstrapServerConfig`는 TCP `port`만 소유한다. bind host는 사용자 설정으로 제공하지
  않고 Motion Server가 항상 `0.0.0.0`을 사용한다.
- bootstrap port parsing 또는 TCP bind/listen 실패처럼 degraded TCP server 자체를 열 수
  없는 오류는 process startup failure로 처리한다.
- bootstrap 성공 이후의 configuration, device profile, PDO/catalog, runtime 생성과 drive
  initialization 실패는 initialization-error 상태로 전환한다.
- 초기화 실패는 stage, 안정적인 cause identifier, 사용자용 message와 발생 시각을 갖는
  typed status로 표현한다. `SERVER_INITIALIZATION_FAILED` Diagnostic 아래에 별도 cause를
  제공하며 API Failure code와 혼합하지 않는다.
- runtime 생성 전 실패를 표현하기 위해 degraded server context는 `runtime=None`을 허용한다.
  불완전하거나 가짜인 `AxisRuntime`은 만들지 않는다.
- degraded 상태에서는 authority, server/bus status, Diagnostic 조회와 허용된 복구 명령만
  제공한다. axis/device 운전 및 접근 API는 `SERVER_NOT_READY` Fail을 반환한다.
- server reset과 bus reconnect는 기존 typed configuration을 재사용한다. 설정 파일과 환경
  변수 변경은 process restart에서만 다시 읽는다.
- reset/reconnect 중 기존 TCP listener와 client connection은 유지하지 않는다. runtime
  재초기화 후 TCP server를 새로 시작하며 hot replacement는 구현하지 않는다.
- server reset은 runtime과 `DiagnosticManager`를 함께 새로 생성하여 기존 Diagnostic 상태와
  history를 폐기한다. process restart도 새 process에서 동일하게 초기화된다.
- bus reconnect는 기존 `DiagnosticManager`를 유지한다. reconnect 성공 시 Initialization
  Fault는 resolve까지만 수행하며 acknowledge/clear는 RF-005의 공통 Fault API가 담당한다.
- drive 초기화 여부와 문자열 오류를 분산 보관하지 않고 별도 typed initialization status로
  관리한다.

### Initialization 데이터 모델

```python
class InitializationStage(Enum):
    CONFIGURATION = "configuration"
    DEVICE_MODEL_BUILD = "device_model_build"
    RUNTIME_CREATION = "runtime_creation"
    BUS_CONNECTION = "bus_connection"
    DEVICE_INITIALIZATION = "device_initialization"


class InitializationCause(Enum):
    CONFIGURATION_INVALID = "configuration_invalid"
    CONFIGURATION_FAILED = "configuration_failed"
    DEVICE_PROFILE_INVALID = "device_profile_invalid"
    DEVICE_LAYOUT_INVALID = "device_layout_invalid"
    PDO_CATALOG_MISMATCH = "pdo_catalog_mismatch"
    DEVICE_MODEL_BUILD_FAILED = "device_model_build_failed"
    RUNTIME_CREATION_FAILED = "runtime_creation_failed"
    BUS_CONNECTION_FAILED = "bus_connection_failed"
    REQUIRED_PARAMETER_READ_FAILED = "required_parameter_read_failed"
    DEVICE_INITIALIZATION_FAILED = "device_initialization_failed"


@dataclass(frozen=True)
class InitializationFailure:
    stage: InitializationStage
    cause: InitializationCause
    message: str
    occurred_at: datetime


@dataclass(frozen=True)
class InitializationStatus:
    initialized: bool
    failure: InitializationFailure | None
```

- `initialized=True`이면 `failure`는 `None`, `initialized=False`이면 `failure`가 반드시
  존재해야 한다. TCP server를 유지하지 않는 재초기화 중간 상태는 모델링하지 않는다.
- stage는 실패한 초기화 절차 위치, cause는 API와 로그가 공유하는 안정적인 원인 식별자다.
- 기존 `initialization_error` 문자열은 삭제하고 `system/server/status`는 typed failure를
  직렬화한다. Python exception 문자열과 traceback은 내부 로그에만 남긴다.
- initialization status와 `SERVER_INITIALIZATION_FAILED` Diagnostic은 서로 포함하지 않고
  같은 발생 시각으로 별도 관리한다. bus reconnect 성공 시 status는 정상으로 교체하고
  Fault는 resolve하되 RF-005의 latching/acknowledge 계약에 따라 clear한다. server reset과
  process restart는 Diagnostic 저장소 자체를 초기화한다.

### Initialization Cause Definition Registry

```python
@dataclass(frozen=True)
class InitializationCauseDefinition:
    stage: InitializationStage
    message: str


INITIALIZATION_CAUSE_DEFINITIONS = {
    InitializationCause.PDO_CATALOG_MISMATCH:
        InitializationCauseDefinition(
            stage=InitializationStage.DEVICE_MODEL_BUILD,
            message=(
                "Configured device layout does not match "
                "the device PDO catalog."
            ),
        ),
}
```

- `InitializationCause`는 Registry key로만 사용한다. Definition에 같은 `cause` field를
  중복 보관하지 않는다.
- 하나의 cause에는 확정된 stage와 사용자용 message 하나를 연결하므로 `default_stage`,
  `default_message` 대신 `stage`, `message`를 사용한다.
- 축 번호, profile 이름과 원본 exception 같은 가변 detail은 Definition을 덮어쓰지 않고
  내부 로그에 별도로 기록한다.

### Exception에서 Initialization Cause로 변환

- exception class만 전역 mapping하지 않고 configuration build, device model build, runtime
  creation, bus connection과 device initialization을 명시적인 stage 함수 경계로 분리한다.
  같은 `ValueError`/`RuntimeError`도 발생 stage에 따라 다르게 해석한다.
- 문자열 내용을 검색하여 cause를 추정하지 않는다. PDO catalog mismatch, device layout 오류와
  필수 parameter readback 실패처럼 구체적인 검출 지점은 내부
  `InitializationException(cause)`로 안정적인 cause를 전달하고 원본 오류는 exception
  chaining으로 보존한다.
- stage별 변환 규칙은 다음과 같다.
  - configuration의 예상 validation exception은 `CONFIGURATION_INVALID`, 그 밖의 예상하지
    못한 exception은 `CONFIGURATION_FAILED`로 변환한다.
  - device model build의 profile/layout/PDO 오류는 각각 `DEVICE_PROFILE_INVALID`,
    `DEVICE_LAYOUT_INVALID`, `PDO_CATALOG_MISMATCH`를 사용하고 그 밖의 실패는
    `DEVICE_MODEL_BUILD_FAILED`로 변환한다.
  - runtime creation의 일반 exception은 `RUNTIME_CREATION_FAILED`로 변환한다.
  - bus connect 과정의 통신 및 일반 exception은 `BUS_CONNECTION_FAILED`로 변환한다.
  - 필수 unit/exponent OD readback 실패는 `REQUIRED_PARAMETER_READ_FAILED`, 그 밖의 device
    startup 실패는 `DEVICE_INITIALIZATION_FAILED`로 변환한다. 선택 OD fallback은
    Initialization Failure를 생성하지 않는다.
- `Exception`만 초기화 경계에서 처리하며 `KeyboardInterrupt`, `SystemExit` 등
  `BaseException`은 degraded 상태로 변환하지 않는다.
- API message는 Cause Definition Registry에서만 가져오고 Python exception type, 문자열,
  traceback과 로컬 경로는 API에 노출하지 않는다.
- 원본 오류는 최상위 initialization boundary에서 stage, cause, 안전한 message와 함께 한 번만
  traceback으로 기록한다. 하위 함수의 중복 error 출력은 제거하고, 초기화를 계속하는 fallback
  warning만 해당 처리 지점에서 기록한다.
- 공통 변환 함수는 Registry definition의 stage와 현재 stage가 일치하는지 검증하며 모든 cause의
  Definition 등록과 stage 일치를 자동 테스트한다.

### Degraded API 계약

degraded 상태에서는 다음 API만 허용한다.

- `system/authority/request`
- `system/authority/release`
- `system/authority/status`
- `system/server/status`
- `system/bus/status`
- `system/server/reset`
- `system/server/restart`
- `system/bus/reconnect`

복구 명령은 기존 command authority 계약을 유지한다. 아직 실제 복구 동작이 없는
`system/bus/rescan`은 허용 목록에서 제외한다. 모든 `system/axis/*`, `system/axes/*`,
`system/io/*` 요청은 status 및 parameter catalog/read를 포함하여 `SERVER_NOT_READY` Fail을
반환하며 임시 axis/device 데이터를 생성하지 않는다.

`system/server/status`는 runtime 없이 구성할 수 있어야 하며 다음 계약을 사용한다.

```json
{
  "type": "system/server/status",
  "ok": true,
  "initialized": false,
  "initialization_failure": {
    "stage": "device_model_build",
    "cause": "pdo_catalog_mismatch",
    "message": "Configured device layout does not match the device PDO catalog.",
    "occurred_at": "2026-08-25T10:30:00+09:00"
  },
  "diagnostic_status": []
}
```

- 기존 `drive_initialized`와 `initialization_error`는 제거한다.
- server 자체 상태와 무관하고 runtime 생성 전에는 신뢰할 수 없는 `axis_count`는 server
  status에서 제거한다.
- 정상 상태에서는 `initialized=true`, `initialization_failure=null`을 반환한다.

`system/bus/status`는 runtime이 없을 때도 성공 응답을 반환하되 알 수 없는 값을 0으로
꾸미지 않는다.

```json
{
  "type": "system/bus/status",
  "ok": true,
  "available": false,
  "connected": false,
  "device_count": null,
  "axis_count": null,
  "wkc": null,
  "expected_wkc": null,
  "wkc_ok": null,
  "diagnostic_status": []
}
```

- `available`은 Bus runtime의 존재 여부, `connected`는 EtherCAT 연결 활성 여부를 뜻한다.
- 측정하거나 확정하지 못한 numeric/status field는 실제 값 0과 구분하기 위해 `null`을
  사용한다.
- 별도 Diagnostic acknowledge API는 TD-018에서 추가하지 않는다.

### 복구 범위 계층

복구 명령 조합을 stage마다 반복해서 나열하지 않고 작업 범위를 다음 계층으로 정의한다.

```python
class InitializationRecoveryScope(IntEnum):
    BUS_RECONNECT = 1
    SERVER_RESET = 2
    SERVER_RESTART = 3


INITIALIZATION_RECOVERY_SCOPE = {
    InitializationStage.CONFIGURATION:
        InitializationRecoveryScope.SERVER_RESTART,
    InitializationStage.DEVICE_MODEL_BUILD:
        InitializationRecoveryScope.SERVER_RESTART,
    InitializationStage.RUNTIME_CREATION:
        InitializationRecoveryScope.SERVER_RESET,
    InitializationStage.BUS_CONNECTION:
        InitializationRecoveryScope.BUS_RECONNECT,
    InitializationStage.DEVICE_INITIALIZATION:
        InitializationRecoveryScope.BUS_RECONNECT,
}
```

- `SERVER_RESTART`는 설정 재로딩과 process 재시작을 포함하는 가장 넓은 범위다.
- `SERVER_RESET`은 같은 typed configuration으로 server runtime과 bus를 다시 생성한다.
- `BUS_RECONNECT`는 같은 server 상태에서 bus/runtime 연결을 다시 구성하는 가장 좁은 범위다.
- 요청한 scope가 해당 stage의 필수 scope 이상이면 허용한다. 숫자 비교는 handler에 직접
  작성하지 않고 `recovery_action_allowed(stage, requested_action)` 같은 공통 함수로 감싼다.
- 따라서 configuration/device-profile 실패는 restart만, runtime-creation 실패는 reset 또는
  restart, bus-connection/device-initialization 실패는 reconnect/reset/restart로 복구할 수 있다.
- 복구 API가 존재하지만 현재 stage에 필요한 범위보다 좁으면 `INVALID_STATE` Fail을 반환한다.
  runtime 부재로 실행할 수 없는 일반 axis/IO 요청의 `SERVER_NOT_READY`와 구분한다.

### 초기화 자원 소유권과 Cleanup

- 객체를 생성하는 함수는 성공적으로 상위 호출자에게 반환하기 전까지 해당 객체와 외부
  자원의 정리 책임도 가진다. 반환 성공 시에만 Server Session lifecycle로 소유권을 넘긴다.
- configuration, device profile, PDO catalog와 MotionController 같은 외부 자원을 열지 않는
  값/계산 객체에는 별도 cleanup을 요구하지 않는다.
- `create_axis_runtime()`에서 master 생성 후 DeviceManager 또는 AxisRuntime 구성/검증이
  실패하면 생성된 가장 높은 소유 객체 하나를 닫는다. DeviceManager가 master를 소유한
  이후에는 master를 중복해서 별도 정리하지 않는다.
- `AxisRuntime` 반환 이후 connect 또는 device initialization이 실패하면 Server Session이
  `runtime.close()`를 호출하고 참조를 제거한다. degraded context에는 실패한 runtime을 남기지
  않고 `runtime=None`만 사용한다.
- master, DeviceManager와 AxisRuntime의 `close()`는 미연결, 부분 초기화와 반복 호출에 안전한
  idempotent 계약을 가져야 한다. 하위 connect 구현이 자체 cleanup을 수행해도 상위 lifecycle의
  최종 `close()` 호출이 안전해야 한다.
- cleanup 중 발생한 exception은 원래 `InitializationFailure`의 stage/cause/message를
  교체하거나 상위로 다시 발생시키지 않는다. 원래 오류와 cleanup 오류를 server log에 별도
  traceback으로 기록한다. 별도 `cleanup_failed` API field는 현재 추가하지 않는다.
- `DiagnosticManager`는 AxisRuntime이 아니라 현재 Server Session이 소유하고 runtime에는 참조만
  전달한다. server reset은 Session과 DiagnosticManager를 교체하고, bus reconnect는 Session과
  DiagnosticManager를 유지한 채 runtime만 교체한다.
- reset/reconnect/restart 요청 시 응답 전송 후 client와 listener를 닫고 runtime을 정리한 다음
  요청된 범위로 재초기화하여 새 listener를 연다.
- cleanup은 공통 내부 helper를 사용하여 `None`을 허용하고 `close()` 오류를 logging하되 원래
  초기화 오류를 보존한다.

## 검증 계획

- mock runtime 생성 단계에 profile, catalog와 configuration 오류를 주입한다.
- degraded 상태의 status, reset, restart와 reconnect 응답 및 복구를 검증한다.
- 대표 CPX layout/ESI mismatch fixture를 사용한다.

## 세부 구현 계획

### S01 Initialization 모델과 Registry

- 상태: `complete`

- `InitializationStage`, `InitializationCause`, `InitializationFailure`,
  `InitializationStatus`, `InitializationCauseDefinition`과 Definition Registry를 구현한다.
- `InitializationRecoveryScope`와 stage별 최소 복구 범위 및 공통 허용 판정 함수를 구현한다.
- `InitializationStatus` 불변 조건, 모든 cause의 Definition 등록, Definition-stage 일치와 복구
  범위 완전성을 단위 테스트한다.
- 기존 runtime/server 동작은 이 단계에서 변경하지 않는다.

완료 조건:

- typed model과 Registry가 독립적으로 import되고 전체 catalog validation test가 통과한다.
- `DEVICE_MODEL_BUILD`/`DEVICE_MODEL_BUILD_FAILED` 명칭과 recovery scope 계층이 코드에
  단일 정의로 존재한다.

구현 기록:

- 변경 파일: `motion_server/app/initialization.py`,
  `tests/test_initialization_model.py`
- typed model, Definition Registry, stage별 최소 recovery scope와 공통 허용 판정을 추가했다.
- S01 단위 테스트 10개와 전체 unittest 210개, source compile 및 diff 검사가 통과했다.

### S02 Bootstrap Configuration과 Application 경계

- 상태: `complete`

- 동일 raw configuration snapshot에서 port 전용 `BootstrapServerConfig`를 먼저 구성한 뒤
  전체 `MotionServerConfig`를 구성하도록 Application 시작 경계를 변경한다.
- 사용자 host 설정과 `ServerConfig.host`를 제거하고 listener는 상수 `0.0.0.0`에 bind한다.
- bootstrap port parsing 또는 bind/listen 실패는 process startup failure, 그 이후 전체
  configuration build 실패는 typed Initialization Failure로 만든다.
- server reset/reconnect는 기존 typed configuration을 재사용하고 process restart만 raw
  configuration을 다시 읽는지 검증한다.

완료 조건:

- 전체 configuration이 잘못되어도 유효한 bootstrap port로 Application과 degraded listener를
  구성할 수 있다.
- `.env`, CLI, Docker/Windows/Linux wrapper와 configuration test에서 host 설정 잔존이 제거된다.
- raw configuration은 한 process startup에서 한 번만 로딩된다.

구현 기록:

- 변경 파일: `configuration/models.py`, `configuration/builder.py`,
  `configuration/loader.py`, `configuration/cli.py`, `configuration/__init__.py`,
  `motion_server/application.py`, `motion_server/server.py`,
  `motion_server/start_server.sh`, 관련 configuration/application/static contract test
- port 전용 `BootstrapServerConfig`와 immutable `ConfigurationSnapshot`을 추가했다. Application은
  project configuration을 한 번 읽은 snapshot에서 bootstrap을 먼저 구성하고, 전체 typed
  configuration 실패 시 bootstrap endpoint와 typed failure 및 원본 exception을 보존한다.
- `ServerConfig.host`, `CliOverrides.host`와 server `--host` option을 제거하고 listener bind는
  `MOTION_SERVER_BIND_HOST = "0.0.0.0"` 상수로 고정했다. 기존 `MOTION_SERVER_HOST`는 ROS/Panel의
  원격 server target 설정으로만 유지되며 Motion Server bind 설정에는 사용되지 않는다.
- configuration failure context를 S04 degraded runner에 전달할 수 있는 경계를 추가했다. 실제
  TCP degraded lifecycle과 status API는 계획대로 S04에서 연결한다.
- S02 관련 회귀 검사 40개와 전체 unittest 215개, source compile 및 diff 검사가 통과했다.

### S03 Staged Runtime 생성과 Cleanup

- 상태: `complete`

- device model build, runtime creation, bus connection과 device initialization을 명시적인 stage
  함수로 분리한다.
- 구체 오류 검출 지점의 `InitializationException(cause)`와 stage별 fallback mapping을
  구현하고 Registry message로 `InitializationFailure`를 만든다.
- runtime factory의 반환 전 cleanup, 반환 후 Server Session cleanup과 idempotent `close()`
  계약을 구현한다.
- cleanup failure는 원래 failure를 보존하면서 별도 traceback만 기록하도록 한다.

완료 조건:

- 각 stage 오류 주입 시 정확한 stage/cause/message가 생성된다.
- 생성 전·후와 connect 중 실패에서 master/runtime이 정확히 한 소유 경로로 닫히며 cleanup
  오류가 원래 failure를 대체하지 않는다.
- 하위 초기화 함수의 중복 error 출력이 제거되고 최상위 boundary에서 한 번만 기록된다.

구현 기록:

- 변경 파일: `motion_server/app/initialization.py`, `motion_server/app/startup.py`,
  `motion_server/application.py`, `motion_server/server.py`, `device/exceptions.py`,
  `device/cpx_ap_i_ec/profile.py`, `tests/test_staged_initialization.py`와 관련 static/OD test
- device model build, runtime creation, bus connection과 device initialization을 분리했다.
  stage 우선 fallback mapping과 구체 원인의 typed `InitializationException(cause)` 전달을
  구현했으며 CPX layout/PDO catalog 검증은 message parsing 없이 device domain exception으로
  구분한다.
- runtime factory 반환 전 실패는 DeviceManager 또는 master 중 가장 높은 생성 소유 객체를
  정리한다. 공통 cleanup helper는 close 오류를 logging하고 원래 exception을 보존한다.
- 필수 unit/exponent readback 실패는 `REQUIRED_PARAMETER_READ_FAILED`로 변환하고 선택 parameter
  fallback 계약은 유지했다.
- S03 중심 회귀 검사 43개와 전체 unittest 224개, source compile, diff 검사 및 6축 Mock staged
  startup smoke가 통과했다.

### S04 Server Session과 Degraded API

- 상태: `complete`

- `DiagnosticManager`, `InitializationStatus`와 `AxisRuntime | None`을 소유하는 Server Session
  context를 구현한다.
- runtime 없이 동작하는 degraded server loop와 확정된 authority/status/recovery allowlist를
  적용한다.
- `system/server/status`를 `initialized`/`initialization_failure` 계약으로 변경하고
  `drive_initialized`, `initialization_error`, server-level `axis_count`를 제거한다.
- `system/bus/status`에 `available`/`connected`를 추가하고 runtime이 없을 때 측정 불가능한
  값을 `null`로 직렬화한다.
- stage별 최소 recovery scope를 적용하여 부적합한 복구는 `INVALID_STATE`, axis/IO 요청은
  `SERVER_NOT_READY`로 반환한다.

완료 조건:

- runtime 생성 전 오류에서도 TCP server, authority, server status, bus status와 허용된 복구
  명령이 응답한다.
- 임시 axis/device 객체나 0 기반 가짜 Bus 측정값을 생성하지 않는다.
- 기존 status/API fixture가 새 계약으로 완전히 전환되고 legacy field가 남지 않는다.

구현 기록:

- 변경 파일: `motion_server/app/session.py`, `motion_server/app/state.py`,
  `motion_server/app/initialization.py`, `motion_server/application.py`,
  `motion_server/server.py`, API specification/validator/router, authority/client transport,
  server/bus/axis/IO status handler와 `tests/test_degraded_server_contract.py`
- `ServerSession`이 `DiagnosticManager`, typed `InitializationStatus`와 `AxisRuntime | None`을
  소유한다. configuration, device model, runtime, bus와 device initialization 어느 단계에서
  실패해도 runtime을 정리한 뒤 같은 bootstrap/typed port에서 degraded listener를 연다.
- degraded allowlist를 authority request/release/status, server/bus status와 server
  reset/restart, bus reconnect로 제한했다. allowlist를 authority 검사보다 먼저 적용하여 모든
  axis/axes/IO API와 bus rescan이 일관되게 `SERVER_NOT_READY`를 반환한다.
- server status는 `initialized`/typed `initialization_failure`를 사용하고 legacy field와
  server-level axis count를 제거했다. runtime 없는 bus status는 available/connected false와
  측정 불가능 값 `null`을 반환한다.
- 최소 recovery scope보다 좁은 복구 명령은 `INVALID_STATE`를 반환한다. 재초기화 action 전에는
  모든 client connection과 listener를 닫는다.
- 실제 configuration-error TCP listener/status/authority/restart 통합 검사를 포함한 전체
  unittest 230개, source compile, diff/legacy 검사 및 6축 ServerSession startup smoke가
  통과했다.

### S05 Diagnostic Lifecycle과 통합 검증

- 상태: `complete`

- initialization failure 발생 시 같은 시각의 `SERVER_INITIALIZATION_FAILED` Fault를 생성한다.
- server reset은 새 Server Session/DiagnosticManager, bus reconnect는 기존 DiagnosticManager를
  사용하는 lifecycle을 구현한다.
- reconnect 성공은 Initialization Fault를 resolve까지만 처리하고 RF-005의 acknowledge/clear
  후속 경계를 유지한다.
- configuration, device model, runtime, bus와 device initialization stage별 오류 주입 및 복구
  통합 테스트를 추가한다.
- 대표 CPX module layout/ESI PDO mismatch fixture와 mock reconnect/reset/restart 경로를
  검증하고 문서·worklog·완료 증거를 갱신한다.

완료 조건:

- server reset/restart와 bus reconnect의 Diagnostic 보존/초기화 차이가 자동 테스트로
  검증된다.
- API와 server log가 동일 cause identifier와 Registry message를 사용한다.
- 전체 test suite, compile validation과 문서 consistency 검사가 통과한다.

구현 기록:

- 변경 파일: `motion_server/app/initialization.py`, `motion_server/application.py`,
  `motion_server/server.py`, `tests/test_initialization_lifecycle.py`와 TD/Work Log 문서
- initialization failure를 Registry 기반의 단일 log 형식으로 출력하고 원본 exception
  traceback은 내부 로그에만 분리했다. API status와 log가 동일 stage/cause/message를
  사용하는지 자동 검증한다.
- configuration 이후 네 runtime stage의 오류 주입, 같은 시각의 Initialization Fault 생성,
  reconnect 성공 후 latching Fault resolve-only 동작을 검증했다.
- server reset은 새 Session/DiagnosticManager를 사용하고 bus reconnect는 기존 Session과
  DiagnosticManager를 보존하는 lifecycle을 자동 검증했다. CPX layout 오류와 ESI PDO catalog
  mismatch도 서로 다른 typed device 오류로 유지되는지 대표 fixture로 검증했다.
- 전체 unittest 236개와 source compile 및 diff 검사가 통과했다.
- 완료 리뷰에서 startup OD readback 이후의 cache, unit conversion, MotionController projection과
  server state 구성이 초기화 성공 판정 밖에 남아 있던 P1 경계를 수정했다. 이 후처리까지
  `DEVICE_INITIALIZATION`으로 처리하며 실패하면 runtime을 정리하고 degraded server를 연다.
- `0x6081 Profile velocity` readback은 첫 cyclic exchange 전에 outgoing RxPDO command에
  동기화한다. startup과 Axis restart가 같은 동기화 helper를 사용하며 서버 상태 구성에서는
  RxPDO를 직접 변경하지 않는다.
- P1 실패 주입과 첫 exchange 이전 RxPDO 동기화 순서 검사를 포함한 전체 unittest 238개가
  통과했다.

## 구현 순서

`S01 → S02 → S03 → S04 → S05` 순서로 진행한다. 각 단계 완료 시 이 문서에 변경 파일,
검증 명령과 결과를 기록하고 다음 단계로 이동한다. 단계 내부의 사소한 helper 작업은 별도
하위 번호로 추가하지 않는다.

## 완료 증거

- typed Initialization model과 Cause Definition Registry, runtime 없는 degraded server 및
  server/bus status 계약을 구현했다.
- configuration, device model, runtime creation, bus connection과 device initialization 실패가
  안정적인 stage/cause/message로 변환되며 원본 오류는 내부 traceback으로만 기록된다.
- 실제 configuration-error TCP listener와 authority/status/restart 경로, 단계별 오류 주입,
  reconnect/reset Diagnostic lifecycle 및 CPX layout/catalog mismatch fixture가 통과했다.
- 최종 검증: 전체 unittest 238개, Python source compile 및 변경 diff 검사 통과.
