# RF-001 CPX-AP-I-EC Virtual I/O

## 사용자 가치

실제 CPX-AP-I-EC가 없어도 동일한 설정과 Motion Server API로 Remote I/O 기능을 개발하고 회귀 시험한다.

## 구현 범위

- `MOTION_SERVER_IO_<io>_MODULES`와 `MOTION_SERVER_IO_<io>_IOL_PORTS` 설정을 사용한다.
- DI/DO/AI/AO/IO-Link process image와 AP module layout을 모사한다.
- EtherCAT SDO와 AP parameter/IO-Link ISDU gateway OD의 request/response 전달 기반을 제공한다.
- gateway 뒤의 실제 AP module parameter 및 IO-Link ISDU runtime 공간은
  [RF-013](RF-013-virtual-ap-iol-parameter-devices.md)에서 구현한다.
- Motion Server와 IO Control Panel에서 실장치와 가상 장치를 같은 API로 처리한다.

## 기술 제약

실장치 고유 timing과 firmware fault를 완전히 모사한다고 간주하지 않으며 지원 차이를 명시한다.

## 확정 데이터 모델

```text
VirtualCpxApDevice
└─ VirtualApModule[]
   ├─ digital input/output state
   ├─ analog input/output state
   └─ IO-Link process-data buffer
```

- DI/DO/DIO/AI/AO/AIO/IO-Link마다 별도 class를 만들지 않고 ESI와 기존 `CPXApModule` metadata로
  동작하는 공통 `VirtualApModule`을 사용한다.
- 채널 수, process-image offset, byte width와 signed 여부는 기존 module layout을 단일 원본으로
  사용한다.
- Analog 값은 engineering unit으로 변환하지 않고 PDO raw integer로 보관한다.
- 값이 datatype 또는 channel 범위를 벗어나면 clamp하지 않고 거부한다.
- 특정 AP module firmware의 고유 반응은 RF-001에 포함하지 않는다.

## Virtual OD Model 구성

- CPX station ESI OD와 설정된 AP module의 ESI OD definition을 사용한다.
- 설정된 process-image 크기에 대응하는 PDO assignment/mapping과 `0x6F00`/`0x7F00` 16-byte
  block만 활성화한다.
- module-dependent object는 실제 AP module slot에 대응하는 OD index로 확장한다.
- 구성되지 않은 AP module의 module-dependent OD는 생성하지 않는다.
- runtime 초기값은 명시적인 virtual startup 값, ESI default, datatype 기본값 `0` 순서로 정한다.
- Identity, configured/detected module list와 PDO assignment는 device configuration과 ESI에서
  명시적으로 생성한다.

```text
RxPDO raw payload
→ VirtualOdBridge
→ 0x6F00 block OD
→ VirtualCpxApDevice.model_update()
→ Virtual module output state

Virtual module input state
→ VirtualCpxApDevice.model_update()
→ 0x7F00 block OD
→ VirtualOdBridge
→ TxPDO raw payload
```

## Process data 동작

- DO/AO/IO-Link Output의 단일 원본은 `0x6F00` process image이며 module output state는 이를
  Model_Update 시점에 해석한 결과다.
- DI 기본값은 `False`, AI 기본값은 `0`, IO-Link Input Process Data 기본값은 zero-filled
  payload다.
- Virtual module input state가 입력의 단일 원본이며 `0x7F00`은 Model_Update마다 생성되는
  보고값이다.
- DO-DI, AO-AI와 IO-Link output-input을 자동 loopback하지 않는다.
- IO-Link process data는 port별 raw byte buffer로만 처리하고 크기는 현재 IODD 및 선택된 module
  variant를 사용한다. IODD variable 의미에 따른 device 반응은 RF-001 범위가 아니다.

## 선행 책임 경계

- [TD-028](../td/TD-028-virtual-od-bridge-boundary.md)의 장치 sequence 분리와
  [TD-029](../td/TD-029-virtual-od-bridge-pdo-sdo-routing.md)의 공통 PDO/SDO-OD 연결 계약을
  사용한다.
- [TD-030](../td/TD-030-mock-pdo-transport-parity.md)을 먼저 완료하여 Mock/PySOEM의 PDO
  encode/decode를 Master 측으로 통일하고 MockSlave를 raw PDO/SDO endpoint로 축소한다.
- OD Model은 definition과 runtime value를 소유한다.
- 공통 OD Bridge는 SDO의 index/sub-index와 `PDO_Configuration`의 RxPDO/TxPDO mapping을 같은
  OD Model에 연결하되 raw PDO payload만 다룬다.
