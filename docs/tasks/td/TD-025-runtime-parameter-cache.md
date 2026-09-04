# TD-025 Device-wide Runtime Parameter Cache 관리 체계 확장

## 배경

TD-023은 CMMT 축 제어에 즉시 필요한 OD readback을 단일
`AxisParameterRuntimeCache`에 보관하고 startup, 설정 변경과 recovery lifecycle에서
동기화한다.

CPX-AP-I-EC의 EtherCAT station parameter, AP module parameter와 IO-Link ISDU 접근 경계도
정리되었으므로 runtime cache는 CMMT 축 전용이 아니라 장치 전체를 표현할 수 있어야 한다.
다만 모든 OD/parameter를 cache하지 않고, 서버 제어/status/API 응답 또는 recovery 이후
정합성에 필요한 항목만 cache 대상으로 둔다.

서버 재시작 후 virtual device parameter를 복원하거나 변경 이력을 관리하고 실장비로 이전하는
영구 저장 기능은 [RF-017](../rf/RF-017-persistent-parameter-store.md)로 분리한다.

## 현재 구현 상태

### 2026-09-04 1차 구현

공통 `RuntimeParameterAddress`, `RuntimeParameterDefinition`,
`RuntimeParameterValue`, `RuntimeParameterCache` 모델을 추가했다.

`AxisParameterRuntimeCache`는 기존 축별 projection field를 유지하되, 내부에서 공통
`RuntimeParameterCache`에 axis parameter definition과 현재값을 같이 등록/갱신한다.

```text
CMMT Axis OD readback
→ AxisParameterRuntimeCache
→ RuntimeParameterCache(axis source)
→ MotionController / status / command default 값에 사용
```

현재 axis provider가 공통 cache에 등록하는 값은 다음과 같다.

```text
AxisParameterValues
├─ user_position_unit
├─ converting_unit_exponents
├─ software_position_limits
├─ profile_settings
├─ motion_limits
└─ axis_metadata
```

기존 축별 projection field는 그대로 남아 있으므로 기존 MotionController/status 경로를 크게
흔들지 않는다. 다만 같은 값이 공통 cache에도 다음과 같은 address/definition/value 구조로
투영된다.

```text
key = axis.0.motion_limits
address = axis0 / ethercat_od_group / role=motion_limits
value = [max_velocity, max_acceleration, max_deceleration, max_jerk], valid=true, updated_at=...
```

`0x607F:00`처럼 단일 OD로 쪼개진 모든 하위 parameter를 아직 개별 definition으로 분해하지는
않았다. 1차 구현에서는 기존 projection 단위인 `profile_settings`, `motion_limits` 같은 묶음도
하나의 runtime parameter value로 다룬다.

### 현재 Startup 경로

```text
read_startup_axis_sdo()
→ user unit / exponent / software limit / profile / motion limit readback
→ user unit 또는 exponent 실패 시 initialization error
→ optional profile/motion limit 실패 시 fallback
→ AxisParameterRuntimeCache와 MotionController projection 구성
```

### 현재 Axis 설정 변경 경로

```text
axis profile / motion limit / software limit write
→ device OD write
→ device OD readback
→ AxisParameterRuntimeCache 업데이트
→ MotionController projection 또는 RxPDO profile_velocity 재동기화
```

여러 OD를 쓰는 설정에서 일부 write가 실패해도 가능한 readback을 수행하여 실제 장치에 반영된
값을 기준으로 cache/projection을 재동기화한 뒤 원래 write 오류를 반환한다.

#### `0x6081 Profile velocity`와 RxPDO mapping

`0x6081 Profile velocity`는 device OD이지만 PDO configuration에 포함될 수 있다. 이 경우
Motion Server가 매 cyclic PDO마다 `0x6081` command value를 계속 송신하므로, SDO로 쓴 값과
RxPDO command value가 서로 다르면 다음 PDO cycle에서 장치 OD 값이 다시 덮일 수 있다.

따라서 `system/axis/profile`에서 `profile_velocity`를 변경할 때는 다음 규칙을 적용한다.

```text
PDO configuration에 0x6081이 포함된 경우
→ 0x6081 SDO write 수행
→ 같은 값으로 RxPDO profile_velocity command value 갱신
→ cache/status의 profile_settings[0]은 effective command value로 유지

PDO configuration에 0x6081이 없거나 mapping 여부를 판단할 수 없는 경우
→ 기존처럼 0x6081 SDO write/readback 기준으로 처리
```

즉 `profile_settings[0]`은 PDO-mapped 구성에서는 단순한 SDO readback 값이 아니라 Motion Server가
앞으로 cyclic PDO로 내보낼 effective profile velocity default를 의미한다. acceleration,
deceleration, jerk는 기존처럼 SDO write/readback 기준으로 갱신한다.

