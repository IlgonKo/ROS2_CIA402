# Design Decisions

이 문서는 구현 전반에 영향을 주며 장기간 유지해야 하는 결정을 기록한다.
현재 상태만 설명하는 문서는 [Software Architecture](motion_server_architecture.md),
미완료 작업은 [Remaining Tasks](remaining_tasks.md), 완료 이력은 [Work Log](worklog.md)에서 관리한다.

결정 상태는 `proposed`, `accepted`, `superseded`, `deprecated`를 사용한다.
기존 결정을 바꿀 때는 항목을 삭제하지 않고 새 결정에서 대체 관계를 명시한다.

## DEC-001 Motion Server를 장치 제어 경계로 사용

- 상태: `accepted`
- 결정일: 2026-07-16
- 결정: 상위 애플리케이션은 EtherCAT과 CiA402 세부 구현을 직접 다루지 않고
  Motion Server의 TCP JSON API를 통해 축과 I/O 장치를 제어한다.
- 이유: EtherCAT master가 실행되는 호스트와 ROS, GUI 또는 low-code client가 실행되는
  환경을 분리하면서 동일한 장치 제어 계약을 제공해야 한다.
- 영향: 장치별 SDO/PDO 처리와 상태 전이는 Motion Server 아래에 유지하고,
  client는 공개 API의 명령, 상태와 단위만 사용한다.

## DEC-002 실장치와 가상 장치에 동일한 상위 API 적용

- 상태: `accepted`
- 결정일: 2026-06-25
- 결정: mock backend와 PySOEM backend는 동일한 Motion Server API와 가능한 한 동일한
  device profile 동작을 제공한다.
- 이유: 실장치 없이 기능을 개발하고 회귀 시험을 수행하되 실제 장치 경로와의 차이를 최소화한다.
- 영향: 가상 장치 전용 동작을 상위 API에 노출하지 않으며, backend 차이는 EtherCAT/device 계층에서 처리한다.

## DEC-003 API 경계의 공학 단위 표준화

- 상태: `accepted`
- 결정일: 2026-07-06
- 결정: 선형 축은 `mm`, `mm/s`, `mm/s^2`, 회전 축은 `deg`, `deg/s`, `deg/s^2`를
  Motion Server API 단위로 사용한다.
- 이유: client가 drive별 object dictionary scale과 user-unit 설정을 알지 않아도 일관된 값을 사용해야 한다.
- 영향: 실제 drive 단위와 API 단위 사이의 변환은 Motion Server가 CMMT user position unit과
  converting unit exponent를 SDO로 읽어 축별로 수행한다.

## DEC-004 명령 제어권은 TCP 연결 단위로 관리

- 상태: `accepted`
- 결정일: 2026-07-09
- 결정: 상태와 feedback은 여러 client에 제공하지만 상태 변경 및 motion command는
  command authority를 획득한 TCP 연결만 실행할 수 있다.
- 이유: 별도 token 전달 없이 여러 GUI, ROS Bridge와 도구가 동시에 연결된 상황의 충돌을 방지한다.
- 영향: 소유 연결이 종료되거나 명시적으로 release하면 authority를 해제한다.
  authority가 없는 연결은 `authority_required`, 다른 연결이 소유 중이면 현재 소유자 정보와 함께
  `authority_busy`로 거부한다.

## DEC-005 실시간 EtherCAT 접근과 상위 client 실행 환경 분리

- 상태: `accepted`
- 결정일: 2026-06-26
- 결정: 실제 EtherCAT NIC에 연결된 호스트에서 Motion Server와 PySOEM을 실행하고,
  ROS2, MoveIt 및 원격 GUI는 TCP client로 연결할 수 있게 한다.
- 이유: raw Ethernet 접근이 필요한 실행 환경을 상위 애플리케이션의 Docker 및 GUI 의존성과 분리한다.
- 영향: Linux 배포는 Motion Server, ROS Bridge, Control Panel과 MoveIt 이미지를 역할별로 유지한다.
  Windows 직접 실행은 장치가 Windows 호스트에 연결된 경우의 별도 경로로 지원한다.

## DEC-006 ROS Bridge와 Trajectory API 후속 개발 보류

- 상태: `accepted`
- 결정일: 2026-08-20
- 결정: 별도 재개 결정 전까지 ROS Bridge 이관과 Motion Server Trajectory API 개발을 보류하고,
  Motion Server API와 device/runtime 구조 안정화에 우선순위를 둔다.
- 이유: 하위 API와 설정 구조가 계속 바뀌는 동안 상위 연동을 동시에 수정하면 중복 작업과 검증 범위가 커진다.
- 영향: 관련 작업은 `RF-008`, `RF-009`로 추적한다. 하위 계약 변경 시 후속 이관에 필요한 내용을
  해당 항목에 남긴다.

## DEC-007 공식 프로젝트명은 Motion Server로 사용

- 상태: `accepted`
- 결정일: 2026-08-21
- 결정: 프로젝트의 공식 사용자 노출 명칭은 `Motion Server`로 사용한다.
- 이유: 프로젝트 범위가 ROS2/CiA402 실험을 넘어 EtherCAT motion axis와 remote I/O를
  공통 API로 제공하는 서버로 확장되었다.
- 영향: 새 문서와 사용자 노출 명칭은 Motion Server를 사용한다. 기존 ROS package,
  환경변수, 설치 경로와 service identifier는 호환성 영향을 검토한 뒤 별도 작업으로 변경한다.

## DEC-008 RF/TD 단위의 단기 작업 브랜치 사용

- 상태: `accepted`
- 결정일: 2026-08-21
- 결정: `main`을 유일한 기준 브랜치로 사용하고, 미완료 기능은
  `rf/<번호>-<설명>`, 기술 부채는 `td/<번호>-<설명>` 브랜치에서 각각 하나씩 처리한다.
- 이유: 요구사항과 기술 부채의 문서 식별자를 코드 변경, 검증과 병합 이력에 직접 연결한다.
- 영향: 각 작업 브랜치는 최신 `main`에서 만들고 한 개의 RF 또는 TD만 포함한다.
  완료와 검증 후 `main`에 병합하며 병합된 단기 브랜치는 삭제한다.

## DEC-009 주기 Feedback과 Full Status Snapshot 분리

- 상태: `accepted`
- 결정일: 2026-08-20
- 결정: `system/feedback`은 주기 송신에 적합한 lightweight feedback으로 유지하고,
  전체 상태 snapshot은 `system/axis/status`, `system/axes/status`, `system/io/status` 계열에서 제공한다.
- 이유: 고주기 feedback payload에 변경 빈도가 낮은 설정과 상세 진단을 모두 포함하면
  network 및 client 처리 부하가 증가하고 API 책임이 불명확해진다.
- 영향: client는 실시간 표시에는 `system/feedback`, 초기 동기화와 상세 조회에는 status API를 사용한다.
  새로운 상태 필드는 갱신 주기와 사용 목적에 따라 두 경계 중 하나에 배치한다.

## DEC-010 Motion Axis와 Remote I/O를 Device Profile로 분리

- 상태: `accepted`
- 결정일: 2026-07-20
- 결정: CMMT motion drive와 CPX-AP-I-EC remote I/O를 독립적인 device profile로 표현하고,
  하나의 EtherCAT bus layout에서 motion axis와 I/O station을 함께 선언한다.
- 이유: motion과 I/O는 PDO, parameter access 및 lifecycle 요구가 다르지만 동일한 EtherCAT master와
  Motion Server API 경계 안에서 함께 구성되어야 한다.
- 영향: device별 catalog, PDO codec과 parameter access는 profile 아래에 유지한다.
  runtime은 bus layout의 axis/I/O binding을 통해 profile을 선택하고 상위 client에 공통 식별 방식을 제공한다.

## DEC-011 ESI/IODD를 Device Metadata의 기준 Source로 사용

- 상태: `accepted`
- 결정일: 2026-08-20
- 결정:
  - CMMT는 ESI로 identity, OD catalog와 PDO support를 확인하고 별도 PDO configuration에 따라 drive를 remap한다.
  - CPX-AP-I-EC는 ESI로 module ident, EtherCAT OD와 PDO size를 검증한다.
  - IO-Link device는 IODD로 port별 parameter catalog를 제공하며 catalog가 지원하지 않는 ISDU parameter를 거부한다.
