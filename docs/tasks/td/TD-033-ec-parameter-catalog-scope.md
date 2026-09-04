# TD-033 CPX EtherCAT Parameter Catalog 응답 일관화

## 상태

- 상태: `complete`
- 우선순위: 보통
- 등록일: 2026-09-01
- 관련 항목: TD-032, RF-001, RF-002, RF-012

## 배경

실장치 CPX-AP-I-EC 진단 중 `0x6101`, `0x6102` 같은 diagnosis object와
`0x1000`, `0x1001`, `0x1018`, `0x10F3`, `0x1C12`, `0x1C13` 같은 EtherCAT general object를
직접 SDO read로 사용했다.

하지만 현재 `system/io/ethercat/param_catalog`는 설정된 AP module의 ESI object를 반환하는
구조라서, 실제로 읽을 수 있는 CPX-AP-I-EC 본체 OD가 catalog와 IO Control Panel의 EC Parameter
목록에 충분히 표시되지 않는다.

이 때문에 사용자는 장치에 존재하는 진단/일반 OD를 알기 어렵고, catalog에 없더라도 수동 index로
직접 접근해야 한다.

## 현재 구조

현재 EC Parameter catalog는 다음 흐름으로 구성된다.

```text
system/io/ethercat/param_catalog
→ 선택한 io device
→ 선택한 CPX-AP-I-EC station
→ station/device-level ESI object 목록 반환
```

station ESI object는 device profile에서 파싱되어 runtime/virtual OD 구성 등에 사용되지만,
catalog payload에서는 AP module object 중심 구현 때문에 충분히 노출되지 않았다.

## 문제

- EtherCAT general object가 catalog에 표시되지 않는다.
  - `0x1000` Device type
  - `0x1001` Error register
  - `0x1008` Device name
  - `0x1009` Hardware version
  - `0x100A` Software version
  - `0x1018` Identity object
- diagnosis 관련 object가 catalog에 표시되지 않는다.
  - `0x10F1` Error settings
  - `0x10F3` Diagnosis history
  - `0x10F8` Timestamp
  - `0x6101`, `0x6102` 계열 station/module diagnosis
- sync/PDO assignment object가 catalog에 표시되지 않는다.
  - `0x1600...0x17FF`
  - `0x1A00...0x1BFF`
  - `0x1C12...0x1C13`
  - `0x1C32...0x1C33`
- 사용자는 process data가 정상인지, station diagnosis가 있는지 구분하기 어렵다.

## 결정 사항

- EC Parameter catalog는 실제 SDO read/write 후보를 찾기 위한 표시 기능이다.
- 이 catalog를 이용해 PDO mapping을 구성하지 않는다.
- 따라서 `PdoMapping` 또는 `ro p`의 `p` 정보는 별도 `pdo_mapping` 필드로 노출하지 않는다.
- 문서상 `ro p`는 catalog 응답에서는 `access: "ro"`로 표시한다.
- `system/io/ethercat/param_catalog`는 CPX-AP-I-EC 본체 EtherCAT OD catalog만 반환한다.
- AP module별 parameter catalog는 `system/io/ap/param_catalog`에서 별도로 다룬다.
- 따라서 `system/io/ethercat/param_catalog`는 `module` 또는 `slot` 입력을 받지 않는다.
- 사용자에게 필요한 구분은 `scope`와 `group`으로 제공한다.

권장 group:

- `station`
- `identity`
- `diagnosis`
- `sync`
- `pdo_mapping`

## 구현 계획

1. CPX station ESI object를 EC Parameter catalog payload에 포함한다.
2. 기존 `system/io/ethercat/param_catalog`의 module/slot selector 동작은 제거한다.
3. 각 object에 사용자가 구분할 수 있는 `group` 정보를 추가한다.
4. `pdo_mapping` 필드는 추가하지 않는다.
5. `ro p`는 `access: "ro"`로 표시한다.
6. IO Control Panel EC Parameter 탭은 station-level EtherCAT OD catalog를 표시한다.
7. 대표 station/general/diagnosis/sync object가 catalog에 포함되는 회귀 테스트를 추가한다.

## 제외 범위

- catalog를 이용한 PDO remapping 기능
- `PdoMapping` 속성 노출
- diagnosis message payload의 완전한 해석
- RF-012의 CPX Diagnostic 상태 모델 구현
- TD-032의 IO-Link ISDU parameter access 경로 확정

## 완료 조건

- `system/io/ethercat/param_catalog`가 설정된 CPX station의 station-level object를 반환한다.
- `module` 또는 `slot` selector가 들어오면 `INVALID_ARGUMENT`로 거부한다.
- catalog 응답에서 `station`, `identity`, `diagnosis`, `sync`, `pdo_mapping` 등 사용자가 구분할 수 있는
  `scope`/`group` 정보를 제공한다.
- `ro p`는 `access: "ro"`로 표시하며 PDO mapping 구성용 `pdo_mapping` 필드는 추가하지 않는다.
- `0x1000`, `0x1001`, `0x1018`, `0x10F1`, `0x10F3`, `0x10F8`, `0x1600...`,
  `0x1A00...`, `0x1C12...`, `0x1C13`, `0x1C32...` 계열 대표 object가 catalog에 노출된다.
- IO Control Panel EC Parameter 탭에서 CPX 본체 EtherCAT parameter와 AP module parameter가 섞이지 않는다.
- 관련 unittest가 통과한다.
