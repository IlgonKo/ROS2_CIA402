# TD-028 Virtual OD Bridge의 장치 시퀀스 책임 제거

## 배경 및 문제

현재 `VirtualOdBridge.write_sdo()`는 OD write와 RxPDO 동기화 이후 Servo 전용 role을 직접
판단한다. `device_reset_command`에는 virtual device reset sequence를 실행하고,
`parameter_save_command`에는 save status와 return value를 생성한다.

이 구조에서는 Object Access adapter가 장치 명령의 의미와 상태 전이를 소유한다. RF-001에서
Virtual CPX를 추가할 경우 AP parameter, IO-Link ISDU와 CPX reset 분기가 같은 Bridge에 누적될
위험이 있다.

## 확정 책임 경계

### Motion Server 및 DeviceProfile

- 공개 restart/save command의 orchestration을 소유한다.
- 안전 상태 전이, command OD write, status readback, reconnect와 recovery를 수행한다.
- MockMaster와 PySOEMMaster에서 같은 sequence를 실행한다.

### VirtualOdBridge

- OD definition 조회 및 access 검증
- SDO payload encode/decode
- OD runtime value read/write
- RxPDO와 OD, OD와 TxPDO의 값 동기화
- 완료된 object write를 장치 의미 없이 호출자에게 반환

Bridge는 reset/save/AP/ISDU role을 해석하지 않는다.

### Virtual Device

- 실제 장치가 command OD write를 받은 뒤 나타내는 내부 반응만 모사한다.
- Virtual Servo는 reset 시 내부 상태와 OD/PDO 값을 초기화한다.
- Virtual Servo는 parameter save command에 대한 status/return code/value를 제공한다.
- 이 반응은 Motion Server sequence를 복제하거나 대신하지 않는다.

### MockSlave

- SDO write를 Bridge에 전달한다.
- Bridge가 반환한 definition/value를 Virtual Device의 공통 object-write hook에 전달한다.
- role의 의미나 reset/save sequence를 직접 구현하지 않는다.

## 구현 단계

- S01: Bridge의 Servo 전용 side-effect 경계를 characterisation test로 고정한다.
- S02: Bridge write 결과를 장치 독립적인 definition/value로 반환한다.
- S03: reset/save 내부 반응을 `VirtualCiA402Servo`로 이동한다.
- S04: `MockSlave`가 의미 해석 없이 Virtual Device hook을 호출하게 한다.
- S05: Bridge purity와 기존 Motion Server restart/save 회귀를 검증한다.
- S06: RF-001에서 재사용할 Virtual Device object-write 계약을 문서화한다.

## 제외 범위

- RF-001 Virtual CPX 구현
- Motion Server restart/save 공개 API 변경
- CMMT OD address 또는 command sequence 변경
- MockSlave의 전체 multi-device 생성 구조 변경

## 검증 계획

- Bridge에 reset command를 직접 write해도 다른 OD/PDO 값이 초기화되지 않는지 검증한다.
- 같은 command를 MockSlave를 통해 write하면 Virtual Servo가 reset 반응을 수행하는지 검증한다.
- parameter save status/return value가 Virtual Servo 반응으로 제공되는지 검증한다.
- 기존 Axis restart, cache refresh와 parameter save 테스트가 동일하게 통과하는지 검증한다.

## 완료 증거

- `VirtualOdBridge.write_sdo()`는 access 검증, decode, OD/RxPDO write 후 definition/value만 반환한다.
- Bridge에서 Servo role 분기, `_apply_write_side_effect()`와 `_restart_virtual_device()`를 제거했다.
- Virtual Servo가 `on_object_write()`에서 reset/save 명령에 대한 장치 내부 반응을 담당한다.
- `MockSlave`는 `virtual_device` 공통 속성과 hook을 사용하고 OD 의미를 해석하지 않는다.
- Bridge 단독 reset/save write에 side effect가 없고 MockSlave 경로에서는 기존 장치 반응이
  유지되는 테스트를 추가했다.
- 기존 Motion Server/CMMT restart·save 구현은 변경하지 않았으며 2026-08-26 전체 unittest
  286개와 diff whitespace 검사가 통과했다.
