# RF-014 Virtual Device Simulation API

## 사용자 가치

Control Panel이나 외부 simulator에서 Virtual CPX의 입력 상태를 변경하여 실제 센서와 IO-Link
Device가 없어도 Motion Server의 I/O 제어, feedback과 상위 application 동작을 시험한다.

## 책임 경계

- 일반 운전 API는 실장치와 가상장치에서 동일한 `system/io/status`와
  `system/io/input_read`를 계속 사용한다.
- Simulation API는 실제 장치 명령이 아니라 virtual environment의 외부 입력을 만드는 별도
  개발·시험용 경계다.
- API handler는 RF-001에서 확정한 `VirtualCpxApDevice`의 input injection 계약을 호출한다.
- `MockSlave`는 EtherCAT transport 순서만 담당하고 simulation command를 해석하지 않는다.
- `VirtualOdBridge`는 PDO/SDO와 OD Model 연결만 담당하고 simulation API에 의존하지 않는다.

## 초기 구현 범위

- logical I/O id, AP module slot과 channel/port를 사용하여 대상을 지정한다.
- Digital Input 값을 설정한다.
- Analog Input 값을 설정한다.
- IO-Link Input Process Data payload를 설정한다.
- 설정한 값은 다음 Model_Update cycle부터 `0x7F00` process image와 기존 I/O feedback에 반영한다.
- 현재 virtual input 상태를 조회하고 기본값으로 초기화한다.
- Control Panel의 virtual input 조작 화면과 외부 simulator가 사용할 API 계약을 제공한다.

## 안전 및 노출 정책

- virtual/mock backend에서만 사용할 수 있으며 실제 EtherCAT 장치에는 전달하지 않는다.
- simulation 기능은 명시적으로 활성화한 경우에만 노출한다.
- 일반 I/O output authority와 simulation input authority의 관계 및 동시 접근 정책은 구현 전에
  확정한다.
- 잘못된 I/O id, module, channel, port, datatype과 payload 길이는 공통 Failure 계약으로 반환한다.
- Virtual Device 전용 기능임을 응답과 사용자 화면에서 명확히 표시한다.

## 제외 범위

- DO와 DI 또는 AO와 AI를 자동 loopback하지 않는다.
- 실장치 입력값을 API로 강제 변경하지 않는다.
- AP parameter 및 IO-Link ISDU runtime parameter 공간은
  [RF-013](RF-013-virtual-ap-iol-parameter-devices.md)에서 구현한다.
- 복잡한 plant model, 물리 simulation과 시간 기반 scenario engine은 초기 범위에 포함하지 않는다.

## 선행 기능

- [RF-001](RF-001-cpx-virtual-io.md)의 Virtual CPX module state와 input injection 내부 계약이
  선행되어야 한다.

## 검증 계획

- DI/AI/IO-Link input을 주입하고 다음 cycle의 기존 status/input feedback에서 같은 값을 확인한다.
- 여러 I/O station, module, channel과 port 사이의 상태 격리를 검증한다.
- real backend, 비활성화 상태와 잘못된 target에 대한 거부 경로를 검증한다.
- Control Panel과 외부 reference client에서 같은 simulation API 시나리오를 실행한다.

## 완료 증거

완료 시 API specification, 활성화·authority 정책, Control Panel 동작, reference client 예제와 자동
테스트 결과를 기록한다.
