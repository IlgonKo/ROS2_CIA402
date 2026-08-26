# TD-024 Axis Control Panel 초기 임시 연결 제거

## 배경 및 현재 구조

Axis Control Panel은 UI를 만들기 전에 축 수를 확인하기 위해
`request_initial_system_status()`에서 Motion Server에 일회성 TCP 연결을 생성한다.
status 응답을 받은 뒤 이 연결을 닫고, `AxisServerClient`가 실제 상시 연결을 다시 생성하여
동일한 `system/axes/status`를 요청한다.

## 문제와 위험

- Control Panel 한 번의 시작에 TCP 연결과 초기 status 요청이 각각 두 번 발생한다.
- 임시 client가 status 응답만 읽고 주기 feedback이 남은 상태에서 socket을 닫으면 Windows
  서버에는 `WinError 10054` connection reset으로 기록될 수 있다.
- 연결이 종료되면 서버가 가장 작은 client ID를 재사용하므로 두 연결이 모두 `client=1`로
  표시되어 실제 재접속 장애로 오인하기 쉽다.
- 축 수를 UI 생성 전에 반드시 알아야 하는 현재 구조가 연결 lifecycle과 UI lifecycle을
  불필요하게 결합한다.
- 시작 시 status 조회가 실패하면 `axis_count = 1` fallback으로 Panel 전체 UI와 Client buffer가
  즉시 생성된다. 이후 화면에서 다른 endpoint에 연결하여 다축 status를 받아도 축 수와 UI를
  재구성하는 경로가 없어 1축 Panel로 고정된다.

## 확인된 재현 사례

- 2026-08-26: Linux Motion Server는 `system/axes/status`에서 `axis_metadata`와
  `statuswords`를 각각 4개 반환했고 Windows의 독립 초기 status 요청도 4축으로 판별했다.
- Windows Panel을 기본 endpoint로 먼저 실행한 뒤 화면에서 Linux endpoint에 연결하면 시작 시
  실패 fallback으로 만든 1축 UI가 유지됐다.
- 따라서 서버 축 구성이나 status schema 문제가 아니라 endpoint 연결 성공 전 축 수를 확정하고
  재접속 status에서 UI를 재구성하지 않는 Panel lifecycle 문제로 확인됐다.

## 목표 구조

- `AxisServerClient`의 상시 연결만 생성한다.
- 상시 연결에서 수신한 첫 `system/feedback`의 축 배열 길이로 축 수를 확정한다.
- 첫 feedback 전에는 연결 및 Server health만 표시하는 bootstrap 화면을 유지한다.
- 축 수 확정 후 로컬 설정 또는 기본 이름으로 Panel 기본 화면과 Axis UI를 한 번만 생성한다.
- UI 생성 후 `system/axes/status`를 요청하여 단위, 설정값과 metadata를 보완한다.
- UI 생성 뒤 feedback의 축 수가 달라지면 동적으로 재구성하지 않고 Panel 재시작 필요 상태로
  전환하여 제어를 제한한다.
- 연결 실패 상태에서는 임의의 1축 구성을 정상 구성처럼 확정하지 않는다.
- 서버는 정상 EOF와 명시적인 client 종료를 오류가 아닌 disconnect lifecycle로 처리한다.

## Feedback 유효성 계약

- `process_data_valid=true`: 이번 feedback의 process data가 정상 EtherCAT cycle에서 갱신됐다.
- `process_data_valid=false`: Bus 단절 또는 초기화 실패로 process data를 현재값으로 신뢰할 수 없다.
- Bus 단절 시 마지막 배열을 유지하여 이미 구성된 UI topology를 보존하되 Panel은 값을 stale로
  표시하고 제어 판단에 사용하지 않는다.
- 초기화 실패로 runtime이 생성되지 않았으면 빈 process data 배열과 Server health를 전송하며
  Axis UI는 생성하지 않는다.
- 정상, Bus 단절, 초기화 실패 상태 모두 기존 feedback 주기로 `system/feedback`을 전송한다.

## 구현 단계

- S01: 공통 Server health projection 및 feedback 유효성 계약을 구현한다.
- S02: 정상·Bus 단절·초기화 실패 loop에서 동일한 feedback 전송 경계를 적용한다.
- S03: Axis client의 임시 연결과 시작 status 요청을 제거하고 feedback topology를 latch한다.
- S04: bootstrap 화면에서 축 수 확정 후 Axis UI를 한 번만 생성하고 full status를 요청한다.
- S05: 축 수 불일치 감지, stale 표시와 제어 제한을 구현한다.
- S06: 연결 lifecycle과 bootstrap 회귀 테스트를 추가한다.

## 관련 위치

- `control_panel/axis_control_panel/config.py`
- `control_panel/axis_control_panel/client.py`
- `control_panel/axis_control_panel/control_panel.py`
- `motion_server/app/client_transport.py`
- `motion_server/server.py`

## 범위 제외

- Motion Server의 일반적인 client ID 발급 정책 변경
- UI 생성 후 실시간 축 topology 변경
- IO Control Panel 전체 연결 구조 통합

## 검증 계획

- Control Panel 시작 시 accept와 `system/axes/status` 요청이 각각 한 번만 발생하는지 검증한다.
- 첫 feedback이 지연되거나 연결이 실패한 경우 bootstrap 화면이 연결 및 Server health를 표시하는지
  검증한다.
- 1축/다축 feedback으로 UI가 한 번만 구성되고 이후 status가 metadata를 보완하는지 검증한다.
- Bus 단절 feedback이 마지막 배열과 `process_data_valid=false`를 제공하는지 검증한다.
- 축 수가 변경된 feedback에서 UI 재구성 대신 재시작 필요 상태가 되는지 검증한다.
- 정상 종료 시 서버에 connection reset 오류가 남지 않는지 Windows socket 통합 테스트로 확인한다.

## 완료 증거

- 축 수 확인용 `request_initial_system_status()`와 임시 socket을 제거했다.
- 상시 client의 첫 feedback이 1축/다축 topology를 latch하고 full status를 한 번 요청한다.
- 초기화 실패 feedback은 빈 배열과 health만 제공하며 1축 fallback UI를 만들지 않는다.
- topology 변경은 UI 재구성 없이 재시작 필요 상태와 `process_data_valid=false`로 처리한다.
- 2026-08-26 전체 unittest 284개와 diff whitespace 검사가 통과했다.
