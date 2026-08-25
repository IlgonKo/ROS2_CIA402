# RF-005 Runtime Fault 및 Recovery 모델 완성

## 목표

runtime fault의 상태, 사용자에게 보이는 진단 정보와 reset/reconnect/restart의 책임 경계를 일관되게 만든다.

## 구현 범위

- normal, initialization-error, bus-disconnected와 recoverable-fault 상태 및 전이를 정의한다.
- `system/server/reset`, `system/bus/reconnect`와 process restart의 허용 조건을 정한다.
- PySOEM Axis restart의 완료 감지, timeout, EtherCAT 재연결과 복구 완료 통지 경계를 정의한다.
- runtime 재구성 전후 authority 소유권과 client notification을 정의한다.
- 실패한 복구와 반복 오류의 degraded behavior를 정의한다.
- latching Fault의 공통 acknowledge API와 resolve 이후 clear 처리를 구현한다.
- bus reconnect가 resolve한 Initialization Fault는 공통 acknowledge 명령을 받은 뒤 clear한다.

## 관련 작업

runtime 생성 단계의 degraded startup 세부 구조는 [TD-018](../td/TD-018-runtime-initialization-error.md)에서 추적한다.
공통 Diagnostic 객체와 clear 조건은 [Diagnostic 데이터 모델](../../diagnostic/diagnostic_model.md)을 따른다.
Definition에서 제외한 recovery policy와 handler 연결은 이 RF에서 확정한다.
server reset/process restart는 Diagnostic 저장소를 초기화하지만 bus reconnect는 기존 저장소를
유지한다. 이때 남는 resolved Initialization Fault의 acknowledge/clear도 이 RF에서 처리한다.
복구 완료 후 parameter OD refresh와 cache invalid 처리는
[TD-025](../td/TD-025-runtime-parameter-cache.md)가 담당한다.

## 검증 계획

- mock backend에 초기화, disconnect와 recoverable fault를 주입한다.
- 상태별 API 허용/거부, notification, authority와 재복구를 검증한다.
- 지원 실장치의 cable disconnect/reconnect와 drive fault recovery를 시험한다.

## 완료 증거

완료 시 state transition 표, API contract와 mock/실장치 시험 결과를 기록한다.
