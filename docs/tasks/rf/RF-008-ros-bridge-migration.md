# RF-008 ROS Bridge 후속 이관 및 테스트

## 상태 및 재개 조건

별도 결정 전까지 개발을 보류한다. Motion Server API와 configuration 구조가 안정되고 관련 TD가 정리된 후 재개한다.

## 목표

ROS Bridge, ROS Control Panel과 Docker 구성을 최신 Motion Server 계약에 맞춘다.

## 구현 범위

- command namespace, authority, feedback와 axis/I/O status 변경을 반영한다.
- Motion Server mm/deg와 ROS SI unit 사이의 변환 경계를 확정한다.
- ROS Docker, Control Panel과 Bridge connection 설정을 공통 configuration model에 맞춘다.
- trajectory action/topic behavior와 error propagation을 최신 API에 맞춘다.

## 검증 계획

- mock/virtual backend에서 command, feedback, authority와 reconnect를 자동 검증한다.
- 실장치에서 joint state 및 trajectory smoke test를 수행한다.
- clean Docker 환경에서 build/start/test 절차를 재현한다.

## 완료 증거

완료 시 API mapping 표, unit conversion test와 Docker/실장치 시험 결과를 기록한다.