- 이유: device/firmware별 metadata를 코드에 중복 기입하거나 추측하지 않고 vendor artifact에 근거해
  startup validation과 사용자 parameter access를 제공해야 한다.
- 영향: ESI/IODD version 선택, parsing failure와 unsupported metadata는 명시적인 startup/API 오류로 처리한다.
  AP parameter catalog처럼 ESI/IODD가 제공하지 않는 정보는 다른 source가 확보되기 전까지 추정하지 않는다.

## DEC-012 필수 Backend Lifecycle과 선택 Device Capability 분리

- 상태: `accepted`
- 결정일: 2026-08-21
- 결정: 모든 EtherCAT master backend는 staged startup lifecycle을 필수 계약으로 구현한다.
  구현체별로 실제 지원 여부가 다른 device 동작만 명시적인 capability로 표현한다.
- 이유: MockMaster와 PySOEMMaster 모두 `connect(target_state="preop")`과 `enter_operational()`을 지원하므로
  staged startup은 선택 기능이 아니다. `AxisRuntime`에 항상 존재하는 method를 `hasattr()`로 검사하는 방식은
  backend 지원 여부를 검증하지 못하고 필수 구현 누락의 발견만 실제 호출 시점까지 늦춘다.
- 영향:
  - startup은 항상 `connect(PRE-OP) -> device 설정 -> enter OP -> process data exchange` 순서를 사용한다.
  - master 필수 method는 명시적인 interface/protocol과 startup validation으로 검사한다.
  - 필수 lifecycle을 지원하지 않는 backend는 fallback 경로로 실행하지 않고 startup 전에 거부한다.
  - axis restart처럼 profile별 지원 여부가 다른 기능만 `DeviceCapability`로 선언한다.
  - platform 호환성, 선택적 진단 metadata와 PDO field 검사는 device capability로 분류하지 않는다.

## DEC-013 Profile/ESI 기반 Virtual OD Model을 가상 장치의 단일 상태 경계로 사용

- 상태: `accepted`
- 결정일: 2026-08-21
- 결정: 가상 장치는 선택된 device profile과 ESI를 기반으로 전체 Object Dictionary를 구성하고,
  OD 정의와 runtime value를 함께 가진 `OD Model`을 SDO, PDO와 device behavior의 단일 상태 경계로 사용한다.
- 이유: 실제 EtherCAT 장치에서 SDO와 PDO는 동일한 Object Dictionary를 서로 다른 방식으로 접근한다.
  PDO 일부만 Virtual Servo에 연결하고 나머지 OD를 MockMaster에서 개별 처리하면 실제 장치 구조와 달라지고
  device type이 추가될 때 EtherCAT transport가 device-specific object 의미를 계속 알게 된다.
- 영향:
  - `od_model.py`는 profile/ESI 기반 OD entry 정의, runtime value, access rule과 mapping metadata를 관리한다.
  - `od_bridge.py`는 SDO read/write, RxPDO-to-OD와 OD-to-TxPDO 접근을 하나의 OD Model에 연결한다.
  - `servo_model.py`는 OD Model을 읽고 쓰며 CiA402 state와 motion behavior를 모사한다.
  - `MockSlave`는 cycle 순서와 OD Bridge 위임을 담당하고 device-specific object 의미를 알지 않는다.
  - `MockMaster`는 slave routing과 generic EtherCAT transport만 담당한다.
  - 공통 역할이 없는 `Axis` wrapper와 `ServoInterface`는 제거한다.

```text
Device Profile + ESI
        -> OD Model <-> Servo Model
             <-> OD Bridge (SDO, RxPDO, TxPDO)
             -> MockSlave -> MockMaster -> DeviceManager -> AxisRuntime
```

## DEC-014 공개 계약과 내부 구현 Helper의 경계 명시

- 상태: `accepted`
- 결정일: 2026-08-21
- 결정:
  - interface, protocol과 capability는 외부 호출자가 의존하는 공개 계약과 필수 구현 항목을 명시적으로 열거한다.
  - 선택 기능과 내부 helper는 공개 계약과 분리하여 문서화한다.
  - 호출 계층에 포함된다는 이유만으로 내부 helper를 필수 method나 capability validation 대상으로 확대하지 않는다.
  - 합의된 공개 계약을 확대해야 하면 구현 전에 별도 설계 결정을 확정한다.
- 이유: TD-004 구현 과정에서 `AXIS_RESTART`의 내부 OD write helper가 request/clear-request 공개 계약과
  같은 계층도에 있다는 이유로 capability 필수 method에 잘못 포함되었다. 기존 구현체만 검증하는 테스트는
  구현체가 우연히 가진 추가 method 때문에 이 범위 확대를 발견하지 못했다.
- 검토한 대안: method 명명 규칙만으로 공개·내부 경계를 추론하는 방식은 Python의 접근 제한이 강제되지 않고
  호출 관계와 계약 관계를 다시 혼동할 수 있어 채택하지 않는다.
- 영향:
  - 관련 TD는 공개 계약, 필수 구현, 선택 기능, 내부 helper와 제외 범위를 계약표로 구분한다.
  - capability/interface 테스트는 최소 구현체 통과, 필수 항목 누락 실패와 내부 helper 부재 통과를 포함한다.
  - 완료 증거는 명세 항목, 구현 위치와 테스트를 대조하여 합의되지 않은 범위 확대가 없음을 확인한다.
  - 저장소 작업 지침은 계약 확대가 필요할 경우 구현을 중단하고 설계 결정을 먼저 갱신하도록 요구한다.

## DEC-015 API 결과와 Diagnostic 상태를 분리

- 상태: `accepted`
- 결정일: 2026-08-21
- 결정:
  - API 요청 결과는 `Success` 또는 `Fail`로 표현하며 Diagnostic에 포함하지 않는다.
  - `Fail`은 개별 요청의 실패 결과이며 지속 상태, acknowledge 또는 clear 대상으로 관리하지 않는다.
  - Diagnostic은 Motion Server 또는 장치의 현재 운전 상태를 나타낸다.
  - `DiagnosticLevel`은 `NORMAL`, `ALARM`, `FAULT`만 정의한다.
  - `NORMAL`은 활성 Alarm이나 Fault 없이 정상 운전 가능한 상태다.
  - `Alarm`은 이상이 발생하여 사용자의 확인이나 대응이 필요하지만 정상 운전을 계속할 수 있는 경우다.
  - `Fault`는 Motion Server 또는 장치의 정상 운전 상태가 제한, 중단, degraded 또는 unavailable로 변경되는 경우다.
  - Python `Exception`은 내부 계층 사이에서 실패를 전달하는 구현 수단이다. API 경계에서는 `Fail`로
    변환하고, 운전 상태에도 영향이 있으면 별도로 `Alarm` 또는 `Fault` Diagnostic을 생성한다.
- 이유: 요청의 성공·실패와 지속되는 운전 상태는 수명 주기와 소비자가 다르다. 두 개념을 같은 level로
  묶으면 정상 상태 표현, clear 정책과 API 응답 의미가 불명확해진다.
- 검토한 대안:
  - `NORMAL`, `ERROR`, `ALARM`, `FAULT`를 하나의 `DiagnosticLevel`로 두는 방식은 요청 실패를
    시스템 활성 상태처럼 오해하게 하므로 채택하지 않는다.
  - transport/protocol/device 원인 taxonomy를 사용자 API에 직접 노출하는 방식은 내부 구조와 API를 과도하게 결합한다.
- 영향:
  - API의 Success/Fail 계약은 `docs/api/`에서 관리한다. `Error`는 API 결과 상태의 명칭으로 사용하지 않는다.
  - Diagnostic 상태와 Alarm/Fault 정책은 `docs/diagnostic/`에서 관리한다.
  - 기존 exception 발생·catch inventory는 분류 전 중립 자료로 `docs/diagnostic/error_point_inventory.md`에 둔다.
  - 각 exception 지점은 후속 설계에서 `API Fail`, `Alarm`, `Fault`, `Internal only` 중 하나로 분류한다.

```text
개별 API 요청의 처리 결과인가? -> Success / Fail
현재 운전 상태에 영향이 없는가? -> Diagnostic 변경 없음
이상이 있지만 정상 운전을 계속할 수 있는가? -> Alarm
운전이 제한·중단되거나 상태가 변경되는가? -> Fault
```

