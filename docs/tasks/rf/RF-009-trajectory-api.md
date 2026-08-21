# RF-009 Motion Server Trajectory API 정리

## 상태 및 재개 조건

별도 결정 전까지 개발을 보류한다. 단축 motion API와 runtime recovery model이 안정된 후 책임 범위를 확정한다.

## 목표

다축 trajectory command의 입력, lifecycle, mode별 지원과 상위 ROS trajectory의 책임 경계를 명확히 한다.

## 구현 범위

- `system/axes/trajectory`와 `system/axes/trajectory_stop` payload 및 단위를 정의한다.
- acceptance, progress, completion, cancel, stop와 Fail response를 정의한다.
- PP/PV/CSP별 지원 범위와 제한 조건을 정의한다.
- 반복 동작, 단축 move와 ROS trajectory 입력의 책임 경계를 결정한다.

## 안전 제약

software limit, velocity/acceleration limit, authority 상실, bus fault와 client disconnect 시 동작을 명시한다.

## 검증 계획

- virtual backend에서 validation, interpolation, cancel, limit와 fault path를 자동 테스트한다.
- 지원 mode별 실장치 저속 smoke test와 중단 동작을 검증한다.

## 완료 증거

완료 시 API specification, mode matrix, 자동 테스트와 실장치 안전 시험 결과를 기록한다.
