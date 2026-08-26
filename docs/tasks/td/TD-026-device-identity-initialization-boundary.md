# TD-026 실장치 Identity 불일치의 초기화 오류 경계 정리

## 배경 및 현재 구조

PySOEM startup은 PRE-OP에서 실제 slave identity를 읽고 `MOTION_SERVER_BUS`에 선언된
CMMT-AS/CMMT-ST profile과 product code가 일치하는지 검증한다. 불일치하면 profile의
`validate_identity()`가 일반 `RuntimeError`를 발생시킨다. 최상위 초기화 경계는 이를
`BUS_CONNECTION_FAILED`로 변환해 degraded server를 유지하지만 원본 traceback도 출력한다.

## 문제와 위험

- 예상 가능한 commissioning/configuration 불일치가 내부 Python runtime 충돌처럼 보인다.
- `BUS_CONNECTION_FAILED`만으로는 adapter 연결 실패와 slave identity 불일치를 구분할 수 없다.
- 상세 문자열과 traceback에 의존하면 API의 안정적인 cause 계약과 구현 언어 독립성이 약해진다.
- 실제 slave를 읽은 뒤에만 확인 가능한 오류이므로 단순 정적 configuration validation으로
  옮길 수 없다.

## 관련 위치

- `device/cmmt/profile.py`
- `motion_server/app/startup.py`
- `motion_server/app/initialization.py`
- `motion_server/server.py`
- `tests/test_initialization_lifecycle.py`
- `tests/test_degraded_server_contract.py`

## 목표 구조 및 구현 범위

- 실제 device identity/profile 불일치를 검출 지점에서 typed initialization exception으로 전달한다.
- adapter 연결 실패, slave 수/layout 불일치와 profile identity 불일치의 안정적인 cause 경계를 정의한다.
- 공개 `InitializationFailure`에는 안정적인 cause와 안전한 메시지만 노출한다.
- 예상된 검증 실패는 일반 traceback 없이 간결한 구조화 로그로 남긴다.
- 예상하지 못한 내부 exception은 DEC-025의 최상위 initialization boundary에서 traceback을 한 번 기록한다.
- 초기화 실패 후에는 불완전한 runtime이나 가상 장치를 만들지 않고 기존 degraded server 계약을 유지한다.
- `system/server/status`, `system/bus/status`, Diagnostic과 recovery scope의 일관성을 검증한다.

## 결정 필요 사항

- identity mismatch 전용 `InitializationCause`를 추가할지, device layout 계열 cause를 확장할지 결정한다.
- 실제 topology 검증을 `BUS_CONNECTION`의 하위 단계로 유지할지 별도 initialization stage로 분리할지 결정한다.
- 안전한 공개 상세에 slave index, configured profile과 actual identity 중 어떤 필드를 포함할지 결정한다.

## 제외 범위

- DEC-025 계열의 degraded server 유지 정책 변경
- EtherCAT slave 자동 profile 추론 또는 `.env` 자동 수정
- PDO mapping, ESI catalog 및 장치 commissioning 절차 자체의 변경

## 검증 계획

- CMMT-AS/CMMT-ST product code 불일치를 주입해 typed cause와 공개 메시지를 검증한다.
- 예상된 identity 불일치에는 Python traceback이 출력되지 않는지 검증한다.
- 예상하지 못한 내부 오류에는 traceback이 정확히 한 번 기록되는지 검증한다.
- 실패 후 runtime이 제거되고 상태/Diagnostic API만 허용되는지 검증한다.
- 올바른 identity의 Mock/PySOEM startup과 bus reconnect 회귀를 검증한다.