## DEC-016 Diagnostic Status를 Definition·Source·History 조합으로 구성

- 상태: `accepted`
- 결정일: 2026-08-21
- 결정:
  - `DiagnosticStatus`는 고유 `diagnostic_id`, `DiagnosticDefinition`, `DiagnosticSource`,
    `DiagnosticHistory`와 예약된 optional `detail/context`를 조합한 최상위 객체다.
  - Definition은 `code`, `level`, `title`, `description`, `latching`을 정의하며 recovery policy는 포함하지 않는다.
  - Source는 `SERVER`, `BUS`, `AXIS`, `IO` type과 장치 종류별 설정 index의 조합으로 식별한다.
  - History는 `occurred_at`, `acknowledged_at`, `resolved_at`을 기록한다. 반복 시각과 횟수 및
    별도의 `cleared_at`은 저장하지 않는다.
  - non-latching Diagnostic은 resolve 시 자동 clear되고, latching Diagnostic은 resolve와
    acknowledge가 모두 완료되었을 때 clear된다.
  - clear 전 재검출은 동일 발생 건으로, clear 후 재발은 새 ID를 가진 발생 건으로 처리한다.
  - `NORMAL`은 개별 Status로 생성하지 않고 관리 대상 Diagnostic이 없을 때의 계산된 상태로만 사용한다.
- 이유: 고정 정의, 발생 위치, 발생 건의 시간 정보와 현재 표시 정보를 분리하면 중복 필드 없이 동일
  Diagnostic의 수명 주기와 재발을 일관되게 판정할 수 있다.
- 검토한 대안:
  - Status에 code, level과 acknowledge/clear 값을 중복 저장하는 방식은 구성 객체와 상태가 어긋날 수 있어 채택하지 않는다.
  - 포괄적인 `DEVICE` Source와 index만 사용하는 방식은 Axis와 IO의 index 공간이 충돌하므로 채택하지 않는다.
  - Definition의 고정 recovery enum은 RF-005에서 정할 실제 복구 동작을 미리 제한하므로 보류한다.
- 영향:
  - 상세 데이터 계약은 [Diagnostic 데이터 모델](diagnostic/diagnostic_model.md)을 따른다.
  - 현재 `runtime.last_diagnostics`의 장치 원시 readback은 이 모델의 `DiagnosticStatus`와 다른 개념으로 유지하고
    후속 구현에서 이름과 책임을 분리한다.
  - recovery handler, 보존 정책과 API serialization은 각각의 후속 설계에서 확정한다.

## DEC-017 API 요청 응답을 Success/Fail Envelope로 통일

- 상태: `accepted`
- 결정일: 2026-08-21
- 결정:
  - 모든 요청 응답은 요청과 같은 `type`, `result` 및 `data` 또는 `failure`를 갖는 공통 envelope를 사용한다.
  - `result` 값은 `success`와 `fail`이며 Success에는 `data`만, Fail에는 `failure`만 포함한다.
  - 요청에 optional `request_id`가 있으면 응답에 그대로 반환한다.
  - Fail의 `failure`는 안정적인 `code`, 사용자용 `message`와 optional `details`로 구성한다.
  - 비동기 명령의 Success는 작업 승인·시작을 뜻하며 완료는 후속 status/notification으로 전달한다.
  - 주기적 feedback과 자발적 notification에는 요청 결과인 `result`를 넣지 않는다.
- 이유: 현재 `ok`, `accepted`, `reason`, `error`와 `command_rejected`가 혼재하여 client가 command별로
  성공과 실패를 다르게 판정한다. 공통 envelope는 요청 상관관계와 실패 처리를 일관되게 만든다.
- 검토한 대안:
  - 기존 flat payload에 `ok`만 공통 추가하는 방식은 성공 데이터와 실패 정보의 경계가 계속 불명확하여 채택하지 않는다.
  - 실패 시 `type`을 `command_rejected`로 바꾸는 방식은 원래 요청과의 상관관계를 약화하므로 채택하지 않는다.
- 영향:
  - 목표 계약은 [API Success/Fail 응답 계약](api/response_contract.md)을 따른다.
  - 기존 응답 형식은 현재 동작으로 유지되며 TD-005 구현에서 새 envelope로 migration한다.
  - failure code taxonomy는 DEC-018을 따르고, 내부 Exception mapper와 호환 기간은 후속 설계에서 확정한다.

## DEC-018 API Failure Code를 Client 대응 기준으로 정의

- 상태: `accepted`
- 결정일: 2026-08-21
- 결정:
  - failure code는 Python Exception이나 command 이름이 아니라 client의 대응이 달라지는 실패 의미를 나타낸다.
  - code는 `UPPER_SNAKE_CASE`를 사용하며 `API_` prefix를 붙이지 않는다.
  - 요청, 권한, 상태, 통신·장치 접근과 복합·내부 실패를 포괄하는 초기 20개 code를 사용한다.
  - 구체적인 대상과 입력값은 code를 추가하지 않고 optional `failure.details`에 기록한다.
  - 예상하지 못한 Exception은 `INTERNAL_FAILURE`와 안전한 message로 변환하고 내부 상세는 log에만 기록한다.
  - 운전 상태에 영향이 있으면 API Fail과 별도로 Diagnostic을 생성한다.
- 이유: Exception 이름이나 command별 code를 외부 계약으로 노출하면 내부 구현 변경에 따라 API가 불안정해지고
  client가 동일한 복구 행동을 중복 구현하게 된다.
- 검토한 대안:
  - Axis, IO와 OD별로 not-found code를 나누는 방식은 client 대응이 같아 `RESOURCE_NOT_FOUND`로 통합한다.
  - `ValueError`, `RuntimeError` 같은 Python 이름을 code로 사용하는 방식은 구현 언어와 API를 결합하므로 채택하지 않는다.
- 영향:
  - 초기 catalog와 매핑 원칙은 [API Failure Code](api/failure_codes.md)를 따른다.
  - 내부 Exception 계층과 mapper 계약을 확정한 뒤 inventory의 각 발생·catch 지점을 분류한다.
  - 새 code는 client 대응이 기존 code와 실제로 다를 때만 추가한다.

## DEC-019 Exception과 API Failure를 중앙 Mapping Table로 연결

- 상태: `accepted`
- 결정일: 2026-08-21
- 결정:
  - 내부 예외는 `MotionServerException`을 기준으로 `Exception` suffix를 사용한다.
  - 내부 계층은 API failure code 문자열을 직접 포함하지 않고 중앙 `EXCEPTION_FAILURE_MAPPINGS`가
    Exception type을 `FailureCode`와 안전한 기본 message에 연결한다.
  - mapper는 정확한 type, 가장 가까운 등록 상위 type, `INTERNAL_FAILURE` 순서로 mapping한다.
  - 별도의 `FailureDefinitionRegistry`는 두지 않고 유효 code는 `FailureCode` Enum이 보장한다.
  - 예상 가능한 실패만 MotionServerException 계층을 사용하고 programming error는 최상위 API
    boundary까지 전달하여 log 후 `INTERNAL_FAILURE`로 변환한다.
  - 상위 계층은 Request, Authority, State, Communication, Device와 Operation Exception으로 구분하고
    client 대응이 달라지는 예상 가능한 실패에만 구체 Exception을 정의한다.
  - 공통 base에 자유 형식 public details를 두지 않고 구체 Exception의 명시적 속성만 mapper가 허용한다.
  - 저수준 원인은 Python exception chaining으로 보존하며 API에 직접 노출하지 않는다.
  - partial failure는 Exception이 아니라 대상별 성공과 실패를 가진 집계 객체로 표현한다.
  - inventory 분류에서 확인된 startup 설정 실패와 OD 부재를 위해 `ConfigurationException`과
    `SdoObjectNotFoundException`을 계층에 추가한다.
- 이유: mapping을 발생 지점에 하드코딩하면 동일 Exception의 API 표현이 달라질 수 있다. 반대로 별도
  Definition Registry까지 두면 Enum과 mapping table의 책임을 중복한다.
