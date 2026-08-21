# TD-007 Control Panel 중복 및 대형 모듈

## 배경 및 현재 구조

- IO Control Panel이 약 1,200줄의 단일 모듈이다.
- Axis Diagnosis와 IO Panel이 catalog data type/length/label 변환을 중복 구현한다.
- ROS Control Panel도 약 1,200줄의 단일 모듈이다.

## 관련 위치

- `control_panel/io_control_panel/control_panel.py`
- `control_panel/axis_control_panel/diagnosis.py`
- `ros/control_panel.py`

## 목표 구조 및 구현 범위

- catalog type/length/label 변환을 GUI 독립적인 공통 utility로 이동한다.
- IO/ROS Panel을 connection, state, parameter tabs와 view builder 단위로 분리한다.
- 기존 실행 entrypoint와 사용자 동작을 유지한다.

## 기술 제약

GUI toolkit object는 domain/state 계층으로 전달하지 않으며, packaging import 경로 변경을 함께 검증한다.

## 검증 계획

- 공통 catalog utility 단위 테스트를 추가한다.
- 연결, 상태 갱신, parameter read/write와 종료 동작을 smoke test한다.

## 완료 증거

완료 시 모듈 책임 표, 중복 제거 결과와 panel 검증 결과를 기록한다.

