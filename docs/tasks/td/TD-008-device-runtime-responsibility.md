# TD-008 Device 및 Runtime 책임이 큰 모듈

## 배경 및 현재 구조

CMMT profile, CPX module layout, virtual servo, PySOEM master와 server가 각각 여러 lifecycle 책임을 가진다.

## 관련 위치

- `device/cmmt/profile.py`
- `device/cpx_ap_i_ec/module_layout.py`
- `device/virtual_servo_drive/servo_model.py`
- `ethercat/pysoem_master.py`
- `motion_server/server.py`

## 목표 구조 및 구현 범위

- catalog/configuration, PRE_OP setup, runtime PDO, diagnostics와 recovery 책임을 구분한다.
- 각 책임의 public interface와 dependency 방향을 문서화한다.
- 동작 변경 없이 작은 단계로 분리하고 각 단계에 characterization test를 둔다.

## 기술 제약

실장치 lifecycle과 EtherCAT state transition 순서를 변경하는 단계는 mock 검증만으로 완료하지 않는다.

## 검증 계획

- 기존 public behavior를 mock regression test로 고정한다.
- CMMT와 CPX startup, cyclic PDO와 recovery smoke test를 수행한다.

## 완료 증거

완료 시 책임 구조도, public interface, 회귀 및 실장치 시험 결과를 기록한다.