- 검토한 대안:
  - Exception이 failure code를 직접 보유하는 방식은 내부 계층과 외부 API 계약을 결합하므로 채택하지 않는다.
  - 별도 Failure Definition Registry는 현재 필요한 code 검증과 기본 message 관리가 기존 두 구성요소로
    충족되므로 도입하지 않는다.
- 영향:
  - 상세 mapper 계약은 [Exception과 API Failure Mapping](api/exception_mapping.md)을 따른다.
  - handler별 broad catch와 Exception별 details allowlist는 inventory 분류 후 최상위 boundary 중심으로 migration한다.
  - 전체 지점의 목표 분류와 migration 순서는
    [Exception 발생·Catch 지점 목표 분류](diagnostic/exception_point_classification.md)를 따른다.

## DEC-020 I/O Diagnostic은 구성에서 보장되는 Health Source만 사용

- 상태: `accepted`
- 결정일: 2026-08-21
- 결정:
  - I/O Diagnostic은 활성 PDO configuration 또는 별도로 확정된 접근 계약에서 health source가 보장될
    때만 생성한다.
  - 현재 CPX-AP 구성에서는 station, module 및 channel 단위 Diagnostic을 생성하지 않는다.
  - Bus WKC 불일치로 특정 I/O source를 추정하거나 단발 AP/ISDU API Fail을 Diagnostic으로 승격하지 않는다.
- 이유: CPX-AP의 `0x1AF1 Diag PDO`는 ESI에 정의되어 있지만 기본 Sync Manager assignment에는 포함되지
  않는다. 이를 전제로 한 module 진단은 PDO 구성에 따라 가능 여부가 달라지고 기존 process-image 계약도
  변경한다.
- 검토한 대안:
  - `0x6102`를 주기적으로 SDO polling하는 방식은 polling 주기, bus 부하, timeout과 동시 접근 정책이
    먼저 필요하여 현재 범위에 포함하지 않는다.
  - 선택형 PDO를 자동 추가하는 방식은 명시적인 설정 없이 process-image 크기와 offset을 변경하므로
    채택하지 않는다.
- 영향: TD-005-S08C2는 구현 없이 조사와 범위 확정으로 완료한다. 선택형 TxPDO 기반 station 진단과
  module 상세정보는 Optional Item `RF-012`에서 별도로 설계·검증한다.

## DEC-021 공통 Configuration 문법과 단일 Bus Model 사용

- 상태: `accepted`
- 결정일: 2026-08-24
- 결정:
  - 프로젝트 공통 설정과 장치별 설정은 동일한 file parser 문법을 사용한다.
  - 프로젝트 공통 설정은 실행 경로별로 다시 해석하지 않고 공통 loader가 읽는다.
  - Bus는 공통 parser가 `BusConfig`와 `BusDevice`로 한 번 해석하며 Motion Server와
    packaging은 같은 model을 사용한다.
  - 공통 loader는 Bus에 포함된 profile의 장치 설정 파일만 추가로 읽고, 장치 코드는
    독자적인 file parser를 갖지 않는다.
- 이유: continuation, indexed entry와 axis/I/O 혼합 Bus를 실행 경로마다 다르게
  해석하거나 새 장치 추가 시 여러 parser를 함께 수정하는 문제를 제거해야 한다.
- 검토한 대안: 장치와 실행 경로별 parser를 유지하고 fixture만 공유하는 방식은 parser
  구현이 다시 달라질 가능성을 제거하지 못하므로 채택하지 않는다.
- 영향: 설정 우선순위는 장치 기본값, 프로젝트 공통 설정, 프로세스 환경 변수 순으로
  적용한다. ROS의 공통 model 연동 및 ROS 전용 설정 분리는 RF-008에서 후속 처리한다.

## DEC-022 Typed Configuration과 명시적 Dependency 전달

- 상태: `accepted`
- 결정일: 2026-08-24
- 결정:
  - 공통 loader 결과를 immutable `MotionServerConfig`와 server, EtherCAT/cycle/DC,
    motion, logging 및 Bus device instance별 typed config로 변환한다.
  - `MotionServerApplication`은 전체 설정을 보유하는 composition root로 사용하되,
    하위 component에는 Application이나 최상위 config 전체가 아니라 실제 필요한
    typed projection과 runtime dependency만 전달한다.
  - 가상/실제 장치는 동일한 device instance config를 사용하고 backend는 master
    구현만 선택한다. simulation 전용 config는 현재 도입하지 않는다.
  - 설정의 numeric Bus label은 최종 model에 보존하지 않고 실제 순서의
    `slave_index`만 사용한다.
  - logging은 공통 optional pre-history를 지원하며 command log는 대상에서 제외한다.
- 이유: 전역 환경 변수와 Application 전체를 전달하는 service-locator 구조는 실제
  dependency를 숨기고 import side effect, 테스트 결합과 서로 다른 runtime 구성의
  간섭을 만든다.
- 검토한 대안:
  - 모든 component에 `MotionServerApplication` 또는 `MotionServerConfig` 전체를
    전달하는 방식은 접근 범위와 결합도가 과도하므로 채택하지 않는다.
  - 실제/가상 장치 config를 분리하는 방식은 동일 profile/OD 구조 원칙과 맞지 않아
    채택하지 않는다.
- 영향: TD-014에서 import-time loading, 전역 config/profile과 active model을 제거하고
  typed dependency injection으로 전환한다. derived velocity는 필수 actual velocity와
  중복되어 제거하고, CMMT interpolation mode는 device config의 Enum으로 관리한다.

## DEC-023 Virtual CMMT 초기 상태를 이름 있는 Non-PDO Configuration으로 구성

- 상태: `accepted`
- 결정일: 2026-08-24
- 결정:
  - `required_non_pdo_od`는 Motion Server가 요구하는 OD의 주소, 자료형, access와 역할
    계약만 정의하며 초기값을 소유하지 않는다.
  - `device/cmmt/non_pdo_configuration.py`에 `linear_mm`, `rotary_deg` 이름의 완전한
    Non-PDO configuration catalog를 정의하고 `.env`에서는 Mock CMMT slave가 하나를
    명시적으로 선택한다. 사용자 정의 preset, 공통 default와 slave별 부분 override는
    사용하지 않는다.
  - Non-PDO configuration은 지원하는 PDO mapping과 겹치지 않는 commissioning parameter
    20개만 포함한다. `0x6081`은 PDO schema가 소유한다. CSP/sync OD는
    startup operational configuration, reset/save/error OD는 Virtual Servo behavior가 관리한다.
  - 같은 configuration의 축은 공통값으로 초기화하고 writable OD만 SDO/API로 축별 변경한다.
    read-only unit/converting-unit OD 변경은 다른 configuration 선택과 runtime reset으로 적용한다.
  - Mock은 Non-PDO configuration으로 Virtual OD를 초기화하고 실축은 이를 무시하며 write하지
    않는다. runtime reset/process restart/device reset과 bus reconnect의 Mock runtime
    재생성은 공통값으로 복원한다.
  - device motion limit와 PP jerk는 OD readback을 사용한다. CSP jerk는 device OD와 분리하여
    메인 `MOTION_SERVER_CSP_PROFILE` 다음의 `MOTION_SERVER_CSP_JERK`로 관리한다.
  - CSP interpolation mode와 velocity offset은 현재 모든 축에 공통 적용하며 축별 설정
    계획이 없으므로 메인 `.env`와 `MotionConfig`가 소유한다. interpolation mode의 CMMT OD
    write는 장치 profile이 수행하고 velocity offset command 생성은 MotionController가 수행한다.
- 이유: OD 존재 계약, 실제 commissioning 상태와 runtime command/status 초기값을 분리하고,
  가상축이 실축과 동일한 access 및 readback 경계를 사용하면서도 반복 가능한 공통 초기
  상태를 갖게 하기 위함이다.
- 검토한 대안:
  - `required_non_pdo_od.default`에 초기값을 계속 두는 방식은 계약과 장치 상태를 혼합하므로
    채택하지 않는다.
  - 축별 초기값 override는 설정 조합을 복잡하게 하므로 채택하지 않고 writable parameter는
    명시적인 SDO/API write로 변경한다.
  - 실축 startup에서 configuration 값을 write하는 방식은 commissioning 상태를 덮어쓰므로
    채택하지 않는다.
