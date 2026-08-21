# TD-015 Virtual Servo Device Profile 기반 OD/PDO 구성 정리

## 배경 및 현재 구조

- Virtual Servo는 실제 slave SDO readback이 없어 내부 OD storage를 초기화해야 한다.
- 현재 OD 초기값은 `device/cmmt/required_od.py`의 `default`에 의존한다.
- `device/virtual_servo_drive/od_model.py`가 CMMT required OD를 직접 import한다.
- virtual axis의 PDO configuration 선택 정책이 실축 profile 정책과 분리되어 있다.

## 문제와 위험

- required OD 역할 정의와 Virtual Servo seed 역할이 한 파일에 섞인다.
- 선택한 device profile과 virtual OD/PDO seed가 어긋날 수 있다.
- mock과 실축 backend의 PDO 검증 조건이 달라질 수 있다.

## 관련 위치

- `device/cmmt/required_od.py`
- `device/cmmt/pdo_configuration.py`
- `device/virtual_servo_drive/.env`
- `device/virtual_servo_drive/od_model.py`
- `ethercat/mock_slave.py`
- `ethercat/mock_master.py`

## 목표 구조 및 구현 범위

- device profile이 required OD role과 PDO configuration registry를 제공한다.
- Virtual Servo는 선택된 device profile을 통해 OD seed와 PDO configuration을 구성한다.
- 축별 configuration 이름, profile 기본값과 잘못된 이름의 startup error를 지원한다.
- required OD metadata는 index/subindex/type/access/role 검증과 virtual seed 정책을 명확히 분리한다.

### Profile/ESI 기반 Virtual OD Model

[DEC-013](../../decisions.md)에 따라 `od_model.py`를 가상축 Object Dictionary의 단일 상태 경계로 사용한다.

- 선택된 device profile과 ESI에서 OD entry definition을 구성한다.
- OD Model은 index/subindex, datatype, access, default, runtime value, role과 PDO mapping metadata를 관리한다.
- required OD와 RxPDO/TxPDO object도 선택된 profile을 통해 공급하며 CMMT module을 직접 import하지 않는다.
- SDO와 PDO는 별도 storage를 만들지 않고 동일한 OD Model의 runtime value를 사용한다.
- Virtual Servo는 OD Model을 직접 읽고 쓰며 CiA402/motion behavior를 수행한다.
- `od_bridge.py`는 value를 별도로 소유하지 않고 SDO/RxPDO/TxPDO 접근을 OD Model에 연결한다.

```text
Device Profile + ESI
        -> OD Model (definition + runtime value)
             <-> Servo Model
             <-> OD Bridge (SDO, RxPDO, TxPDO)
```

## 검증 계획

- 여러 axis/profile/configuration 조합과 기본값을 테스트한다.
- 동일 OD entry를 SDO와 PDO로 접근했을 때 같은 runtime value와 side effect가 보이는지 테스트한다.
- 잘못된 profile/configuration, required OD 누락과 mock/real policy 일치를 테스트한다.

## 완료 증거

완료 시 profile contract, 제거된 직접 의존과 OD/PDO 선택 테스트 결과를 기록한다.
