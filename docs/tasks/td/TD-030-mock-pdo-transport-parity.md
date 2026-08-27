# TD-030 Mock/실축 PDO 직렬화 책임 비대칭

## 배경 및 문제

TD-029에서 `VirtualOdBridge`와 Virtual Device를 PDO 객체 및 codec으로부터 분리했지만 PDO
직렬화의 소유 위치는 Mock와 PySOEM backend에서 아직 다르다.

- PySOEM은 Master가 `prepare_processdata()`에서 RxPDO 객체를 raw output으로 encode하고
  `receive_processdata()`에서 raw input을 TxPDO 객체로 decode한다.
- Mock는 `MockSlave.process()`가 `DeviceProfile.pdo_codec`을 직접 사용하여 RxPDO encode와
  TxPDO decode를 모두 수행한다.

이 비대칭 때문에 MockSlave가 raw slave endpoint와 Master-side PDO adapter 책임을 동시에 가지며,
Mock cycle이 실제 backend의 `prepare -> send -> receive` 경계를 그대로 검증하지 못한다. RF-001의
Virtual CPX를 현재 구조에 추가하면 이 책임 누수가 CMMT와 CPX 양쪽으로 확대된다.

따라서 TD-030은 RF-001의 선행 작업이다. TD-030을 완료하여 MockSlave를 raw endpoint로 축소한
후, RF-001의 Virtual CPX를 같은 MockMaster 및 MockSlave 계약 위에 추가한다.

## 목표 책임 경계

### MockMaster 및 PySOEMMaster

- Master-side runtime이 `RxPDO`, `TxPDO`와 `DeviceProfile.pdo_codec`을 소유한다.
- `prepare_processdata()`에서 현재 RxPDO 객체를 raw output buffer로 encode한다.
- `send_processdata()`에서 prepare된 raw output을 해당 cycle의 전송 snapshot으로 확정한다.
- prepare 후 RxPDO 객체가 변경되어도 이미 prepare된 snapshot에는 반영하지 않고 다음 cycle에서
  encode한다.
- `receive_processdata()`에서 수신 raw input을 TxPDO 객체로 decode한다.
- 두 backend는 같은 lifecycle 오류, buffer 갱신 순서와 관찰 가능한 PDO 계약을 제공한다.

### MockSlave

- raw PDO output을 수신하고 raw PDO input을 반환하는 virtual EtherCAT slave endpoint다.
- raw RxPDO를 `VirtualOdBridge`에 전달하고 Model_Update 이후 Bridge에서 raw TxPDO를 가져온다.
- raw SDO read/write endpoint를 제공한다.
- RxPDO/TxPDO 객체, `PdoCodec`과 Motion Server의 Master-side 상태를 소유하지 않는다.
- 장치별 OD role이나 command 의미를 해석하지 않는다.

### VirtualOdBridge 및 Virtual Device

- TD-029에서 확정한 경계를 유지한다.
- Bridge는 raw PDO/SDO와 OD Model만 연결한다.
- Virtual Device는 Model_Update 시점의 OD 상태에만 반응한다.
- PDO lifecycle이나 codec을 알지 않는다.

## 확정 Cycle 계약

```text
prepare
  Master RxPDO object
  -> Master PdoCodec encode
  -> prepared raw output

send
  prepared raw output
  -> transmitted snapshot 확정

receive
  transmitted snapshot
  -> MockSlave raw RxPDO endpoint
  -> VirtualOdBridge -> OD -> Model_Update -> OD
  -> MockSlave raw TxPDO endpoint
  -> Master PdoCodec decode
  -> Master TxPDO object
```

- `send_processdata()`는 선행 `prepare_processdata()`가 없으면 실패한다.
- `receive_processdata()`는 마지막으로 전송 확정된 snapshot만 처리한다.
- WKC, DC timestamp와 process-data timing field의 기존 공개 의미는 유지한다.
- SDO는 cyclic PDO phase와 분리된 raw request/response 경로를 계속 사용한다.

## 구현 단계

- S01: Mock/PySOEM의 prepare, send, receive별 PDO 관찰 동작을 characterization test로 고정한다.
- S02: Master-side slave runtime의 RxPDO/TxPDO/PdoCodec 소유 계약과 prepared/transmitted raw buffer를
  정의한다.
- S03: Mock의 PDO encode/decode를 MockSlave에서 MockMaster 측으로 이동한다.
- S04: MockSlave를 raw PDO exchange와 raw SDO endpoint로 축소하고 TD-029의 Bridge/Model_Update
  순서를 유지한다.
- S05: MockMaster의 prepare/send/receive 상태 전이, WKC와 timing 갱신을 PySOEM 경계와 정렬한다.
- S06: prepare 이후 RxPDO 변경, send 전후 snapshot, receive decode, 다중 slave와 실패 경로의
  backend parity test를 추가한다.
- S07: `DEC-034`, TD-029, RF-001, Remaining Tasks와 Work Log의 책임 설명을 최종 구조에 맞춘다.

## 제외 범위

- RF-001 Virtual CPX 구현
- CPX OD Model, module state 또는 PDO mapping 작성
- 실제 EtherCAT frame, datagram이나 network timing simulation
- 공개 Motion Server API 변경
- WKC/DC algorithm 및 recovery 정책 재설계
- Virtual Device의 장치별 동작 변경

## 후속 작업

- [RF-001](../rf/RF-001-cpx-virtual-io.md)은 TD-030 완료 후 구현한다.
- RF-001은 TD-030에서 확정한 Master-side codec과 raw MockSlave endpoint를 그대로 사용하며
  CPX 전용 우회 경로를 추가하지 않는다.

## 완료 조건

- MockMaster와 PySOEMMaster가 모두 Master 측에서 PDO encode/decode를 수행한다.
- 두 backend 모두 `prepare`에서 output을 생성하고 `send`에서 전송 snapshot을 확정하며
  `receive`에서 input을 decode한다.
- prepare 후 변경된 RxPDO가 이미 prepare된 snapshot을 바꾸지 않는 것이 자동 테스트로 검증된다.
- MockSlave는 raw PDO/SDO endpoint만 담당하고 RxPDO/TxPDO 객체나 PdoCodec을 소유하지 않는다.
- `VirtualOdBridge`와 Virtual Device의 TD-029 책임 경계가 유지된다.
- lifecycle 오류, 다중 slave, WKC와 timing field의 Mock/PySOEM parity가 검증된다.
- `DEC-034`, TD-029와 RF-001의 책임 설명이 최종 구조와 일치한다.
- 전체 자동 테스트, source compile과 diff whitespace 검사가 통과한다.

## 완료 증거

완료 시 변경된 Master/Slave 책임 구조, phase별 characterization/parity test와 전체 검증 결과를
기록한다.