- 영향: TD-023에서 Non-PDO configuration parser/model/validation과 Virtual OD 초기화를
  구현하고 startup motion-limit fallback 및 `startup_parameters`를 제거한다. 정확한 20개
  OD와 `linear_mm`/`rotary_deg` 값은 TD-023 기술 명세를 따른다.

## DEC-024 Device OD 기반 단일 Axis Parameter Runtime Cache 사용

- 상태: `accepted`
- 결정일: 2026-08-25
- 결정: Device OD를 최종 원본으로 두고 서버 제어에 필요한 CMMT 축 parameter는
  `AxisParameterRuntimeCache` 한 곳에 보관한다. startup, 설정 변경과 reset lifecycle에서
  OD readback이 성공한 뒤 cache를 갱신하며 주기 제어와 status API는 SDO를 반복 조회하지
  않고 cache를 사용한다.
- 이유: mutable server state와 MotionController 주변에 같은 값을 중복 보관하면 장치 reset
  이후 서로 다른 값이 남는다. 반대로 실시간 cycle에서 SDO를 조회하는 것은 부적절하다.
- 영향: TD-023은 필수 CMMT 축 parameter와 reset 동기화를 구현한다. 범용 validity,
  refresh API, 일반 parameter write, PySOEM Axis restart 완료 후 refresh와 다른 장치
  확장은 TD-025에서 처리한다. 실제 restart 완료 감지와 EtherCAT recovery는 RF-005가
  책임진다.

## DEC-025 Bootstrap 이후 초기화 실패에서 Degraded Server 유지

- 상태: `superseded` — runtime recovery 부분은 DEC-026~DEC-029로 대체
- 결정일: 2026-08-25
- 결정:
  - Motion Server 설정은 같은 raw snapshot으로 bootstrap과 전체 typed configuration을
    순서대로 구성한다.
  - bootstrap 설정은 TCP port만 소유하고 bind host는 설정에서 제거하여 항상 `0.0.0.0`을
    사용한다.
  - bootstrap 또는 TCP bind/listen 실패는 process startup failure로 처리하고, 그 이후의
    configuration/profile/catalog/runtime/drive 초기화 실패는 `runtime=None`을 허용하는
    degraded server 상태로 표현한다.
  - 초기화 실패는 stage와 안정적인 cause identifier를 사용하고
    `SERVER_INITIALIZATION_FAILED` Diagnostic과 연결한다.
  - 현재 상태는 `InitializationStatus`, 실패 내용은 `InitializationFailure`, 절차 위치는
    `InitializationStage`, 안정적인 식별자는 `InitializationCause`로 모델링한다. 기존
    `initialization_error` 문자열은 제거한다.
  - device profile, ESI/PDO catalog, module layout과 device instance model 구성 절차의 stage는
    객체 이름처럼 보이는 `DEVICE_PROFILE` 대신 `DEVICE_MODEL_BUILD`를 사용한다. 이 단계의
    분류되지 않은 일반 실패 cause는 `DEVICE_MODEL_BUILD_FAILED`로 맞춘다.
  - `InitializationCause`를 Definition Registry의 key로 사용하고 definition은 `stage`와
    `message`만 소유한다. key와 중복되는 `cause` field 및 override 가능성을 암시하는
    `default_stage`/`default_message` 명칭은 사용하지 않는다.
  - degraded 상태에는 상태·Diagnostic·복구 API만 제공하며 장치 API는
    `SERVER_NOT_READY`를 반환한다.
  - degraded 허용 목록은 authority request/release/status, server/bus status, server
    reset/restart와 bus reconnect로 제한한다. bus rescan과 모든 axis/axes/IO API는
    제외한다.
  - server status는 `initialized`와 typed `initialization_failure`를 사용하고 기존
    `drive_initialized`, `initialization_error`와 `axis_count`를 제거한다. bus status는 runtime이
    없을 때도 응답하되 `available=false`, `connected=false`와 측정 불가능한 field의 `null`을
    사용한다.
  - reset/reconnect는 기존 typed configuration으로 재초기화하고, 설정 재로딩은 process
    restart만 수행한다. 재초기화 중 기존 TCP listener와 client connection은 유지하지 않는다.
  - server reset과 process restart는 Diagnostic 저장소를 초기화한다. bus reconnect는 기존
    `DiagnosticManager`를 유지하고 해결된 Initialization Fault를 resolve까지만 처리하며,
    acknowledge/clear는 RF-005의 공통 Fault API가 담당한다.
  - 초기화 복구는 `BUS_RECONNECT < SERVER_RESET < SERVER_RESTART` 범위 계층으로 정의한다.
    configuration/device-profile은 restart, runtime-creation은 reset, bus-connection과
    device-initialization은 reconnect를 최소 필요 범위로 갖는다. 더 넓은 범위의 명령도
    허용하며 stage별 command 집합을 중복 관리하지 않는다.
  - 생성 함수는 객체를 반환하기 전까지 외부 자원 정리도 소유하고, 반환 후에는 Server
    Session이 AxisRuntime을 소유한다. 실패한 runtime은 idempotent `close()` 후 폐기하여 degraded
    context에는 `runtime=None`만 남긴다.
  - cleanup exception은 원래 Initialization Failure를 대체하지 않고 별도 내부 log로 남긴다.
    `DiagnosticManager`는 Server Session이 소유하며 server reset에서는 교체하고 bus reconnect에서는
    유지한다.
  - exception-to-cause 변환은 전역 exception type이 아니라 명시적인 initialization stage
    boundary를 우선한다. 구체 원인은 검출 지점의 typed `InitializationException(cause)`로
    전달하고 문자열 분석은 사용하지 않는다. Registry message만 API에 노출하며 원본 exception과
    traceback은 최상위 initialization boundary에서 한 번만 기록한다.
- 이유: 전체 runtime 설정이 잘못되어도 사용자가 동일한 API로 실패 원인을 확인하고 복구를
  요청할 수 있어야 하지만, 진단을 위해 불완전한 runtime을 꾸며내거나 설정 snapshot을
  중복 파싱해서는 안 된다.
- 검토한 대안:
  - 모든 설정 실패를 process 종료로 처리하는 방식은 원격 진단과 복구 API를 제공하지 못한다.
  - runtime 재초기화 중 TCP listener와 client connection을 유지하는 hot replacement는
    lifecycle 및 동시성 복잡도를 증가시키므로 채택하지 않는다.
  - bind host를 bootstrap 사용자 설정으로 유지하는 방식은 현재 배포 계약에 불필요하므로
    채택하지 않는다.
- 영향: TD-018에서 bootstrap config, initialization status, degraded context와 오류 주입
  테스트를 구현한다. runtime fault와 연결 유지 복구 정책의 추가 확장은 RF-005가 담당한다.

## DEC-026 공통 Server Runtime 상태와 Initialization 상세 분리

- 상태: `accepted`
- 결정일: 2026-08-25
- 결정:
  - Motion Server의 현재 운전·복구 상태는 `ServerRuntimeState`로 표현한다.
  - 상태 값은 `NORMAL`, `INITIALIZATION_ERROR`, `BUS_DISCONNECTED`, `FAULT` 네 가지로
    고정한다.
  - `ServerSession`이 `ServerRuntimeState`를 소유하고 API 허용 여부와 recovery 경로는 이
    상태를 기준으로 결정한다.
  - `InitializationStatus`는 제거하지 않고 initialization 절차의 성공 여부와
    `InitializationFailure` 상세를 담당한다. 공통 runtime 상태 판정에는 사용하지 않는다.
  - `NORMAL`은 유효한 runtime으로 정상 운전 가능한 상태다.
  - `INITIALIZATION_ERROR`는 초기화 실패로 runtime을 제공하지 않는 degraded 상태다.
  - `BUS_DISCONNECTED`는 운전 중 Bus 연결이 유실되어 cyclic I/O를 중단하고 기존 runtime과
    cache/topology를 유지한 채 reconnect를 기다리는 상태다. runtime 객체의 존재와 EtherCAT
    연결 활성 여부를 동일시하지 않는다.
  - `FAULT`는 runtime은 유지되지만 하나 이상의 Fault 때문에 정상 motion command를
    제한하고 명시적인 recovery가 필요한 상태다.
  - `DiagnosticLevel.FAULT`는 개별 Diagnostic의 심각도이고 `ServerRuntimeState.FAULT`는
    Fault로 운전이 제한된 집계 상태다.
