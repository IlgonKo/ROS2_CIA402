# TD-023 Virtual Servo OD 초기값의 Startup 덮어쓰기

## 배경 및 현재 구조

Virtual Servo의 OD Model은 선택된 profile의 required non-PDO OD default를 적용해 가상 장비의 초기 parameter를 구성한다.
그러나 mock runtime 생성 과정에서 `servo.set_motion_limits()`를 호출하여 다음 OD를 서버 설정값으로 즉시 다시 기록한다.

- `0x607F` Max profile velocity
- `0x2183:0C` Negative velocity limit
- `0x60C5` Max acceleration
- `0x60C6` Max deceleration
- `0x6083` Profile acceleration
- `0x6084` Profile deceleration

실축 startup은 해당 parameter를 덮어쓰지 않고 장비의 기존 값을 SDO로 읽어 runtime 상태를 구성한다.

## 문제와 위험

- required non-PDO OD 계약과 Virtual Servo 초기값의 책임이 하나의 `default` field에 혼재한다.
- required non-PDO OD에 정의한 Virtual Servo 초기값이 실제 mock 구동 상태에 반영되지 않는다.
- 동일한 CMMT profile을 사용하는 가상축별로 linear/rotary, 단위와 motion limit 등 서로 다른
  commissioning 상태를 설정할 명시적인 장치 instance 경로가 없다.
- mock과 실축의 startup parameter 정책이 달라 시험 결과가 실제 장비 동작을 대표하지 못할 수 있다.
- MotionController가 정상 startup에서는 device OD readback을 사용하지만 readback 실패 시
  `MOTION_SERVER_MAX_VELOCITY`, `MOTION_SERVER_ACCELERATION`, `MOTION_SERVER_DECELERATION`으로
  대체하여 제한값의 기준이 일관되지 않다.
- 위 설정은 device 제한과 최솟값을 계산하지 않으므로 독립적인 server safety limit로 볼 수 없다.

## 관련 위치

- `device/cmmt/required_non_pdo_od.py`
- `device/virtual_servo_drive/od_model.py`
- `device/virtual_servo_drive/servo_model.py`
- `configuration/models.py`
- `configuration/builder.py`
- `motion_server/app/startup.py`

## 확정된 데이터 책임

`required_non_pdo_od`와 장치 초기값을 다음과 같이 분리한다.

```text
RequiredNonPdoOdRole
├─ role
├─ index
├─ subindex
├─ name
├─ data_type
└─ access

NonPdoOdValue
├─ index
├─ subindex
└─ value
```

- `required_non_pdo_od.py`는 Motion Server가 요구하지만 지원하는 PDO configuration의
  mapping에는 포함되지 않는 OD의 존재, 주소, 자료형, access와 역할 계약만 정의하며
  초기값을 소유하지 않는다.
- 지원하는 모든 CMMT PDO configuration의 주소 합집합과 required Non-PDO 주소는 서로
  겹치지 않아야 한다. 현재 교차 확인에서 유일하게 겹쳤던 `0x6081:00 Profile velocity`는
  required Non-PDO 계약과 configuration에서 제외하고 PDO schema가 소유한다.
- `RequiredNonPdoOdRole.default`는 제거한다.
- `NonPdoOdValue`는 특정 장치 instance가 commissioning 이후 보유하는 OD 값을
  index/subindex 기준으로 표현한다.
- role 이름이 아니라 실제 OD index/subindex를 사용하여 실축 SDO 주소, ESI catalog와
  직접 대응시킨다.
- commissioning 주소는 TD-023 범위에서 ESI에 존재하고 `required_non_pdo_od`에 등록된
  OD로 제한하며, 자료형과 값 범위를 configuration 생성 시 검증한다.

## 축별 Configuration 경계

가상 CMMT 장치는 `device/cmmt/non_pdo_configuration.py`에 정의된 이름 있는 Non-PDO
configuration을 `.env`에서 `slave_index`별로 하나 선택한다.

```python
@dataclass(frozen=True)
class NonPdoOdValue:
    index: int
    subindex: int
    value: int | float | str

@dataclass(frozen=True)
class CmmtDeviceConfig:
    ...
    non_pdo_configuration: NonPdoConfiguration | None
```

- `NonPdoConfiguration`은 `name`과 immutable `NonPdoOdValue` 목록을 소유한다.
- preset의 실제 OD 값은 PDO configuration과 마찬가지로 code catalog에서 관리한다.
  `.env` 사용자 정의 preset과 부분적인 OD 값 override는 지원하지 않는다.