- MockMaster는 실제 CPX 경로에서 사용하는 기존 `CPXPdoCodec`으로 CPXRxPDO/CPXTxPDO 객체와
  raw payload를 변환한다. Virtual 전용 PDO codec이나 configuration은 만들지 않는다.
- Virtual Device는 PDO 객체를 직접 다루지 않고 Model_Update 시점의 OD 상태를 반영해 장치
  상태와 결과 OD를 갱신한다.
- MockSlave는 장치 의미를 해석하지 않고 raw PDO/SDO endpoint만 담당한다.
- Gateway request dispatch 경계는 `VirtualCpxApDevice`가 제공하지만 AP module과 IO-Link Device의
  실제 parameter 저장 및 반응은 RF-013의 하위 virtual device가 담당한다.
- Virtual input은 module state에 별도로 보관하고 Model_Update 시점에 TxPDO OD로 반영한다.
  RF-001은 내부 input injection 계약까지만 제공하며 Control Panel과 외부 simulator용 공개 API는
  [RF-014](RF-014-virtual-device-simulation-api.md)에서 구현한다.

## 후속 기능 경계

- Virtual CPX 신규 생성 시 process image와 모든 module input/output state를 기본값으로
  초기화한다.
- `system/io/reset`, `system/io/restart` API와 실제 device command sequence는
  [RF-003](RF-003-bus-io-management.md)에서 구현한다. RF-001에 mock 전용 reset command를 만들지
  않는다.
- Virtual CPX는 기본적으로 정상 상태이며 Error Register 등 상태 OD를 정상값으로 초기화한다.
- 잘못된 layout, ESI 불일치와 지원하지 않는 module은 startup Failure로 처리한다.
- runtime CPX Alarm/Fault, module 상세 Diagnostic과 fault injection은
  [RF-012](RF-012-cpx-ap-optional-diagnostic.md) 범위다.

## 검증 계획

- module/port 조합별 process image layout과 codec을 테스트한다.
- station/module OD 구성, slot-dependent index, PDO block 선택과 초기값을 테스트한다.
- DI/AI input injection, DO/AO output 반영, IO-Link raw process data와 자동 loopback 부재를
  테스트한다.
- feedback, output write, station SDO와 AP/IOL gateway request/response 경계를 end-to-end 테스트한다.
- 동일 client scenario를 virtual 및 실제 CPX profile에 적용한다.

## 완료 증거

### 지원 범위와 차이

| 항목 | Virtual CPX | 실장치 CPX |
|---|---|---|
| 설정 및 DeviceProfile | 공통 설정과 `CPXApIEcDeviceProfile` 사용 | 동일 |
| PDO encode/decode | Master의 기존 `CPXPdoCodec` 사용 | 동일 |
| PRE-OP 준비 | module ident, PDO assignment/mapping과 process-image 크기 검증 | 동일 sequence |
| Station/module OD | station ESI와 구성된 module ESI로 생성 | 장치 firmware가 제공 |
| DI/AI | 독립 module input state, 기본값 `False`/`0` | 실제 입력 |
| DO/AO | RxPDO process image를 `Model_Update`에서 반영 | 실제 출력 |
| IO-Link process data | 고정 크기 raw input/output buffer | 실제 IO-Link Device data |
| AP/ISDU parameter | gateway OD request/response dispatch 경계만 제공 | 실제 parameter 처리 |
| Diagnostic 및 reset | 정상 초기값만 제공, RF-003/RF-012 후속 | 실제 장치 동작 |
| 외부 input 조작 | 내부 injection 계약만 제공, RF-014 후속 | 실제 입력으로 조작 |

### 자동 검증

- `tests/test_virtual_cpx_ap.py`에서 fixed PDO block 선택, station/module OD, slot-dependent index,
  PRE-OP readback, DI/DO/AI/AO, IO-Link raw buffer, no-loopback, range 검증, AP/ISDU gateway와
  Axis/IO 혼합 runtime API를 검증한다.
- 2026-08-27 기준 전체 unittest 309개가 통과했다.
- IO Control Panel은 virtual 전용 분기 없이 공통 IO snapshot/input/output API를 사용하며,
  혼합 runtime 회귀 테스트에서 같은 응답 계약을 검증했다.
- 실제 CPX와의 통신 sequence 비교는 기존 CPX DeviceProfile 및 codec을 그대로 재사용하는 것으로
  확보했다. firmware timing, 실제 I/O 전기 신호와 parameter device 반응은 위 표의 제외 범위다.
