# TD-016 MockMaster의 Device-specific SDO 처리

## 배경 및 현재 구조

`ethercat/mock_master.py`가 `0x216E`, `0x2194`, `0x607D`, `0x6081`, `0x2005` 등
가상축 SDO object와 PDO field mapping의 device-specific 의미를 직접 처리한다.

## 문제와 위험

EtherCAT master 계층이 device semantics를 알아 실축 `PySOEMMaster`의 책임과 달라지고,
다른 virtual device가 추가될 때 MockMaster가 계속 커진다.

## 관련 위치

- `ethercat/mock_master.py`
- `ethercat/mock_slave.py`
- `device/virtual_servo_drive/od_model.py`
- `device/virtual_servo_drive/od_bridge.py`

## 목표 구조 및 구현 범위

- MockMaster는 generic SDO transport와 slave routing만 담당한다.
- mock slave 또는 virtual device가 `read_sdo()`/`write_sdo()` object access interface를 제공한다.
- OD/PDO mapping과 side effect는 해당 device의 bridge/model에서 관리한다.

### OD Model/Bridge 위임 계약

[DEC-013](../../decisions.md)에 따라 MockMaster와 MockSlave의 책임을 다음과 같이 고정한다.

- MockMaster는 slave index routing, payload 전달과 generic EtherCAT transport만 담당한다.
- MockSlave는 `read_sdo()`/`write_sdo()`를 제공하고 OD Bridge에 위임한다.
- OD Bridge는 SDO payload와 PDO mapping을 동일한 OD Model의 read/write로 연결한다.
- MockSlave의 cyclic process는 `RxPDO -> OD -> Servo update -> OD -> TxPDO` 순서로 수행한다.
- MockMaster와 MockSlave에는 CMMT OD index, CiA402 field 의미와 CPX module 의미를 하드코딩하지 않는다.

```text
MockMaster -> MockSlave -> OD Bridge -> OD Model <-> Virtual Device Model
```

## 검증 계획

- 기존 Virtual Servo의 SDO read/write와 PDO side effect를 regression test로 고정한다.
- 같은 object의 SDO/PDO access가 하나의 OD Model state를 공유하는지 검증한다.
- device-specific index를 모르는 MockMaster로 두 종류 이상의 virtual device를 연결한다.

## 완료 증거

- `MockMaster.write_sdo()`/`read_sdo()`는 slave index routing과 raw payload 전달만 수행한다.
- `MockSlave`가 object access interface를 제공하고 `VirtualOdBridge`에 위임한다.
- SDO datatype 변환은 OD metadata를 기준으로 수행하며 RxPDO/TxPDO와 동일한 OD runtime value를 사용한다.
- reset과 parameter save 부작용은 OD index가 아니라 profile의 OD role을 기준으로 Virtual OD Bridge가 처리한다.
- `ethercat/mock_master.py`와 `ethercat/mock_slave.py`에서 device-specific OD index와 CMMT 의존을 제거했다.
- 서로 다른 generic virtual slave routing, signed/float SDO, PDO 상태 공유와 parameter save 회귀 테스트를 추가했다.
- `python -m unittest discover -s tests -v`: 기존 TD-015 테스트를 포함한 8개 자동 테스트 통과.
- CMMT-AS 1축 mock의 전체 drive initialization과 CiA402 `Operation Enabled(0x0027)` 진입을 확인했다.