- 설정 선택은 axis index가 아니라 bus에서 유일한 `slave_index`로 장치 instance를 식별한다.
- `device/cmmt/.env`의 권장 문법은 다음과 같다.

```text
MOTION_SERVER_CMMT_SLAVE_NON_PDO_CONFIGURATIONS=\
    0:linear_mm,1:linear_mm,2:linear_mm,\
    3:rotary_deg,4:rotary_deg,5:rotary_deg
```

현재 6축 구성은 slave `0~2`에 `linear_mm`, slave `3~5`에 `rotary_deg`를 선택한다.

- 개별 `MOTION_SERVER_CMMT_SLAVE_<index>_NON_PDO_CONFIGURATION` 선택이 목록보다 우선한다.
- 공통 default configuration은 두지 않는다. Mock CMMT slave가 configuration을 선택하지
  않거나 정의되지 않은 이름을 선택하면 configuration error로 처리한다.
- PySOEM CMMT에서는 선택이 필수가 아니며 값이 있어도 적용하거나 write하지 않는다.

- `0x216E:01` 값에서 linear/rotary를 판정하며 별도의 `axis_type` 또는 mock 전용 unit
  설정은 만들지 않는다.
- `0x0100`은 linear, `0x1000`/`0x4100`/`0xB400`은 rotary로 해석하고 기존
  `AxisUnitConverter`가 API 단위를 결정한다.

## Backend 적용 경계

```text
Mock backend
ESI schema + required non-PDO OD contract
            + slave별 Non-PDO configuration
            → VirtualObjectDictionary 생성

PySOEM backend
Non-PDO configuration을 적용하거나 write하지 않음
            → 실제 장치 OD readback 사용
```

- Non-PDO configuration 값은 Virtual OD를 생성할 때 한 번 초기값으로 주입한다.
- 이후 SDO write, PDO exchange와 ServoModel에 따른 현재값은 기존
  `VirtualObjectDictionary`가 소유하므로 별도의 runtime-value 객체는 추가하지 않는다.
- 실축에서는 Non-PDO configuration을 무시하며 기대값 비교와 strict validation도 TD-023
  범위에 포함하지 않는다.
- mock과 실축 모두 MotionController와 server state는 startup OD readback 결과로 구성한다.

## Non-PDO Configuration 대상

- `required_non_pdo_od`는 Motion Server가 요구하는 전체 존재 계약을 유지한다.
- Non-PDO configuration은 그중 commissioning tool로 설정되고 장치에 보존되는 parameter만
  포함한다.
- device reset, parameter-save command/status/result와 error code 같은 command/runtime OD는
  Non-PDO configuration 대상에서 제외하고 Virtual Servo behavior가 정상 초기 상태를 만든다.
- 별도의 `NON_PDO_CONFIGURATION_OD_ROLES` 계약으로 code catalog에 포함할 수 있는 범위를
  명시한다.
- commissioning 전용 read-only OD는 Virtual OD 생성 시 초기화할 수 있지만 공개 SDO/API
  write에서는 ESI access 계약에 따라 거부한다.

## 공통 초기값과 축별 변경 정책

- 이름 있는 각 Non-PDO configuration은 해당 종류의 모든 가상축에 적용할 공통 초기값을
  20개 commissioning OD에 대해 완전하게 정의한다.
- 같은 Non-PDO configuration을 선택한 축은 software limit, motion/profile limit와 homing
  parameter를 포함하여 동일한 값으로 초기화한다.
- 축별로 달라야 하는 writable OD는 Virtual Servo 생성 이후 사용자가 실제 장치와 동일한
  SDO/API parameter write 경로로 변경한다. 초기 configuration의 slave별 부분 override는
  지원하지 않는다.
- `0x216E:01` user position unit과 `0x2194:01~04` converting unit처럼 commissioning
  tool에서만 변경 가능한 read-only OD는 SDO/API write로 개별화할 수 없다. 이 값을 바꾸려면
  다른 Non-PDO configuration을 선택하고 runtime reset으로 Virtual Servo를 재생성한다.
- runtime reset, process restart와 virtual device reset은 SDO로 변경한 축별 현재값을 버리고
  선택된 Non-PDO configuration의 공통 초기값으로 복원한다.
- SDO 변경값을 parameter save 후 영속화하는 Virtual Servo simulation은 TD-023 범위에
  포함하지 않는다.

### Non-PDO Configuration 허용 OD

`NON_PDO_CONFIGURATION_OD_ROLES`는 다음 20개 commissioning parameter로 확정한다.

