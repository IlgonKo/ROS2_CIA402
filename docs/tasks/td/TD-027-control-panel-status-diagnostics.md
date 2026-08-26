# TD-027 Control Panel의 Motion Server 상태 및 Axis 오류 표시 보완

## 배경 및 현재 구조

Axis Control Panel과 IO Control Panel은 TCP 연결과 장치 feedback을 주로 표시하지만
`system/server/status`의 초기화 여부, `runtime_state`와 공통 Diagnostic 상태를 운영자가
지속적으로 확인할 수 있는 공통 표시 영역이 없다. 특히 Bus가 끊겨 feedback이 중단되거나
initialization-error 상태가 되면 TCP 연결은 유지되더라도 Panel에서 Server 상태를 직관적으로
구분하기 어렵다.

Axis Control Panel Motion Tab의 `Error` 항목은 `device_diagnostics`의 `error_code_text`에만
의존한다. 이 값은 Panel의 지연 SDO read 결과로 갱신되므로 `AXIS_DRIVE_FAULT` 같은 활성
`diagnostic_status`가 존재해도 `Panel SDO read pending`, `No error` 또는 숫자 code만 표시될 수
있다. 따라서 사용자가 현재 축이 Fault인 이유와 복구 대상을 Motion Tab에서 확인할 수 없다.

## 목표 구조

### 공통 Motion Server 상태 표시

- Axis/IO Control Panel이 동일한 Server health projection을 사용한다.
- TCP 연결 상태와 Motion Server 운전 상태를 분리하여 표시한다.
- 최소 표시 항목은 다음과 같다.
  - TCP connected/disconnected
  - `initialized`
  - `runtime_state`: normal, initialization-error, bus-disconnected, fault
  - 공통 Diagnostic level과 활성 Fault/Alarm 수
  - 대표 Diagnostic code/title 또는 상세 보기 진입점
  - Initialization Failure stage/cause/message
- feedback이 중단되는 degraded 상태에서도 저주기 `system/server/status` 조회가 계속 동작한다.
- 최초 연결, 주기 갱신, reconnect 및 recovery command 완료가 동일한 상태 적용 경로를 사용한다.

### Axis Motion Tab 오류 표시

- 선택 Axis의 `diagnostic_status.statuses`를 `source.type=axis`와 Axis index로 필터링한다.
- 활성 Fault/Alarm의 level, code, title과 제공되는 detail을 Motion Tab `Error` 항목에 표시한다.
- Device error code readback은 Diagnostic을 대체하지 않고 보조 상세로 결합한다.
- 여러 Diagnostic이 활성화되면 우선순위와 표시 순서를 `FAULT > ALARM`, 발생 순서 기준으로
  결정하고 생략 개수를 알 수 있게 한다.
- 활성 Axis Diagnostic이 없고 Drive error code도 0이면 `No error`를 표시한다.
- fault-reset, 조건 resolve, reconnect와 축 선택 변경 직후 이전 축 또는 해제된 오류가 남지 않는다.

## 데이터 및 책임 경계

- Server와 Axis 오류의 기준 source는 Motion Server가 제공하는 typed status/Diagnostic 응답이다.
- Panel은 Diagnostic code의 의미를 별도 hard-coding하지 않고 Definition의 title/description을
  표시 형식으로 변환한다.
- 주기 상태 조회와 응답 저장은 client 계층, 공통 health projection은 공유 가능한 utility/model,
  widget 갱신은 각 Panel view 계층이 담당한다.
- Panel의 socket 오류와 API Fail 메시지는 Server Diagnostic과 혼합하지 않는다.

## 관련 위치

- `control_panel/axis_control_panel/client.py`
- `control_panel/axis_control_panel/control_panel.py`
- `control_panel/axis_control_panel/ui_builders/panel_layout.py`
- `control_panel/axis_control_panel/ui_builders/single_axis_view.py`
- `control_panel/io_control_panel/client.py`
- `control_panel/io_control_panel/control_panel.py`
- `motion_server/handlers/status/server_status.py`
- `motion_server/handlers/status/axis_status.py`

## 범위 제외

- 새로운 Motion Server Diagnostic level 또는 lifecycle 정의
- 장치 제조사 오류 code catalog의 전체 번역
- CPX-AP module 단위 선택형 상세 Diagnostic 구현
- Control Panel 전체 UI framework 교체

## 검증 계획

- normal, initialization-error, bus-disconnected와 fault 상태 payload를 두 Panel에 적용한다.
- TCP 연결은 유지되지만 feedback이 중단된 상태에서도 Server 상태가 갱신되는지 검증한다.
- 선택 Axis Fault/Alarm, 여러 Diagnostic, Drive error code와 정상 상태의 Motion Tab 표시를 검증한다.
- Axis 선택 변경, fault-reset, reconnect와 Diagnostic clear 후 stale 표시가 제거되는지 검증한다.
- 공통 projection의 Axis/IO Panel parity와 client reconnect 회귀 테스트를 수행한다.

## 완료 증거

완료 시 두 Panel의 상태별 표시 결과, Axis Motion Tab 오류 예시와 자동 테스트 결과를 기록한다.
