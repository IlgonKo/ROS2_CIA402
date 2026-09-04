# RF-017 Persistent Device Parameter Store and Commissioning Transfer

- 등록일: 2026-09-04
- 상태: `planned`
- 우선순위: 보통
- 관련 항목: TD-025, RF-003, RF-013, RF-016

## 배경

현재 virtual device parameter는 서버 프로세스 안의 OD/runtime state에만 존재한다.
따라서 서버를 다시 시작하면 virtual CMMT/CPX/IO-Link parameter는 기본 preset 또는 설정값으로
초기화된다. 앞으로는 가상장치에서 조정한 commissioning parameter를 저장하고 변경 이력을 관리한
뒤, 필요 시 같은 값을 실장비로 이전할 수 있어야 한다.

이 기능은 실행 중 제어용 cache인 TD-025와 성격이 다르다. TD-025의 Runtime Parameter Cache는
빠른 제어/status projection을 위한 현재값이고, RF-017의 Persistent Store는 사용자가 명시적으로
저장한 commissioning snapshot과 변경 이력의 원본이다.

## 핵심 계약

```text
parameter write
→ Device OD / AP parameter / IO-Link ISDU 변경
→ Runtime Parameter Cache 갱신 또는 invalidation
→ 영구 저장 안 함

parameter save
→ 현재 runtime/cache 또는 device readback snapshot 수집
→ Persistent Store에 snapshot commit
→ 변경 이력 revision 기록

server restart
→ Virtual Device 기본 OD 초기화
→ Persistent Store 값 조회
→ Virtual Device OD / AP / ISDU parameter space에 저장값 적용
→ Runtime Parameter Cache는 적용된 device state readback으로 다시 구성
```

## 범위

- CMMT Axis OD, CPX station EtherCAT OD, CPX AP module parameter, IO-Link ISDU parameter를
  식별할 공통 persistent parameter address model
- virtual device parameter save와 서버 재시작 후 restore
- 별도 maintenance/commissioning tool을 통한 Virtual Device 초기화
- 실장비 parameter readback snapshot 저장
- 변경 이력 revision, timestamp, source, actor, note 관리
- 저장 profile export/import
- 저장된 virtual commissioning profile을 실장비에 명시적으로 apply하고 readback으로 verify하는 경계
- save/apply/verify의 부분 성공 및 실패 보고

## 제외 범위

- Runtime cycle 중 SDO polling
- parameter write 시 자동 영구 저장
- 서버 시작 시 Persistent Store 값을 실장비에 자동 적용
- 모든 device OD를 무조건 저장하는 full dump
- 외부 DB server 의존성
- 공개 Motion Server TCP API를 통한 Virtual Device 초기화

## Virtual Device 초기화

Virtual Device 초기화는 운전 중 일반 제어 API가 아니라 maintenance/commissioning 작업으로
분류한다. 따라서 1차 구현에서는 공개 Motion Server TCP API에 넣지 않고 별도 CLI 또는
`Motion Server Commissioning Tool`에서 제공한다.

초기화 동작은 다음 세 가지를 구분한다.

```text
Runtime reset
→ 현재 실행 중인 virtual device OD/AP/ISDU parameter space를 기본값으로 되돌림
→ Persistent Store는 변경하지 않음

Store reset
→ Persistent Store에 저장된 virtual parameter snapshot 삭제
→ 현재 실행 중인 runtime parameter는 변경하지 않음
→ 다음 서버 재시작 또는 명시적 restore 시 기본값 사용

Factory restore
→ Runtime reset + Store reset
→ virtual device를 저장 이력 없는 초기 commissioning 상태로 복원
```

초기화 tool은 대상 device/source를 명시적으로 받는다.

예시:

```text
motion-server-commissioning virtual reset-runtime --device axis0
motion-server-commissioning virtual reset-store --device io0
motion-server-commissioning virtual factory-restore --device axis0
```

공개 TCP API에 넣지 않는 이유:

- `reset`, `restart`, `fault_reset`, `parameter_save`와 의미가 섞이면 운전 중 사용자가 잘못 호출할
  위험이 있다.
- Virtual Device 초기화는 실제 장치 제어가 아니라 store/commissioning 관리 작업이다.
- Persistent Store 삭제나 factory restore는 복구 명령보다 파괴적이므로 일반 runtime client에서
  노출하지 않는 편이 안전하다.

## 권장 저장소

1차 구현은 SQLite 기반 local file store를 권장한다.

- Windows/Linux 양쪽에서 추가 서비스 없이 사용할 수 있다.
- snapshot과 history table을 분리하기 쉽다.
- export/import 및 diff 기능으로 확장하기 쉽다.
- repository에는 포함하지 않고 사용자 data/config 영역에 보관한다.

외부 DB 서버는 다중 장비/중앙 관리가 필요해진 뒤 별도 확장으로 검토한다.

## Persistent Parameter Address 초안

```text
PersistentParameterAddress
├─ device_id
├─ device_type
├─ instance_id
├─ domain
│  ├─ ethercat_od
│  ├─ ap_parameter
│  └─ iol_isdu
├─ axis | io | module | port
├─ index | subindex
├─ parameter_id | instance
└─ data_type
```

## Parameter Record 초안

```text
PersistentParameterRecord
├─ address
├─ value
├─ raw_value
├─ data_type
├─ source
│  ├─ virtual_parameter_save
│  ├─ real_device_readback
│  ├─ imported_profile
│  └─ user_override
├─ revision
├─ changed_at
├─ changed_by
└─ note
```

## 실장비 이전 원칙

- 실장비에는 자동 적용하지 않는다.
- 사용자가 명시적으로 선택한 profile/apply 명령에서만 write한다.
- 적용 전 target device identity, topology, module layout과 parameter compatibility를 확인한다.
- apply 후 device readback으로 verify한다.
- 실장비 내부 non-volatile save와 서버 Persistent Store 저장은 별도 단계와 별도 결과로 보고한다.
- Virtual Device 초기화 tool은 실장비에 적용되지 않는다. 실장비 parameter 변경은 별도의
  explicit apply/verify 경로만 사용한다.

## TD-025와의 경계

- TD-025는 실행 중 현재값, validity, refresh와 control/status projection을 담당한다.
- RF-017은 저장된 snapshot, 변경 이력, restart restore와 실장비 transfer를 담당한다.
- `parameter_save` 명령에서 RF-017은 TD-025가 제공하는 현재 cache snapshot 또는 명시적 device
  readback 결과를 저장 대상으로 사용한다.
- Persistent Store 값은 주기 제어에 직접 사용하지 않는다. restore 후 Runtime Cache가 device
  state readback으로 다시 구성된 뒤 제어에 사용된다.

## 완료 조건

- persistent address/record/schema와 저장 위치가 확정된다.
- virtual CMMT와 virtual CPX/IO-Link parameter save 및 restart restore가 동작한다.
- Virtual Device runtime reset, store reset과 factory restore가 별도 maintenance/commissioning
  tool로 제공된다.
- Virtual Device 초기화 기능은 공개 Motion Server TCP API에 노출되지 않는다.
- parameter write만으로는 영구 저장되지 않고 save 명령만 snapshot commit을 수행한다.
- 저장 profile export/import가 가능하다.
- 저장된 virtual profile을 실장비에 명시적으로 apply하고 readback verify하는 smoke test가 제공된다.
- 부분 적용 실패와 실장비 internal save 실패가 서버 store 저장 실패와 분리되어 응답된다.
- SQLite store migration 및 history 조회 테스트가 통과한다.
