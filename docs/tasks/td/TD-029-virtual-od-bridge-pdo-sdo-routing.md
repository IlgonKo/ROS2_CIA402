# TD-029 Virtual OD Bridge의 PDO/SDO-OD 연결 복원

## 배경 및 문제

TD-028에서 장치별 reset/save 동작을 Bridge 밖으로 분리한 뒤 책임을 추가로 축소하는 과정에서
`rxpdo_to_od()`와 `od_to_txpdo()`까지 제거하고 PDO 처리를 Virtual Servo로 이동했다.

그러나 Virtual OD Bridge의 원래 목적은 MockSlave가 수신한 SDO와 PDO를 하나의 OD Model에
연결하는 것이다. SDO는 요청의 index/sub-index로 OD를 직접 식별하고, PDO는 payload에 OD 주소가
없으므로 선택된 `PDO_Configuration`의 mapping으로 OD를 식별해야 한다. Virtual Device는 PDO
객체가 아니라 Model_Update command를 받을 때 현재 OD 상태를 반영해 처리 결과를 OD에
기록해야 한다.

## 확정 책임 경계

### PDO_Configuration

- RxPDO/TxPDO에 포함되는 OD index, sub-index, 순서와 data type의 단일 원본이다.
- CMMT와 CPX의 장치별 process image 차이를 각 configuration에서 표현한다.
- 공통 Bridge가 사용할 RxPDO/TxPDO mapping 계약을 제공한다.

### VirtualOdBridge

- SDO 요청의 index/sub-index를 OD Model read/write에 연결한다.
- `PDO_Configuration`의 mapping을 사용해 raw RxPDO payload를 OD Model에 기록한다.
- `PDO_Configuration`의 mapping을 사용해 OD Model에서 raw TxPDO payload를 생성한다.
- OD access 검증과 raw SDO payload encode/decode를 담당한다.
- PdoCodec이나 장치별 RxPDO/TxPDO 객체를 직접 참조하지 않는다.
- 장치 명령의 의미, 상태 전이와 simulation은 담당하지 않는다.

### Virtual Device

- RxPDO/TxPDO 객체나 `PDO_Configuration`을 직접 참조하지 않는다.
- OD write 자체에는 직접 반응하지 않는다.
- Model_Update command를 받을 때 현재 OD 상태를 읽고 명령, 상태기계, 시간 진행과 물리
  simulation을 계산한다.
- 장치 내부 상태 전이와 처리 결과를 OD Model에 기록한다.
- reset/save/AP/ISDU 등 장치별 내부 반응만 담당한다.

### Master 및 MockSlave

- TD-030 후 MockMaster와 PySOEMMaster의 공통 `MasterPdoRuntime`이 RxPDO/TxPDO 객체와
  `DeviceProfile.pdo_codec`을 소유한다.
- Master가 RxPDO 객체를 raw payload로 encode하고 raw TxPDO payload를 TxPDO 객체로 decode한다.
- MockSlave는 raw RxPDO를 Bridge에 전달하고 OD 반영 뒤 Virtual Device에 Model_Update command를
  전달한 후 Bridge의 raw TxPDO를 반환한다.
- 전체 cycle은 `Master RxPDO -> codec -> raw RxPDO -> OD -> Model_Update -> OD -> raw TxPDO ->
  codec -> Master TxPDO` 순서다.
- MockSlave는 PDO 객체, codec, 장치 종류와 OD role 의미를 알지 않는다.

## 구현 단계

- S01: `PDO_Configuration` 기반 Bridge 생성 계약을 적용한다.
- S02: raw payload 기반 `rxpdo_payload_to_od()`와 `od_to_txpdo_payload()`를 공통 Bridge에
  구현한다.
- S03: SDO/PDO write와 Virtual Device 반응 사이의 직접 callback을 제거한다.
- S04: Virtual Servo의 RxPDO/TxPDO 직접 참조를 제거하고 Model_Update 시점의 OD 상태 반영으로
  전환한다.
