# RF-016 Hidden Expert Mode

## 상태

- 상태: `complete`
- 우선순위: 보통
- 등록일: 2026-09-01
- 관련 항목: TD-032, TD-031, TD-005

## 목적

Motion Server에는 일반 사용자가 실수로 장치 내부 gateway OD나 raw SDO 영역에 접근하지 못하도록
API abstraction guard가 있다. 이 guard는 정상 운전과 공개 API 안정성에는 필요하지만,
실장치 진단이나 commissioning 조사에서는 원인 확인을 어렵게 만들 수 있다.

RF-016은 개발자 전용 숨김 `Expert Mode`를 추가하여, 명시적으로 켠 경우에만 일부 raw access
guard를 우회할 수 있게 한다.

## 핵심 원칙

- Expert Mode는 일반 사용자 기능이 아니다.
- Expert Mode는 안전 기능 해제가 아니다.
- Expert Mode는 Motion Server의 공개 API 추상화 보호를 일부 우회하는 내부 진단용 통로다.
- 설정은 하나만 사용한다.

```env
MOTION_SERVER_EXPERT_MODE=0
```

기본값은 항상 off다.

## 범위

### 1차 구현 범위

- `system/io/param_read`와 `system/io/param_write`에서 CPX 내부 조사 후보 OD에 대한
  직접 접근 차단만 우회한다.
- TD-032 조사 과정에서 `0x2001`, `0x2011`, ...을 ISDU access object 후보로 보았으나,
  추가 실장치 확인 결과 `0x2001`은 IOL module parameter object로 판단한다.
  Expert Mode는 특정 object가 ISDU gateway라고 확정하지 않고, 개발자가 지정한 raw SDO
  후보를 확인하기 위한 통로로만 사용한다.
- TD-032의 실장치 IO-Link parameter read/write 원인 조사를 우선 지원한다.

### 장기 방향

- 모든 parameter access safeguard를 Expert Mode에서 우회할 수 있는 구조로 확장한다.
- 단, command authority, runtime 상태 확인, transport 연결 확인, device reject와 fault 처리는
  계속 우회하지 않는다.
- 장기 확장은 개별 safeguard 위치를 조사한 뒤 같은 `MOTION_SERVER_EXPERT_MODE` 설정을 사용해
  일관되게 적용한다.

### Normal mode

- 기존 보호 동작을 유지한다.
- CPX 내부 조사 후보 OD 같은 raw access는 계속 차단한다.
- 일반 사용자 API, Control Panel, Node-RED flow 동작은 변경하지 않는다.

### Expert mode

- `MOTION_SERVER_EXPERT_MODE=1`일 때만 활성화한다.
- Motion Server가 공개 API 보호 목적으로 막아둔 일부 raw SDO 접근을 허용한다.
- TD-032처럼 CPX 내부 object를 직접 read/write해야 하는 실장치 조사에서 사용한다.
- write 동작은 기존 command authority 요구를 유지한다.
- runtime 상태 확인, transport 연결 확인, device reject, fault/recovery 처리는 우회하지 않는다.

## 공개 노출 정책

다음 위치에는 일반 사용자 기능으로 노출하지 않는다.

- README
- 공개 API 문서
- `.env.example`
- Axis Control Panel
- IO Control Panel
- Node-RED Dashboard

다음 위치에는 내부 기능으로만 기록한다.

- Remaining Tasks
- RF-016 명세
- Work Log
- TD-032 같은 관련 진단 절차 문서

## 구현 계획

1. configuration model에 `expert_mode: bool = False`를 추가한다. `complete`
2. raw SDO guard가 필요한 위치에서 `expert_mode`를 확인한다. `complete`
3. normal mode에서는 기존 차단을 유지한다. `complete`
4. expert mode에서는 CPX 내부 조사 후보 OD 직접 접근을 허용한다. `complete`
5. raw write는 command authority를 요구하고 server log에 남긴다. `complete`
6. 실패는 기존 Success/Fail envelope와 typed Exception mapping을 사용한다. `complete`
7. normal/expert mode의 read/write guard 회귀 테스트를 추가한다. `complete`
8. TD-032 진단 절차에서 Expert Mode 사용 경계를 기록한다. `complete`

## 구현 결과

- `ServerConfig.expert_mode`를 추가하고 `MOTION_SERVER_EXPERT_MODE`에서만 읽는다.
- 기본값은 off이며 `.env.example`에는 노출하지 않는다.
- initialized runtime에 `expert_mode`를 전달한다.
- normal mode에서는 `system/io/param_read/write`의 CPX 내부 조사 후보 OD 직접 접근 차단을 유지한다.
- expert mode에서는 같은 raw SDO 접근을 허용한다.
- `system/io/param_write`는 기존 API specification의 command authority 요구를 그대로 사용한다.
- expert mode에서 CPX 내부 조사 후보 OD raw write가 실행되면 console log에 남긴다.

검증:

- `python -m unittest tests.test_ethercat_parameter_handlers tests.test_typed_configuration`
- `python -m unittest discover tests`

## 제외 범위

- drive safety, EtherCAT state check, fault/emergency 처리 우회
- 일반 사용자 UI 노출
- Node-RED Dashboard toggle 제공
- 모든 validation 제거
- device reject 무시 또는 강제 성공 처리

## 완료 조건

- 기본 실행에서 `expert_mode`는 off이며 기존 raw access guard가 유지된다.
- `MOTION_SERVER_EXPERT_MODE=1`에서 TD-032 조사에 필요한 CPX 내부 후보 OD 직접 접근이 가능하다.
- expert raw write는 command authority 없이 실행되지 않는다.
- expert raw write는 로그로 식별 가능하다.
- read/write 실패는 기존 API Fail 계약으로 반환된다.
- 공개 문서와 사용자 UI에 Expert Mode가 일반 기능처럼 노출되지 않는다.
