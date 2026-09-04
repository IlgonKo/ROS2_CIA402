# TD-026 실장치 Identity 불일치의 초기화 오류 경계 정리

## 상태

- 상태: `complete`
- 우선순위: 보통
- 등록일: 2026-08-26
- 완료일: 2026-09-04
- 관련 항목: TD-018, RF-005

## 배경 및 현재 구조

PySOEM startup은 PRE-OP에서 실제 slave identity를 읽고 `MOTION_SERVER_BUS`에 선언된
DeviceProfile과 실제 EtherCAT slave가 일치하는지 검증해야 한다.

현재 CMMT-AS/CMMT-ST profile은 product code mismatch를 검출하지만 일반 `RuntimeError`를
발생시킨다. CPX-AP-I-EC profile은 ESI에 vendor/product/revision 정보를 가지고 있지만,
station 자체의 EtherCAT identity 검증이 명확하지 않고 AP module ident/layout 검증과 PDO
mapping 검증만 수행한다.

최상위 초기화 경계는 이러한 예상 가능한 mismatch를 안정적인 initialization cause로 보고해야 한다.

## 문제와 위험

- 예상 가능한 commissioning/configuration 불일치가 내부 Python runtime 충돌처럼 보일 수 있다.
- `BUS_CONNECTION_FAILED`만으로는 adapter 연결 실패와 slave identity 불일치를 구분할 수 없다.
- 상세 문자열과 traceback에 의존하면 API의 안정적인 cause 계약과 구현 언어 독립성이 약해진다.
- 실제 slave를 읽은 뒤에만 확인 가능한 오류이므로 단순 정적 configuration validation으로
  옮길 수 없다.
- CPX station identity mismatch, CPX AP module layout mismatch, PDO mapping mismatch가 서로
  다른 원인인데 같은 오류처럼 보일 수 있다.

## 관련 위치

- `device/cmmt/profile.py`
- `motion_server/app/startup.py`
- `motion_server/app/initialization.py`
- `motion_server/server.py`
- `tests/test_initialization_lifecycle.py`
- `tests/test_degraded_server_contract.py`

## 목표 구조 및 구현 범위

- 실제 device identity/profile 불일치를 검출 지점에서 typed device exception으로 전달한다.
- adapter 연결 실패, slave 수/layout 불일치, AP module layout 불일치, profile identity 불일치와
  PDO mapping mismatch의 안정적인 cause 경계를 정의한다.
- 공개 `InitializationFailure`에는 안정적인 cause와 안전한 메시지만 노출한다.
- 예상된 검증 실패는 일반 traceback 없이 간결한 구조화 로그로 남긴다.
- 예상하지 못한 내부 exception은 DEC-025의 최상위 initialization boundary에서 traceback을 한 번 기록한다.
- 초기화 실패 후에는 불완전한 runtime이나 가상 장치를 만들지 않고 기존 degraded server 계약을 유지한다.
- `system/server/status`, `system/bus/status`, Diagnostic과 recovery scope의 일관성을 검증한다.

## 결정 사항

- identity mismatch 전용 `DeviceIdentityMismatchException`과
  `InitializationCause.DEVICE_IDENTITY_MISMATCH`를 추가한다.
- stage는 PRE-OP bus connection 중 실제 slave identity를 읽는 현재 lifecycle에 맞춰
  `BUS_CONNECTION`으로 둔다.
- 공개 `InitializationFailure`에는 안정적인 cause/message만 노출한다.
- 상세 slave index, expected/actual vendor/product code는 서버 로그 detail에만 남긴다.
- CMMT는 expected product code와 actual product code를 비교한다.
- CPX-AP-I-EC는 expected vendor id/product code와 actual vendor id/product code를 비교한다.
- CPX AP module ident mismatch는 station identity mismatch가 아니므로 `DEVICE_LAYOUT_INVALID`로
  유지한다.
- PDO mapping mismatch는 `PDO_CATALOG_MISMATCH`로 유지한다.

분류 기준:

```text
Wrong EtherCAT slave at configured bus position
→ DEVICE_IDENTITY_MISMATCH

Right CPX station, wrong AP module order/type
→ DEVICE_LAYOUT_INVALID

Right device/layout, but actual PDO mapping differs from expected catalog/config
→ PDO_CATALOG_MISMATCH
```

## 제외 범위

- DEC-025 계열의 degraded server 유지 정책 변경
- EtherCAT slave 자동 profile 추론 또는 `.env` 자동 수정
- PDO mapping, ESI catalog 및 장치 commissioning 절차 자체의 변경

## 검증 계획

- CMMT-AS/CMMT-ST product code 불일치를 주입해 typed cause와 공개 메시지를 검증한다.
- CPX-AP-I-EC vendor/product code 불일치를 주입해 typed cause와 공개 메시지를 검증한다.
- 예상된 identity 불일치에는 Python traceback이 출력되지 않는지 검증한다.
- 예상하지 못한 내부 오류에는 traceback이 정확히 한 번 기록되는지 검증한다.
- 실패 후 runtime이 제거되고 상태/Diagnostic API만 허용되는지 검증한다.
- 올바른 identity의 Mock/PySOEM startup과 bus reconnect 회귀를 검증한다.

## 완료 기록

- `DeviceIdentityMismatchException`과 `DEVICE_IDENTITY_MISMATCH` initialization cause를 추가했다.
- CMMT profile mismatch는 일반 `RuntimeError` 대신 typed identity mismatch exception으로 분류한다.
- CPX-AP-I-EC station은 PRE-OP process-image 준비 전에 vendor/product identity를 검증한다.
- CPX AP module ident mismatch와 PDO mapping mismatch는 각각 기존 `DEVICE_LAYOUT_INVALID`,
  `PDO_CATALOG_MISMATCH` 경계로 유지했다.
- 관련 초기화, mock transport, CPX process image 테스트와 전체 unittest 397개가 통과했다.