- 이유: `InitializationStatus.initialized`만으로 운전 중 Bus 단절을 표현하면 연결이 끊긴
  runtime에 축 API가 허용될 수 있다. 초기화 결과 상세와 현재 운전 상태를 분리해야 API
  gating, status와 recovery scope를 일관되게 적용할 수 있다. Bus 연결 유실만으로
  cache/topology를 포함한 runtime 객체까지 즉시 폐기할 이유는 없다.
- 검토한 대안:
  - 운전 중 Bus 단절을 `BUS_CONNECTION_FAILED` Initialization Failure로 재사용하는 방식은
    startup 실패와 runtime 장애를 혼합하므로 채택하지 않는다.
  - Bus 단절 즉시 runtime을 `None`으로 만드는 방식은 연결 상태와 runtime 객체 수명을
    불필요하게 결합하고 마지막 topology/cache를 진단에 사용할 수 없으므로 채택하지 않는다.
  - runtime 존재 여부만으로 상태를 추론하는 방식은 recoverable Fault와 정상 상태를 구분하지
    못하므로 채택하지 않는다.
- 영향: RF-005에서 `ServerRuntimeState`와 상태 전이를 구현하고 validator, server/bus status와
  recovery handler가 이를 사용한다. Initialization stage/cause와 TD-018 복구 범위는 그대로
  유지한다.

## DEC-027 WKC Fault와 Bus Transport Disconnect 복구 경계

- 상태: `accepted`
- 결정일: 2026-08-25
- 결정:
  - 연속 WKC mismatch는 EtherCAT cyclic exchange가 가능한 `FAULT`로 분류한다.
    cyclic exchange는 유지하되 정상 motion command를 제한한다. WKC 조건이 정상화되면
    Diagnostic을 resolve하지만 `fault_reset`으로 내부 acknowledge되어 clear되기 전까지
    runtime 상태는 `FAULT`를 유지한다.
  - transport exception 또는 연결 유실로 cyclic exchange가 불가능하면
    `BUS_DISCONNECTED`로 전환한다. AxisRuntime, DeviceManager, parameter cache와
    MotionController는 유지하고 EtherCAT transport 연결만 닫는다.
  - `system/bus/reconnect`는 같은 AxisRuntime에서 transport 연결, device initialization과
    process data를 다시 구성한다. AxisRuntime 전체와 `DiagnosticManager`를 다시 만드는
    복구는 `system/server/restart`만 사용한다.
  - Bus reconnect는 자동 재시도하지 않고 사용자 명령으로 시작하며 `NORMAL` 상태에서는
    거부한다.
  - 연속 WKC mismatch에서는 slave transport 상태를 추가 확인한다. slave가 존재하면 WKC
    Fault, slave가 사라졌으면 `BUS_DISCONNECTED`로 분류한다.
  - Bus 상태 변화는 EtherCAT lifecycle이며 TCP listener/client lifecycle과 연동하지 않는다.
    Bus disconnect와 reconnect 동안 기존 TCP 연결을 유지한다. Server process restart에서만
    TCP 연결이 종료된다.
- 이유: WKC 불일치와 transport 단절은 복구 가능 범위가 다르다. 연결 유실만으로 서버의
  topology/cache/control 객체까지 폐기할 필요가 없으며, 같은 runtime에서 transport만
  복구해야 reconnect와 server restart의 의미가 구분된다. Bus와 TCP는 독립 transport다.
- 검토한 대안:
  - WKC mismatch마다 Bus를 재생성하는 방식은 일시적인 process data 불일치에 비해 복구
    범위가 지나치게 크므로 채택하지 않는다.
  - Bus disconnect에서 AxisRuntime을 즉시 폐기하는 방식은 reconnect를 사실상 server reset과
    같게 만들므로 채택하지 않는다.
  - 무제한 자동 reconnect는 반복 장애와 commissioning 중 상태를 숨길 수 있어 채택하지 않는다.
- 영향: RF-005에서 cyclic boundary가 두 오류를 분류하고 runtime state/API gating을 변경한다.
  reconnect 성공 후 OD parameter refresh와 projection은 TD-025 계약으로 연결한다.

## DEC-028 공개 Fault Reset과 내부 Diagnostic Acknowledge 분리

- 상태: `accepted`
- 결정일: 2026-08-25
- 결정:
  - 공개 API에는 `acknowledge` 명령을 만들지 않고 source별 `fault_reset`을 사용한다.
  - `system/server/reset`은 제거하고 Server 전체 복구는 `system/server/restart`만 사용한다.
  - `system/axis/fault_reset`과 `system/axes/fault_reset`은 선택된 Axis Fault를 내부적으로
    acknowledge하고 CiA 402 Fault Reset을 수행한다.
  - `system/bus/reconnect`는 Bus Fault acknowledge와 transport reconnect를 함께 수행한다.
  - `system/server/restart`는 process와 Diagnostic 저장소를 새로 만들므로 별도 acknowledge를
    수행하지 않는다.
  - recovery 동작 없이 자동 resolve될 수 있는 Fault를 위해 `system/server/fault_reset`과
    `system/bus/fault_reset`을 제공한다. 이 명령은 해당 source의 모든 활성 Fault를 내부적으로
    acknowledge한다.
  - 향후 `system/io/fault_reset`은 IO source Fault acknowledge를 기본으로 하고 실제 장치 복구
    동작은 RF-003에서 확장한다.
  - API는 `diagnostic_id`를 요구하지 않는다. 명령으로 지정한 대상의 모든 활성 `FAULT`가
    대상이며 `ALARM`은 제외한다. 예를 들어 axis 2를 지정하면 axis 2에서 활성화된 여러 Fault
    code를 함께 처리하며 다른 Axis의 Fault는 건드리지 않는다.
  - 내부 Diagnostic 모델의 `acknowledged_at`, resolve와 latching clear 계약은 그대로 유지한다.
- 이유: 사용자가 opaque Diagnostic 발생 ID를 선택해 acknowledge하는 방식은 복잡하다. 산업용
  장치에서 Fault Reset은 사용자의 확인과 복구 요청을 함께 나타내므로 source/device를 지정하는
  API가 더 직관적이다.
- 검토한 대안:
  - `system/diagnostic/acknowledge`와 `diagnostic_id` 단건 계약은 내부 모델을 사용자에게 과도하게
    노출하므로 채택하지 않는다.
  - `reset`과 `acknowledge`를 별도 명령으로 두는 방식은 동일 Fault에 두 번의 사용자 동작을
    요구하므로 채택하지 않는다.
- 영향: RF-005에서 기존 `system/axis/reset`, `system/axes/reset`을 `fault_reset`으로 변경하고
  Server/Bus fault-reset handler와 source 단위 DiagnosticManager 연산을 구현한다. backward
  compatibility는 제공하지 않는다. Initialization recovery scope는 `BUS_RECONNECT <
  SERVER_RESTART` 두 단계로 단순화한다.

## DEC-029 Recovery 실행·완료와 Parameter Refresh 경계

