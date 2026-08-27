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

- logical I/O id, AP module slot과 channel을 사용하여 대상을 지정한다.
- Digital Input 값을 설정한다.
- Analog Input 값을 설정한다.
- IO-Link Input Process Data payload를 설정한다.
- 설정한 값은 다음 Model_Update cycle부터 `0x7F00` process image와 기존 I/O feedback에 반영한다.
- 현재 virtual input 상태를 조회하고 기본값으로 초기화한다.
- IO-Link는 module 전체 Input Process Data raw payload를 설정한다. port별 payload API는 후속
  확장으로 둔다.
- Control Panel의 virtual input 조작 화면과 외부 simulator가 사용할 API 계약을 제공한다.

## 확정 API 계약

- `system/simulation/io/input_write`
  - `io`, `slot`, `kind` 필수
  - `digital`: `channel`, JSON boolean `value`
  - `analog`: `channel`, PDO raw integer `value`
  - `io_link`: module 전체 크기의 hexadecimal/list `payload`
- `system/simulation/io/input_read`
  - `io` 생략 시 사용 가능한 모든 Virtual CPX station을 반환한다.
  - `io` 지정 시 해당 station의 현재 internal input state를 반환한다.
- `system/simulation/io/input_reset`
  - `io` 필수, `slot` 선택
  - slot 지정 시 module 하나, 생략 시 station 전체 입력을 기본값으로 초기화한다.
- 쓰기와 reset은 command authority를 요구하지 않는다. 여러 client 요청은 server 처리 순서의
  last-write-wins로 직렬화된다.

## 안전 및 노출 정책

- virtual/mock backend에서만 사용할 수 있으며 실제 EtherCAT 장치에는 전달하지 않는다.
- `MOTION_SERVER_SIMULATION_API_ENABLED=1`로 명시적으로 활성화한 경우에만 노출한다.
- 일반 I/O output command authority와 독립적으로 동작하며 별도 simulation authority는 두지 않는다.
- 잘못된 I/O id, module, channel, port, datatype과 payload 길이는 공통 Failure 계약으로 반환한다.
- Virtual Device 전용 기능임을 응답과 사용자 화면에서 명확히 표시한다.
- 입력값은 cycle 사이와 client disconnect 후에도 유지한다. bus reconnect/server restart로 Virtual
  Device가 재생성되면 기본값으로 초기화한다.

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

- 세 API를 공통 API specification과 command/status registry에 등록했다. write/reset은
  `authority_required=False`이고 활성화 flag와 MockMaster를 모두 검증한다.
- Virtual CPX input snapshot/reset과 MockMaster의 virtual-device 접근을 연결했으며 MockSlave와
  VirtualOdBridge에는 simulation 의미를 추가하지 않았다.
- IO Control Panel은 연결 시 capability probe를 실행하고 사용 가능할 때만 DI checkbox, AI integer,
  IO-Link hexadecimal raw payload 및 module/station reset 화면을 표시한다.
- API 예제는 `docs/motion_server_api_basic.md`, 수동 검증 절차는 `docs/test_procedure.md`에 기록했다.
- DI의 next-cycle 기존 feedback 반영, AI/IO-Link payload, module reset, 다중 station 격리,
  비활성/real backend/잘못된 target 거부, authority 독립, reconnect reset 및 Control Panel 상태 보존을
  자동 테스트했다.
- 2026-08-27 기준 전체 unittest 319개, source compile과 diff whitespace 검사를 통과했다.
