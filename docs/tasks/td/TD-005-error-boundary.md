# TD-005 예외 경계와 오류 형식 불균일

## 배경 및 현재 구조

EtherCAT master, startup, SDO/AP/IOL parameter access와 Control Panel에서 broad
`except Exception`이 사용되며 서로 다른 실패가 문자열 오류로 합쳐질 수 있다.

## 문제와 위험

mailbox timeout, unsupported object, protocol validation과 programming error를 구분하기 어려워
client의 복구 판단과 장애 분석이 불안정하다.

## 관련 위치

- `ethercat/pysoem_master.py`
- `ethercat/sdo_access.py`
- `motion_server/app/startup.py`
- `motion_server/handlers/parameter_access/*`
- Axis/IO Control Panel

## 목표 구조 및 구현 범위

- Diagnostic 데이터 모델, API Success/Fail 계약, exception 지점 분류 순으로 선행 설계를 완료한 뒤
  구현 범위를 확정한다. 전체 순서는 [Diagnostic 문서](../../diagnostic/README.md#설계-및-구현-순서)를 따른다.
- 요청 응답은 [API Success/Fail 응답 계약](../../api/response_contract.md)의 공통 envelope로 migration한다.
- client가 의존하는 code는 [API Failure Code](../../api/failure_codes.md)의 catalog와 변환 원칙을 따른다.
- transport, protocol, validation과 runtime 오류 계층을 정의한다.
- 오류 유형을 안정적인 Motion Server API failure code에 매핑한다.
- 복구 가능한 오류만 해당 계층에서 처리하고 programming error는 숨기지 않는다.
- 최상위 process/client boundary의 broad exception 허용 정책을 문서화한다.

## 검증 계획

- timeout, unsupported object, invalid payload, initialization failure와 내부 오류를 주입한다.
- 각 오류의 API code, 메시지, logging과 connection 유지 여부를 검증한다.

## 조사 자료

- [Exception 발생 및 Catch 지점 전수 조사](../../diagnostic/error_point_inventory.md)
- 2026-08-21 기준 catch 144곳, broad catch 85곳, 명시적 raise 233곳과
  generic `RuntimeError` 42곳을 migration 대상으로 추적한다.

## 완료 증거

완료 시 오류 표, API 문서, broad exception 검사와 테스트 결과를 기록한다.