- 상태: `accepted`
- 결정일: 2026-08-25
- 결정:
  - `system/bus/reconnect`와 `system/axis/restart`는 recovery와 후속 검증이 완료된 뒤
    Success/Fail을 반환하는 동기 명령으로 구현한다. `system/server/restart`만 응답 후 process가
    종료되는 비동기 명령으로 유지한다.
  - latching Fault가 실제 조건 해제로 resolve되어도 `fault_reset`을 통해 내부 acknowledge되어
    clear되기 전에는 관련 runtime/device를 정상 운전 상태로 복귀시키지 않는다.
  - recovery 실패는 `BUS_CONNECTION_LOST`, `BUS_RECONNECT_FAILED`, `AXIS_RESTART_FAILED`로
    구분한다. `PARAMETER_REFRESH_FAILED`의 정의와 발생은 TD-025가 소유한다.
  - recovery 후 parameter 동기화는 범용 event bus 없이 명시적인 동기
    `refresh_after_recovery(runtime, recovery_type, affected_axes)` 경계로 연결한다. refresh 성공
    후에만 recovery를 완료하고 실패하면 `FAULT`를 유지한다.
  - Bus reconnect는 모든 Axis, Axis restart는 해당 Axis를 refresh 대상으로 한다.
  - recovery parameter refresh는 PRE-OP에서 수행한 뒤 OP에 진입한다. OP 진입 후 blocking SDO
    refresh로 cyclic PDO watchdog을 발생시키지 않는다.
  - recovery 완료 전 expected WKC와 같은 process data가 3회 연속 수신되는지 검증한다.
    상태 입력만 들어오고 출력 PDO가 승인되지 않는 상태는 recovery 완료로 보지 않는다.
  - timeout은 공통 설정의 양수 초 단위 값으로 두며 기본값은 Bus reconnect 10초, Axis restart
    30초로 한다.
  - startup Bus 연결 실패에서는 runtime을 새로 구성하고, 운전 중 Bus 단절에서는 기존
    AxisRuntime을 유지한 채 transport만 reconnect한다.
  - 별도 recovery worker는 두지 않는다. 동기 recovery 동안 같은 server loop의 다른 API 처리는
    일시 정지하되 기존 TCP socket과 command authority는 유지한다.
  - Axis restart 전에 전체 Axis의 homing/trajectory를 중단하고 실제 위치 hold와 disable을
    완료한다. recovery 후 자동 enable 또는 이전 motion 재개는 하지 않는다.
  - Axis restart가 의도적으로 발생시키는 transport 단절은 성공 경로에서 Bus Fault로 생성하지
    않는다. Axis restart coordinator가 slave 재발견, process image 재구성, OP 및 WKC 검증까지
    같은 요청 안에서 수행하므로 별도 Bus reconnect도 요구하지 않는다. 이 내부 복구가 실패해
    `BUS_DISCONNECTED`가 된 경우에만 후속 `system/bus/reconnect`를 사용한다.
  - timeout의 남은 시간은 connect와 OP 전이에 전달한다. worker 없이 이미 실행 중인 native/SDO
    호출을 강제로 중단하는 hard timeout은 보장하지 않는다.
- 이유: recovery 완료 전 Success를 반환하면 별도 진행 상태와 notification이 필요하고 client가
  실제 복구 결과를 알기 어렵다. 또한 연결 복구 후 장치 OD와 cache가 다르면 즉시 정상 운전을
  허용할 수 없다. latching Fault는 사용자 Fault Reset까지 운전을 막아야 한다.
- 검토한 대안:
  - 조건이 resolve되면 Fault Reset 없이 자동 `NORMAL`로 복귀하는 방식은 latching 안전 계약과
    맞지 않아 채택하지 않는다.
  - 범용 recovery event bus는 현재 단일 process의 명시적 순차 복구에 비해 복잡하므로 채택하지
    않는다.
  - 별도 recovery worker는 recovery 중 status/안전 명령 동시 처리에 유리하지만 lifecycle과
    동기화 복잡도를 늘리므로 현재 범위에서는 채택하지 않는다.
- 영향: RF-005 recovery coordinator와 설정 모델, Diagnostic definition 및 상태 전이 테스트에
  적용한다. TD-025는 동기 refresh 구현과 cache invalid Diagnostic을 제공한다.

## DEC-030 프로젝트 저장소와 설치 경로를 Motion Server 명칭으로 직접 전환

- 상태: `accepted`
- 결정일: 2026-08-26
- 결정:
  - GitHub repository는 `IlgonKo/motion-server`를 사용한다.
  - Windows repository root는 `C:\Users\Festo\Documents\motion-server`, Linux repository
    root는 `/home/festo/Documents/motion-server`를 사용한다.
  - 이전 경로 alias나 fallback은 제공하지 않고 script·문서·checkout을 새 경로로 직접 전환한다.
  - Linux checkout은 GitHub clone과 fast-forward pull로 갱신하고 host별 `.env`는 Git에서 제외한다.
    대상 checkout을 삭제하는 Windows archive sync는 사용하지 않는다.
  - Docker/systemd 실행 식별자는 TD-020, ROS 전용 식별자는 RF-008에서 변경한다.
- 이유: 외부 배포 전이므로 두 경로를 병행 지원하는 것보다 프로젝트명과 실제 checkout 경계를
  일치시키는 편이 설치·동기화·장애 대응을 단순하게 유지한다.
- 영향: TD-019는 GitHub rename, remote 갱신, Windows/Linux 경로 migration과 rollback을 함께
  검증한다. rollback은 compatibility layer가 아니라 directory와 repository 이름을 이전 상태로
  되돌리는 절차다.

## DEC-031 Motion Server 실행 식별자를 호환 계층 없이 직접 전환

- 상태: `accepted`
- 결정일: 2026-08-26
- 결정:
  - Docker image/container는 `motion-server:dev`와 `motion-server`, Compose project는
    `motion-server`를 사용한다.
  - Axis/IO Panel 공용 image는 `motion-server-control-panel:dev`를 사용한다.
  - systemd unit은 `motion-server.service`를 사용한다.
  - 외부 배포 전이므로 이전 identifier alias, fallback 및 deprecation 기간을 두지 않는다.
  - 이전 resource는 migration 시 한 번 명시적으로 중지·삭제하고 운영 script는 신규 이름만 다룬다.
  - ROS 전용 image/container/environment identifier는 RF-008 범위로 유지한다.
- 이유: 신규·이전 identifier를 함께 지원하면 cleanup과 장애 진단 경로가 계속 이중화된다.
- 영향: TD-020은 Compose, host script, systemd installer, 문서와 legacy naming 검사를 직접
  전환한다. 기존 설치는 문서화된 일회성 cleanup 후 신규 service를 설치해야 한다.

## DEC-032 Startup INFO 로그는 적용 중인 Server Runtime 요약만 제공

- 상태: `accepted`
- 결정일: 2026-08-26
- 결정:
  - 초기화 성공 로그는 `Motion Server initialized`와 server/runtime 공통 field만 출력한다.
  - DC detail은 DC와 phase lock의 실제 활성 조건에 따라 단계적으로 포함한다.
  - CSP detail은 startup motion mode가 CSP일 때만 포함한다.
  - 축별 scale, OD readback, statusword, software limit와 actual position은 초기화 요약에서 제외한다.
  - 정상 listening 로그는 bind endpoint만 출력하고 초기화 요약의 `backend`와 `axes`를 반복하지 않는다.
  - startup summary formatter는 typed configuration과 axis count만 입력받고 device/runtime 객체에
    의존하지 않는다.
- 이유: 비활성 설정 원본과 장치 상태 배열을 server lifecycle 로그에 함께 표시하면 실제 적용
  상태를 오인하고 핵심 startup 결과를 찾기 어렵다.
- 영향: 상세 축 상태는 feedback/status API, startup validation 실패는 기존 warning/error,
  실행 중 상세 진단은 명시적인 diagnostics/debug log가 계속 담당한다.

## DEC-033 Control Panel topology와 Server health는 주기 feedback에서 확정

- 상태: `accepted`
- 결정일: 2026-08-26
- 결정:
  - `system/feedback`은 process data와 함께 공통 `server_health` 및
    `process_data_valid`를 제공한다.
  - 정상, Bus 단절과 초기화 실패 상태 모두 TCP 연결과 feedback 전송을 유지한다.
  - Bus 단절 feedback은 마지막 process data 배열을 유지하되 유효하지 않다고 표시하고,
    runtime이 없는 초기화 실패 feedback은 빈 배열을 제공한다.
  - Axis Panel은 상시 연결의 첫 비어 있지 않은 feedback 배열로 topology를 한 번만 확정한 뒤
    full status로 단위·설정·metadata를 보완한다.
  - UI 생성 후 topology 변경은 동적 재구성하지 않고 Panel 재시작 대상으로 처리한다.
  - 공통 feedback에는 축별 Diagnostic 목록을 넣지 않는다. 선택 축의 상세 Diagnostic은
    `system/axis/status`로 조회한다.
- 이유: 별도 bootstrap 연결과 Server status polling 없이도 두 Control Panel이 연결 lifecycle,
  process data 유효성 및 Server 상태를 일관되게 판단해야 한다.
- 검토한 대안: `system/server/status` 저주기 polling은 feedback과 상태 전달 경로가 이중화되고,
  endpoint 변경 때 UI를 동적으로 재구성하는 방식은 축별 Tk 상태와 진행 중 제어를 안전하게
  이전하기 어렵기 때문에 선택하지 않았다.
