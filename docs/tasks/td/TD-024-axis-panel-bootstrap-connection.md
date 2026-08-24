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

## 목표 구조

- `AxisServerClient`의 상시 연결만 생성한다.
- 상시 연결 직후 보내는 첫 `system/axes/status` 응답을 bootstrap status로 사용한다.
- 축 수와 축 metadata가 확인된 후 UI를 생성하거나, UI가 먼저 필요한 경우 동적으로 축 view를
  구성할 수 있는 명시적인 초기화 경계를 둔다.
- 재접속 후 축 구성이 변경되었으면 동일한 status 적용 경로로 UI 상태를 안전하게 재구성한다.
- 서버는 정상 EOF와 명시적인 client 종료를 오류가 아닌 disconnect lifecycle로 처리한다.

## 관련 위치

- `control_panel/axis_control_panel/config.py`
- `control_panel/axis_control_panel/client.py`
- `control_panel/axis_control_panel/control_panel.py`
- `motion_server/app/client_transport.py`
- `motion_server/server.py`

## 범위 제외

- Motion Server의 일반적인 client ID 발급 정책 변경
- TCP protocol 또는 status response schema 변경
- IO Control Panel 전체 연결 구조 통합

## 검증 계획

- Control Panel 시작 시 accept와 `system/axes/status` 요청이 각각 한 번만 발생하는지 검증한다.
- 첫 status가 지연되거나 연결이 실패한 경우 UI가 멈추지 않고 연결 상태를 표시하는지 검증한다.
- 첫 연결과 재접속에서 1축/다축 metadata가 동일한 경로로 반영되는지 검증한다.
- 정상 종료 시 서버에 connection reset 오류가 남지 않는지 Windows socket 통합 테스트로 확인한다.

## 완료 증거

완료 시 연결 lifecycle 테스트, 초기화·재접속 시나리오 결과와 대표 서버 로그를 기록한다.