- S05: Mock cycle과 SDO 처리 순서를 새 계약으로 정리한다.
- S06: SDO 직접 주소 접근, PDO mapping 접근과 장치 반응 회귀 테스트를 추가한다.
- S07: TD-028, RF-001과 Decision/Worklog 문서를 새 책임 경계로 정합화한다.

## 제외 범위

- Virtual CPX 구현
- CPX `PDO_Configuration`의 구체적인 module OD mapping 작성
- 실제 EtherCAT command sequence 또는 공개 API 변경
- Motion Server runtime parameter cache 변경

## 완료 조건

- SDO는 요청의 index/sub-index로 OD Model을 직접 read/write한다.
- PDO는 선택된 `PDO_Configuration`만을 mapping 원본으로 사용해 OD Model과 양방향 연결된다.
- `PDO_Configuration`을 Bridge에 전달하는 것은 raw PDO와 OD의 변환 규칙을 제공하는 것이며,
  PRE-OP에서 device의 PDO assignment/mapping OD를 SDO write하고 readback하는 startup 절차를
  대체하지 않는다. Mock startup parity는 TD-030에서 완성한다.
- Mock/PySOEM Master는 실제 장비 경로와 동일한 `DeviceProfile.pdo_codec`으로 PDO 객체와 raw
  payload를 변환한다.
- Virtual Servo는 RxPDO/TxPDO 객체를 직접 참조하거나 OD write callback을 받지 않고
  Model_Update만 입력으로 사용한다.
- MockSlave는 Servo 패키지나 장치별 role에 의존하지 않는다.
- reset/save 장치 반응과 기존 Mock/PySOEM 공통 sequence가 유지된다.
- SDO와 PDO가 같은 OD runtime value를 사용하고 cycle 순서가 검증된다.
- 전체 자동 테스트와 변경 형식 검사가 통과한다.

## 완료 증거

- `VirtualOdBridge`를 `device.virtual_device` 공통 영역으로 이동하고 Servo 패키지 의존성을
  제거했다.
- SDO는 요청의 index/sub-index로 OD를 직접 read/write하고, raw PDO payload는 생성 시 전달된
  `PDO_Configuration.rxpdo_objects()`/`txpdo_objects()`만 mapping 원본으로 사용한다.
- Bridge의 `rxpdo_payload_to_od()`와 `od_to_txpdo_payload()`가 OD Model을 중심으로 양방향 raw
  PDO payload를 연결한다.
- Virtual Servo에서 RxPDO/TxPDO 인자와 OD write callback을 제거했다.
- `VirtualCiA402Servo.model_update()`가 현재 OD의 reset/save/mode/target command를 반영한 뒤
  CiA 402 상태기계와 motion model을 갱신한다.
- TD-030에서 codec과 PDO 객체를 공통 `MasterPdoRuntime`으로 이동했다. `MockSlave`의
  `exchange_processdata()`는 raw RxPDO를 OD에 반영하고 Model_Update 뒤 raw TxPDO를 반환한다.
  SDO write도 먼저 OD에 반영한 뒤 별도 `model_update()` 단계로 장치 반응을 계산한다.
- device reset은 master의 PDO 객체를 직접 초기화하지 않고 Virtual OD의 PDO runtime value를
  초기화한다.
- OD 값 encode/decode를 `device.od_value_codec`으로 공통화하여 CMMT PDO와 Virtual SDO가 같은
  변환 규칙을 사용한다.
- Bridge 직접 SDO write에는 Virtual Device 반응이 없고 Model_Update 후에만 결과 OD가
  갱신되는 테스트, `PDO_Configuration` 양방향 mapping 테스트와 reset/save 회귀 테스트를
  추가했다.
- 2026-08-26 전체 unittest 289개와 source compile 및 diff whitespace 검사가 통과했다.