### 현재 Recovery 경로

```text
refresh_after_recovery()
→ refresh_axis_parameter_cache()
→ 대상 Axis OD readback
→ AxisParameterRuntimeCache 업데이트
→ unit conversion / MotionController / RxPDO profile_velocity 재동기화
```

`refresh_after_recovery()`는 RF-005와 TD-025 axis cache 사이의 adapter 경계다.

Recovery 이후 axis parameter readback이 실패하면:

```text
refresh_after_recovery()
→ 대상 axis RuntimeParameterCache value invalid 처리
→ PARAMETER_REFRESH_FAILED Diagnostic detect
→ 기존 recovery 요청은 fail로 반환
```

다시 recovery refresh가 성공하면 기존 `PARAMETER_REFRESH_FAILED` Diagnostic은 resolve한다.
Diagnostic acknowledge/clear 정책은 RF-005의 latching fault 계약을 따른다.

### 현재 CPX/AP/IOL Parameter 경로

CPX station EtherCAT parameter, AP module parameter와 IO-Link ISDU parameter를 표현할 address
domain은 공통 모델에 포함했다.

```text
ethercat_od
ethercat_od_group
axis_projection
ap_parameter
iol_isdu
```

CPX/AP/IOL handler는 실제 read/write가 성공한 뒤 결과를 공통 cache에 반영한다.

```text
system/io/param_read
→ EtherCAT SDO read
→ RuntimeParameterCache(io / ethercat_od) 갱신

system/io/ap/param_read
→ AP gateway sequence 실행
→ RuntimeParameterCache(io / ap_parameter) 갱신

system/io/iol/param_read
→ ISDU gateway sequence 실행
→ RuntimeParameterCache(io / iol_isdu) 갱신
```

write 경로도 device access가 성공한 뒤 written value와 raw payload를 cache에 반영한다.
실패한 접근은 기존 Failure 계약대로 응답하고 성공하지 않은 값을 cache에 남기지 않는다.

직접 parameter API는 실제 catalog access 권한을 항상 알 수 있는 경로가 아니므로, 동적 cache
definition의 access는 기본 `rw`로 등록한다. 실제 접근 가능 여부는 기존 AP/IOL/SDO access
검증과 장치 응답이 결정한다.

### 1차 구현에서 추가된 자동 테스트

- 공통 runtime parameter definition/address/value/cache 모델 검증
- Axis cache 값이 공통 RuntimeParameterCache로 투영되는지 검증
- Axis cache invalidation 시 공통 cache validity가 `false`로 전환되는지 검증
- Recovery refresh 실패 시 cache invalidation과 `PARAMETER_REFRESH_FAILED` Diagnostic 발생 검증
- Recovery refresh 재성공 시 `PARAMETER_REFRESH_FAILED` resolve 검증
- Axis/IO EtherCAT OD read/write 성공 결과가 공통 cache에 반영되는지 검증
- CPX AP parameter read/write 성공 결과가 공통 cache에 반영되는지 검증
- IO-Link ISDU read/write 성공 결과가 공통 cache에 반영되는지 검증

## 현재 구조의 한계

- Axis cache는 아직 기존 projection field와 공통 cache를 동시에 유지한다.
- `motion_limits`, `profile_settings`는 아직 개별 OD 단위가 아니라 projection 묶음 단위로 cache된다.
- CPX/AP/IOL은 성공한 직접 read/write 결과를 cache에 남기지만, startup에서 자동으로 모든 parameter를
  scan하지는 않는다.
- 명시적 외부 refresh API는 만들지 않았다. 현재는 startup/recovery/parameter access 경계에서 내부
  refresh 또는 cache update를 수행한다.
- RF-017 Persistent Store에 넘길 snapshot은 `RuntimeParameterCache.snapshot()`을 기반으로 하되,
  실제 파일 저장 포맷은 RF-017에서 확정한다.

## 범위

- CMMT Axis, CPX station EtherCAT OD, CPX AP module parameter와 IO-Link ISDU parameter를
  표현할 runtime parameter source/address model
- cache 항목의 definition, source, validity, 마지막 갱신 시각과 마지막 오류
- 전체/장치별/축별/항목별 명시적 refresh API 또는 내부 refresh 경계
- 일반 `param_write` 이후 관련 cache 갱신 또는 invalidation
- Motion Server 외부 commissioning 변경의 refresh 정책
- readback 실패 시 이전 값 유지 또는 invalid 처리 정책
- 다중 항목의 atomic update와 Diagnostic 연동
- RF-005가 동기 호출한 PySOEM Axis restart/Bus reconnect 완료 전 대상 cache refresh
- restart/reconnect 후 readback 실패 항목의 invalid 처리와 MotionController/API 사용 차단
- device profile별 cache provider 확장 경계

