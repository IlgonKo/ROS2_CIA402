# RF-003 예약된 Bus 및 I/O 관리 API

## 배경

다음 API name은 예약되어 있으나 장치별 의미와 lifecycle 계약이 확정되지 않았다.

- `system/bus/rescan`
- `system/io/reset`
- `system/io/restart`
- `system/io/param_save`

## 선행 결정

- 각 명령의 device별 의미와 지원 capability
- command authority 요구 여부
- 실행 중 cyclic PDO 중지, runtime 재구성과 client notification 정책
- 실패 후 rollback 또는 degraded state 정책

## 구현 범위

결정된 계약에 따라 specification, validation, handler, Fail response와 공개 문서를 구현한다.

## 검증 계획

- supported/unsupported device, authority 충돌과 runtime state별 명령을 테스트한다.
- virtual device에서 자동 복구 경로를 검증하고 지원 실장치에서 smoke test한다.

## 완료 증거

완료 시 관련 DEC, API 계약, capability matrix와 시험 결과를 기록한다.
