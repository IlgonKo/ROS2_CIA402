# TD-010 자동 테스트 부재

## 배경 및 현재 구조

`diagnostics/pysoem_single_axis_smoke_test.py` 외에 독립적인 회귀 test suite와 CI 기준이 부족하다.

## 우선 테스트 범위

- config continuation과 bus/module/IODD parser
- CMMT ESI root/subindex와 PDO configuration 검증
- CPX process image offset과 codec
- API authority, routing, serialization과 unit conversion
- virtual servo state machine, homing, limit, stop/jog

## 목표 구조 및 구현 범위

- 빠른 unit test, mock integration test와 실장치 smoke test를 분리한다.
- 실장치가 없는 clean environment에서 기본 suite가 재현되게 한다.
- fixture, marker/profile과 실패 보고 형식을 표준화한다.

## 기술 제약

EtherCAT timing과 실제 drive behavior 검증은 CI mock test로 대체하지 않고 별도 hardware profile로 유지한다.

## 검증 계획

- clean checkout 기준 설치 및 test command를 검증한다.
- CI에서 기본 suite를 실행하고 hardware suite는 명시적 실행으로 분리한다.

## 완료 증거

완료 시 CI workflow, test inventory, 실행 시간과 hardware smoke-test 결과를 기록한다.