```text
user_position_unit                 0x216E:01
converting_unit_position           0x2194:01
converting_unit_velocity           0x2194:02
converting_unit_acceleration       0x2194:03
converting_unit_jerk               0x2194:04
software_position_limit_negative   0x607D:01
software_position_limit_positive   0x607D:02
position_window                    0x6067:00
position_window_time               0x6068:00
max_profile_velocity               0x607F:00
negative_velocity_limit            0x2183:0C
profile_acceleration               0x6083:00
profile_deceleration               0x6084:00
homing_method                      0x6098:00
homing_speed_search_switch         0x6099:01
homing_speed_search_zero           0x6099:02
homing_acceleration                0x609A:00
max_acceleration                   0x60C5:00
max_deceleration                   0x60C6:00
pp_jerk                            0x60A4:01
```

`0x217B`, `0x212E`와 `0x1C32`의 CSP interpolation/sync OD는 startup operational
configuration에서 관리한다. `0x2000`, `0x2005`와 `0x2145`의 reset/save/error OD는
Virtual Servo runtime behavior에서 관리한다.

현재 CSP interpolation mode와 velocity offset은 모든 축에 공통 적용하며 축별 설정
계획이 없으므로 메인 `.env`와 `MotionConfig`가 소유한다. `0x217B:0D` write 자체는 CMMT
profile의 startup operational 경로가 수행한다.

### `linear_mm` code catalog 값

정확한 20개 값은 `device/cmmt/non_pdo_configuration.py`의 `linear_mm` 항목을 단일
기준으로 사용한다. 대표값은 user unit `0x0100`, software position limit
`±1000000`, max profile velocity `200`, homing method `37`이다.

API 기준 position은 mm이며 `position_scale=1000 count/mm`이다. 공통 software position
범위는 `-1000~1000 mm`, 최대 속도는 `±200 mm/s`로 시작한다.

### `rotary_deg` code catalog 값

정확한 20개 값은 `device/cmmt/non_pdo_configuration.py`의 `rotary_deg` 항목을 단일
기준으로 사용한다. 대표값은 user unit `0x4100`, software position limit
`±180000000`, max profile velocity `200000`, homing method `37`이다.

API 기준 position은 degree이며 `position_scale=1000000 count/deg`이다. 공통 software
position 범위는 `-180~180 deg`, 최대 속도는 `±200 deg/s`로 시작한다. `0x2183:0C`는
profile 변환 계약상 저장값에 `1000`을 곱해 내부 velocity raw 값으로 사용한다.

## Lifecycle 정책

- EtherCAT bus reconnect는 runtime을 재생성한다. Mock 장치는 선택된 Non-PDO
  configuration으로 초기화하고, PySOEM 장치는 값을 write하지 않은 채 실제 OD를 다시
  readback한다.
- Motion Server runtime reset은 Virtual Servo를 선택된 Non-PDO configuration으로 초기화한다.
- process restart와 virtual device reset도 선택된 Non-PDO configuration으로 초기화한다.
- parameter-save 영속성 simulation은 TD-023 범위에 포함하지 않는다.

## Axis Parameter Runtime Cache

- Device OD를 최종 원본으로 두고 서버 제어에 필요한 축 parameter는 하나의 typed
  `AxisParameterRuntimeCache`에 보관한다.
- startup, Server reset과 Bus reconnect는 OD readback으로 cache를 새로 구성한다.
- user position unit과 converting unit만 필수 startup OD로 두며 readback 실패를
  initialization error로 처리한다. Profile settings와 motion limits는 0 기반 안전
  fallback, software position limit은 기존 범위 fallback을 사용할 수 있다.
- Mock Axis restart는 preset 복원 직후 해당 축 OD를 다시 읽어 cache, unit conversion과
  MotionController 제한을 동기화한다. PySOEM은 preset을 쓰지 않는다. 실축 Axis restart
  완료 감지와 EtherCAT recovery는 RF-005, 완료 후 parameter cache refresh와 invalid 처리는
  TD-025가 담당한다.
- 설정 API는 `OD write → readback → cache 갱신` 순서를 사용하고 실패한 요청값을 cache에
  먼저 반영하지 않는다.
- 여러 OD를 쓰는 profile 설정은 일부 write가 실패해도 가능한 readback을 수행하여 실제
  반영된 값으로 cache와 `0x6081` RxPDO command를 재동기화한 뒤 원래 오류를 반환한다.
- status API와 command validation은 cache를 사용하며 기존 mutable server state의
  `software_position_limits`, `profile_settings`, `motion_limits`, unit/metadata 복사본은
  제거한다.