- 영향: feedback payload는 작고 공통적인 health projection만 추가한다. Axis 상세 오류는 선택
  시점과 health/recovery 변화에만 별도 요청하며, stale process data에서는 motion UI와 trace
  갱신을 제한한다.

## DEC-034 Virtual OD Bridge는 장치 명령의 의미를 소유하지 않음

- 상태: `accepted`
- 결정일: 2026-08-26
- 결정:
  - Virtual OD Model은 profile/ESI 기반 definition과 runtime value를 소유한다.
  - Virtual OD Bridge는 공통 Virtual Device 영역에서 SDO의 index/sub-index와
    `PDO_Configuration`의 RxPDO/TxPDO mapping을 raw PDO payload와 OD Model 사이에 연결한다.
  - SDO encode/decode와 access 검증, raw RxPDO payload-to-OD 및 OD-to-raw TxPDO payload 변환을
    담당하고 PdoCodec이나 장치별 PDO 객체를 참조하지 않는다.
  - MockMaster와 PySOEMMaster는 공통 `MasterPdoRuntime`에서 RxPDO/TxPDO 객체,
    `DeviceProfile.pdo_codec`과 cycle별 raw snapshot을 소유한다.
  - 두 Master는 `prepare`에서 RxPDO를 encode하고 `send`에서 output snapshot을 확정하며
    `receive`에서 raw input을 TxPDO로 decode한다.
  - `PDO_Configuration`의 생성 시점 주입은 Master/Bridge의 변환 규칙을 제공할 뿐 device
    configuration을 대신하지 않는다. Mock와 PySOEM 모두 PRE-OP에서 같은 DeviceProfile
    process-image 준비 sequence를 실행하고, PDO assignment/mapping SDO write와 readback 검증 후
    Master-side mapping을 확정한다.
  - MockSlave는 raw PDO/SDO endpoint로서 raw RxPDO를 Bridge에 전달하고 Model_Update 이후 raw
    TxPDO를 반환하며 PDO 객체나 codec을 소유하지 않는다.
  - OD 값 codec은 실축 CMMT PDO와 Virtual SDO adapter가 공통으로 사용한다.
  - reset, parameter save, AP parameter와 IO-Link ISDU 같은 command role을 Bridge에서 해석하지 않는다.
  - Motion Server와 DeviceProfile이 Mock/PySOEM 공통 command sequence를 소유한다.
  - Virtual Device는 PDO 객체나 OD write callback을 받지 않는다. Model_Update command 시점에
    현재 OD 상태를 반영하여 실제 장치의 내부 반응과 물리 model을 갱신한다.
  - MockSlave는 OD 반영과 Model_Update 순서만 조정하고 장치별 의미를 알지 않는다.
- 이유: Bridge에 장치별 sequence와 role 분기가 누적되면 CPX 등 새로운 Virtual Device를 추가할
  때 Object Access 계층이 장치 behavior 계층으로 변질되고 실축과 가상 장치의 command sequence가
  이중화된다.
- 영향: RF-001은 Servo 패키지에 의존하지 않는 raw MockSlave와 공통 OD Bridge를 재사용한다.
  기존 `CPXPdoConfiguration`과 `CPXPdoCodec`을 그대로 재사용하고, CPX의 OD mapping은 해당
  configuration이 제공한다. CPX 고유 반응은
  `VirtualCpxApDevice.model_update()`에 구현한다. 새로운 장치 명령은 Bridge 분기가 아니라
  DeviceProfile의 공통 sequence와 Virtual Device Model_Update 반응으로 추가한다.

## DEC-035 Virtual CPX의 OD, Module 및 Process Data 모델

- 상태: `accepted`
- 결정일: 2026-08-26
- 결정:
  - Virtual CPX는 ESI와 기존 `CPXApModule` metadata로 동작하는 공통 `VirtualApModule` 목록을
    소유하며 DI/DO/DIO/AI/AO/AIO마다 장치 class를 만들지 않는다.
  - Analog 값은 PDO raw integer로 유지하고 범위 밖 값은 clamp하지 않고 거부한다.
  - OD Model은 CPX station ESI OD, 설정된 module의 slot-dependent OD와 선택된 process-image
    assignment/mapping만 생성한다. `0x6F00`과 `0x7F00`은 ESI와 같은 16-byte block으로 보관한다.
  - output process image가 module output의 단일 원본이고, 독립된 virtual module input state가
    input의 단일 원본이다. Model_Update에서 두 상태를 반영하며 자동 loopback하지 않는다.
  - IO-Link process data는 port별 raw byte buffer까지만 제공한다. 실제 AP/ISDU parameter 공간은
    RF-013, 외부 input 조작 API는 RF-014에서 구현한다.
  - 신규 Virtual CPX 생성은 모든 process/module state를 초기화한다. I/O reset/restart command는
    RF-003, runtime 상세 Diagnostic과 fault injection은 RF-012에서 구현한다.
- 이유: 실장치의 ESI/OD/process-image 구조를 유지하면서도 module별 반복 class, mock 전용 command와
  후속 parameter·simulation·diagnostic 기능의 책임 누수를 방지하기 위해서다.
- 검토한 대안: 채널별 가상 OD, module type별 class, output-input 자동 loopback과 RF-001의 mock 전용
  reset/fault injection은 실제 장치 의미와 달라지고 기능 범위를 불필요하게 넓히므로 선택하지 않았다.
- 영향: RF-001은 정상 상태의 Virtual CPX station, generic module state, raw process data와 내부 input
  injection 경계까지만 구현한다. RF-003, RF-012, RF-013과 RF-014는 이 모델을 확장하되 Bridge와
  MockSlave의 책임은 변경하지 않는다.

## DEC-036 Virtual I/O Simulation API 경계

- 상태: `accepted`
- 결정일: 2026-08-27
- 결정:
  - `system/simulation/io/input_write`, `input_read`, `input_reset`의 별도 namespace를 사용한다.
  - API는 `MOTION_SERVER_SIMULATION_API_ENABLED=1`이고 backend가 `mock`일 때만 사용할 수 있다.
  - DI는 JSON boolean, AI는 PDO raw integer, IO-Link는 module 전체 input process-data raw payload로
    설정한다. IO-Link port별 분할은 초기 범위에서 제외한다.
  - Simulation input은 외부 환경 자극이므로 Motion Server command authority를 요구하지 않는다.
    여러 client가 쓰면 서버가 처리한 마지막 값이 적용된다.
  - 입력은 cycle 사이에 유지하고 명시적 reset까지 보존한다. virtual device가 bus reconnect 또는
    server restart로 재생성되면 기본값으로 초기화한다.
  - reset은 I/O id를 필수로 받고 optional slot으로 station 전체 또는 module 하나를 초기화한다.
  - IO Control Panel은 API 사용 가능 여부를 조회하여 mock simulation에서만 DI checkbox, AI 정수와
    IO-Link hexadecimal payload 조작 화면을 노출한다.
- 이유: 일반 운전 API와 virtual environment 입력 조작을 분리하고 실제 EtherCAT 장치에 simulation
  값이 전달될 가능성을 차단하면서 제어 client와 simulator가 동시에 동작할 수 있게 하기 위해서다.
- 검토한 대안: 일반 I/O output authority 공유는 simulator의 독립 실행을 막고, 별도 simulation
  authority는 초기 범위에 비해 복잡하다. IO-Link port별 API는 IODD layout 의존성이 추가되므로
  module raw payload 이후로 미룬다.
- 영향: RF-014 handler는 MockMaster의 virtual-device 접근과 RF-001 input injection만 사용한다.
  MockSlave, VirtualOdBridge, 일반 I/O feedback 및 실장치 DeviceProfile 계약은 변경하지 않는다.

## 새 결정 작성 양식

```text

## DEC-### 제목

- 상태: proposed | accepted | superseded | deprecated
- 결정일: YYYY-MM-DD
- 대체 관계: 해당하는 경우 DEC-###을 대체함
- 결정: 선택한 방향
- 이유: 이 결정이 필요한 배경과 제약
- 검토한 대안: 선택하지 않은 주요 대안과 이유
- 영향: 코드, 설정, API, 배포 및 시험에 미치는 결과
```