## 제외 범위

- TD-023이 소유하는 CMMT startup, Mock reset 직후 필수 축 parameter 동기화
- 주기 제어 중 SDO polling
- parameter write 시 자동 영구 저장
- 서버 재시작 후 virtual parameter restore
- Persistent Store, 변경 이력, export/import와 실장비 commissioning transfer

## RF-005와의 경계

- RF-005는 실축 restart 완료 감지, EtherCAT 연결 복구와 상태 전이를 책임진다.
- RF-005는 `refresh_after_recovery(runtime, recovery_type, affected_axes)`를 복구 완료 전에
  동기 호출한다. 현재 adapter는 TD-023의 Axis cache refresh를 사용한다.
- TD-025는 이 호출 경계 안에서 OD readback, cache 갱신/invalid 처리와 제어 projection
  재동기화를 확장하며 공개 event bus는 만들지 않는다.

## RF-017과의 경계

- TD-025의 Runtime Parameter Cache는 실행 중 현재값과 validity를 표현한다.
- RF-017의 Persistent Parameter Store는 사용자가 `parameter_save`로 commit한 snapshot과 변경
  이력을 저장한다.
- parameter write는 TD-025 cache만 갱신 또는 invalid 처리하며 영구 저장하지 않는다.
- parameter save는 RF-017이 담당하고, 저장 대상 현재값은 TD-025 cache snapshot 또는 명시적
  device readback 결과를 사용한다.
- 서버 재시작 시 virtual device는 기본 OD를 초기화한 뒤 RF-017 store 값을 적용하고, TD-025 cache는
  적용된 device state readback으로 다시 구성된다.

## 구현 단계

### S01 공통 Runtime Parameter 모델

- 상태: `complete`
- 공통 `RuntimeParameterAddress`, `RuntimeParameterDefinition`, `RuntimeParameterValue`,
  `RuntimeParameterCache`를 추가한다.
- source type은 `server`, `bus`, `axis`, `io`를 지원한다.
- domain은 `ethercat_od`, `ethercat_od_group`, `axis_projection`, `ap_parameter`, `iol_isdu`를
  지원한다.

### S02 Axis provider projection 연동

- 상태: `complete`
- 기존 `AxisParameterRuntimeCache`를 유지하되 공통 `RuntimeParameterCache`에 definition/value를
  함께 등록한다.
- 기존 MotionController/status 사용 경로는 유지한다.
- refresh 실패 시 axis cache 항목을 invalid 처리할 수 있는 경계를 추가한다.

### S03 Recovery refresh Diagnostic 연동

- 상태: `complete`
- RF-005 recovery 후 axis parameter refresh 실패를 `PARAMETER_REFRESH_FAILED` Diagnostic으로
  보고한다.
- 실패한 axis cache value는 invalid 처리한다.
- 이후 refresh 성공 시 해당 Diagnostic을 resolve한다.

### S04 CPX station EtherCAT parameter provider

- 상태: `complete`
- `system/io/ethercat/param_read/write` 결과 중 서버가 보관해야 하는 항목을 공통 cache에 반영한다.
- 현재 TD-033에서 정리한 CPX station catalog scope와 일관되게 address를 구성한다.

### S05 CPX AP module / IO-Link ISDU provider

- 상태: `complete`
- `system/io/ap/param_read/write`, `system/io/iol/param_read/write` 결과를 공통 cache에 반영한다.
- AP/IOL parameter는 모든 항목을 자동 cache하지 않고 서버 상태/API/recovery에 필요한 항목만
  definition으로 등록한다.

### S06 명시적 refresh/snapshot 경계

- 상태: `complete`
- 공개 refresh API는 만들지 않고 startup/recovery/parameter access 내부 경계에서 cache를 갱신한다.
- RF-017 Persistent Store가 사용할 수 있는 runtime cache snapshot 기반을 제공한다.

## 완료 조건

- CMMT와 CPX를 모두 표현할 runtime parameter definition/source/address 모델이 확정된다.
- 서버 제어와 status/API에 필요한 parameter만 cache 대상으로 선정된다.
- startup, parameter write, Bus reconnect, Axis restart 후 cache refresh/invalidation 경계가 구현된다.
- readback 실패는 조용한 fallback이 아니라 validity와 Diagnostic으로 표현된다.
- Persistent Store 및 commissioning transfer는 RF-017 범위로 명확히 제외된다.
- CMMT/CPX provider 단위 테스트와 recovery 연동 회귀 테스트가 통과한다.