- 범용 validity/source/timestamp, 일반 parameter write 연동, 명시적 refresh API,
  PySOEM Axis restart 완료 후 refresh, Diagnostic과 다른 장치 유형 확장은 TD-025로
  분리한다.

## 목표 구조 및 구현 범위

- Virtual Servo의 초기 OD parameter는 slave별로 선택한 Non-PDO configuration에서 생성한다.
- mock runtime 생성 단계에서 device OD motion parameter를 자동으로 덮어쓰지 않는다.
- `MOTION_SERVER_MAX_VELOCITY`, `MOTION_SERVER_ACCELERATION`, `MOTION_SERVER_DECELERATION`과
  대응 command-line option 및 이에 기반한 motion limit fallback을 제거한다.
- MotionController의 velocity, acceleration과 deceleration 제한은 mock과 실축 모두
  device OD readback을 기준으로 구성한다.
- profile setting과 motion limit readback 실패 시 장치에 값을 쓰지 않고 해당 축 제어를
  제한하는 0 기반 runtime fallback으로 계속한다.
- device OD parameter 변경은 실축과 동일하게 명시적인 axis setting 명령을 통해 수행한다.
- startup readback은 mock과 실축 모두 기존 device parameter를 읽어 runtime 상태를 구성한다.
- 기존 `OdStartupParameter`와 `CmmtDeviceConfig.startup_parameters`는 제거하고 startup 자동
  OD write 계약을 만들지 않는다.
- `MOTION_SERVER_PP_JERK`는 device OD readback으로 대체한다.
- CSP jerk는 device OD가 아니라 Motion Server CSP profile generator의 parameter이므로
  device limit 제거 대상에 포함하지 않는다.
- 메인 `.env`와 `.env.example`에서 `MOTION_SERVER_CSP_PROFILE` 바로 다음에
  `MOTION_SERVER_CSP_JERK`를 정의한다. 기존 `MOTION_SERVER_JERK`와 `--jerk`는 각각
  `MOTION_SERVER_CSP_JERK`, `--csp-jerk`로 변경하고 CMMT 장치 설정 파일에서는 제거한다.
- typed model에서는 device limit를 나타내는 `MotionLimitConfig.jerk`에서 분리하여
  `MotionConfig.csp_profile` 바로 다음의 `MotionConfig.csp_jerk`로 관리한다.
- CSP profile generator만 `csp_profile`과 `csp_jerk`를 소비하며 PP jerk와 device OD
  readback 경로에는 영향을 주지 않는다.
- 독립적인 server safety limit가 필요하면 별도 요구사항과 명시적인 설정으로 추가하고,
  적용값을 device limit와 server safety limit 중 더 제한적인 값으로 계산한다.

## Catalog 교차 확인 결과

- `0x6068:00 Position window time`은 `UINT16`이며 단위는 `ms`이다. 따라서 두
  configuration의 값 `20`은 `20 ms`를 의미한다.
- 현재 위치를 reference mark로 채택하고 이동하지 않는 CMMT-AS/ST homing method는
  `37`이다. CiA 402 계열에서 같은 의미로 사용되는 method `35`는 Festo 기준
  `CMMP-AS`용이며 CMMT-AS/ST용이 아니므로 두 configuration에 `37`을 사용한다.
- 로컬 CMMT-AS/ST ESI도 `0x6068`을 `UINT`, `0x6098`을 `SINT`의 read/write OD로
  정의한다. ESI에는 단위와 method enum 의미가 없으므로 이 의미는 Festo CMMT 기능
  문서와 CiA 402 object definition을 함께 기준으로 확정한다.

## 세부 구현 계획 및 진행 상태

- 현재 단계: `TD-023-S05` (`TD-023` 전체 완료)
- 다음 실행 단계: 없음
- 재개 방법: 아래에서 가장 앞선 `pending` 단계를 시작하고, 완료 시 상태·완료 증거와
  다음 실행 단계를 함께 갱신한다.

| 단계 | 상태 | 범위 | 완료 조건 |
|---|---|---|---|
| TD-023-S01 | completed | `NonPdoOdValue`, `NonPdoConfiguration` 모델, code-defined preset catalog와 slave 선택 parser | 20개 완전성, PDO 주소와 비중복, 주소·자료형·범위, 누락·미정의 선택과 우선순위 테스트 통과 |
| TD-023-S02 | completed | required non-PDO OD의 default 제거 및 선택 configuration을 Virtual OD 생성에 전달 | linear/rotary slave의 생성 직후 OD 값과 read-only write 거부 테스트 통과 |
| TD-023-S03 | completed | mock startup 자동 motion-limit write 제거와 mock/실축 공통 OD readback 기준 적용 | startup 이후 configuration 값 유지, optional readback의 안전 fallback 테스트 통과 |
| TD-023-S04 | completed | legacy server limit·PP jerk 설정 제거와 CSP jerk의 `MotionConfig` 분리 | legacy 환경변수/CLI 부재 및 CSP generator 단독 소비 테스트 통과 |
| TD-023-S05 | completed | lifecycle·통합·정적 회귀 검증과 문서 마감 | reset/reconnect 정책, backend 비대칭 금지, 전체 테스트와 계약 추적 검토 완료 |
| TD-023-S06 | completed | typed Axis parameter cache와 reset/write readback 동기화 | mutable state 중복 제거, Mock Axis restart 후 OD/cache/controller 일치 테스트 통과 |

