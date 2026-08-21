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
