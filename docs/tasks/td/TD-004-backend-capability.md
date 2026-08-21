# TD-004 Backend Capability Fallback과 오래된 Servo Interface

## 배경 및 현재 구조

- `ServoInterface`와 `Axis`가 virtual servo 중심의 오래된 계약을 유지한다.
- 선택 기능을 `hasattr()`로 확인해 호출하는 경로가 있다.
- startup이 backend method 존재 여부로 staged startup과 restart 지원을 판단한다.

## 문제와 위험

지원 기능이 암묵적이어서 backend 구현 누락이 startup 이후에 발견될 수 있고,
device profile과 transport capability의 책임이 섞인다.

## 관련 위치

- `interfaces/servo_interface.py`
- `motion_server/control/axis.py`
- `motion_server/app/startup.py`
- `motion_server/server.py`

## 목표 구조 및 구현 범위

- backend와 device profile capability를 명시적인 interface 또는 immutable capability object로 표현한다.
- 필수 method와 선택 기능을 startup validation에서 구분한다.
- 암묵적인 `hasattr()` fallback을 제거한다.

### 필수 Backend Lifecycle 계약

[DEC-012](../../decisions.md)의 원칙에 따라 staged startup은 선택 capability가 아니라 모든 지원 backend의
필수 계약으로 정의한다.

```text
connect(target_state="preop")
  -> PRE-OP에서 device/PDO/SDO 설정
  -> enter_operational()
  -> process data exchange
  -> CiA402 enable
```

- MockMaster는 실제 EtherCAT state가 없더라도 위 호출 순서와 결과 계약을 모사한다.
- PySOEMMaster는 실제 EtherCAT PRE-OP/SAFE-OP/OP state transition을 수행한다.
- `AxisRuntime`과 `DeviceManager`는 동일한 필수 lifecycle interface를 노출한다.
- `hasattr(runtime, "enter_operational")` 분기와 단일 단계 startup fallback을 제거한다.
- `set_axis_position_counts_per_api_unit()`처럼 모든 runtime에 필요한 동작도 필수 계약으로 호출한다.
- 필수 method가 누락된 backend는 runtime 생성 또는 startup validation 단계에서 구체적인 오류로 거부한다.

다음 항목은 이 capability 계약의 범위에서 제외한다.

- `os.add_dll_directory` 같은 platform 기능 검사
- PySOEM version별 선택 진단 metadata
- 선택한 PDO mapping에 따른 PDO field 검증
- cycle timing 등 선택적 계측 데이터

### Axis/ServoInterface 제거와 Virtual OD 구조 연결

[DEC-013](../../decisions.md)에 따라 `ServoInterface`를 실제 backend 공통 interface로 확장하지 않는다.
이 interface의 구현체는 Virtual CiA402 Servo뿐이고 실제 CMMT/PySOEM 경로는 PDO/OD 경계를 사용한다.

- `interfaces/servo_interface.py`를 제거한다.
- mock startup에서만 생성되는 `motion_server/control/axis.py`의 `Axis` forwarding wrapper를 제거한다.
- `VirtualCiA402Servo`는 profile/ESI 기반 OD Model을 직접 읽고 쓴다.
- OD Bridge는 Axis method가 아니라 OD Model을 통해 SDO/RxPDO/TxPDO를 연결한다.
- `set_profile_velocity()`의 `hasattr()` fallback은 제거하고 PDO mapping 및 OD role 검증으로 대체한다.
- Motion Server 공통 control package에는 mock/virtual-device 전용 abstraction을 남기지 않는다.

이 부분은 TD-015의 OD Model 전환과 TD-016의 MockMaster SDO 위임이 완료된 후 최종 정리한다.

### TD-015/016과의 구현 순서

세 TD는 DEC-013의 동일한 목표 구조를 공유하지만 브랜치와 완료 판정은 분리한다.

1. TD-015: profile/ESI 기반 OD Model과 전체 OD Bridge를 구성한다.
2. TD-016: MockSlave가 SDO/PDO를 OD Bridge에 위임하고 MockMaster의 device-specific 처리를 제거한다.
3. TD-004: Axis/ServoInterface를 제거하고 backend lifecycle 및 device capability 계약을 최종 고정한다.

최종 단계에서 세 TD의 완료 조건과 통합 회귀 테스트를 함께 확인하며, 조건을 모두 만족하면
TD-004, TD-015와 TD-016을 각각 `complete`로 전환한다.

### Axis Restart Capability 및 명칭 계약

- 전체 선택 기능은 `DeviceCapability.AXIS_RESTART`로 표현한다.
- 상위 profile 동작은 다음 이름으로 통일한다.
  - `request_axis_restart(...)`: restart request를 확실한 `0 -> 1` 전이로 발생시킨다.
  - `clear_axis_restart_request(...)`: startup 또는 복구 전에 남아 있을 수 있는 request를 `0`으로 초기화한다.
- 실제 OD command write primitive가 필요하면 `write_axis_restart_command(master, axis_index, value)`를 사용한다.
- `command`라는 단어는 저수준 OD write에만 사용하고, 상위 동작에는 `request`를 사용한다.
- 기존 `restart_axis(...)`와 `clear_axis_restart_command(...)` 명칭은 위 계약으로 변경한다.
- `AXIS_RESTART` capability를 선언한 profile은 request와 clear-request 동작을 모두 제공해야 하며,
  누락 시 startup validation에서 실패한다.

의도한 계층은 다음과 같다.

```text
DeviceCapability.AXIS_RESTART
  -> request_axis_restart()
       -> write_axis_restart_command(..., 0)
       -> write_axis_restart_command(..., 1)
  -> clear_axis_restart_request()
       -> write_axis_restart_command(..., 0)
```

## 검증 계획

- mock/PySOEM backend의 capability 선언과 필수 method 일치 여부를 테스트한다.
- mock/PySOEM backend가 동일한 PRE-OP 설정 후 OP 진입 호출 순서를 따르는지 테스트한다.
- 필수 lifecycle method가 누락된 test backend가 startup 전에 거부되는지 테스트한다.
- capability 누락과 지원하지 않는 기능 요청의 오류를 테스트한다.
- axis restart request가 `0 -> 1`, startup clear가 `0`을 기록하는지 테스트한다.
- capability 선언과 request/clear-request method가 불일치하면 startup 전에 실패하는지 테스트한다.

## 완료 증거

완료 시 interface 정의, migration 결과와 자동 테스트 링크를 기록한다.