### 단계별 완료 증거

- `TD-023-S01`: code-defined configuration 20개 완전성, PDO 주소와 비중복, 허용 주소,
  ESI 자료형, 값 범위,
  누락/미정의 선택, slave별 선택과 개별 override 우선순위 테스트를 추가했다.
- `TD-023-S02`: 선택 configuration을 CMMT profile에서 Virtual OD로 전달하고
  linear/rotary 초기값이 서로 다르게 생성되는 테스트를 추가했다.
- `TD-023-S02~S05`: required 계약의 default와 Virtual Servo의 startup motion-limit helper를
  제거했다. Mock은 선택 configuration으로만 초기화하고, runtime 제한과 PP profile 값은
  device OD readback을 사용한다. legacy server limit/PP jerk 설정을 제거하고 CSP jerk만
  `MotionConfig.csp_jerk`로 분리했으며 reset/reconnect 재생성 계약을 검증했다.
- `TD-023-S06`: `AxisParameterRuntimeCache`를 runtime 단일 cache로 추가하고 startup과
  설정 API의 OD readback, Mock Axis restart의 preset 복원 후 cache/unit/controller
  동기화를 연결했다. 기존 mutable server state의 parameter 복사본을 제거하고 profile
  부분 write 실패 후에도 readback 기준으로 cache/RxPDO를 재동기화했다.

## 검증 계획

- required non-PDO OD 계약에 더 이상 초기 `default`가 포함되지 않는지 정적으로 검증한다.
- 동일 profile의 slave별 Non-PDO configuration으로 linear/rotary와 motion limit가 독립적으로
  초기화되는지 검증한다.
- Virtual Servo 생성 직후와 전체 startup 이후 Non-PDO configuration 값이 유지되는지 검증한다.
- MotionController 제한이 device OD readback과 일치하는지 검증한다.
- unit/converting-unit 실패가 initialization error, profile/motion/software limit 실패가
  해당 안전 fallback으로 처리되는지 검증한다.
- 제거 대상 `MOTION_SERVER_*` 설정과 command-line option이 startup 제한값에 관여하지 않는지 검증한다.
- axis setting 명령을 실행하면 mock과 실축의 동일한 profile API 경로로 OD parameter가 변경되는지 검증한다.
- Non-PDO configuration 주소의 ESI/required non-PDO OD 존재, 허용 목록, 자료형과 값 범위
  validation을 검증한다.
- 누락/미정의/중복 configuration과 slave 선택 우선순위를 검증한다.
- 같은 configuration을 선택한 여러 축이 동일한 값으로 초기화되고 writable OD의 SDO 변경은
  해당 축에만 적용되는지 검증한다.
- read-only unit/converting-unit OD의 SDO write가 거부되는지 검증한다.
- 실축 backend가 Non-PDO configuration 값을 write하지 않는지 검증한다.
- runtime reset 후 선택된 Non-PDO configuration으로 재초기화되는지 검증한다.
- 서로 다른 Non-PDO configuration을 선택한 virtual axis별로 readback과 MotionController 제한이
  독립적으로 구성되는지 검증한다.

## 완료 증거

- 제거된 startup write 경로: `create_axis_runtime()`의 `servo.set_motion_limits()` 호출과
  Virtual Servo의 전용 `set_motion_limits()`/`get_motion_limits()` helper를 제거했다.
- mock/real 정책: Mock만 선택 Non-PDO configuration을 Virtual OD 생성에 사용하고 PySOEM은
  실제 OD를 write하지 않는다. 양쪽 runtime 제한은 동일한 profile readback으로 구성한다.
- legacy server limit 환경변수/CLI/Compose/launcher projection을 제거하고 CSP jerk를 메인
  configuration으로 이동했다.
- 완료 리뷰 보완을 포함한 전체 unittest `200개`, source compile과
  `git diff --check`가 통과했다.
