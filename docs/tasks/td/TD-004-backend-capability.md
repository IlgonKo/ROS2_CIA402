# TD-004 Backend Capability Fallback과 오래된 Servo Interface

## 배경 및 현재 구조

- `ServoInterface`와 `Axis`가 virtual servo 중심의 오래된 계약을 유지한다.
- 선택 기능을 `hasattr()`로 확인해 호출하는 경로가 있다.
- startup이 backend method 존재 여부로 staged startup과 restart 지원을 판단한다.

## 문제와 위험

지원 기능이 암묵적이어서 backend 구현 누락이 startup 이후에 발견될 수 있고,
device profile과 transport capability의 책임이 섞인다.

## 관련 위치

- `interfaces/servo_interface.py`
- `motion_server/control/axis.py`
- `motion_server/app/startup.py`
- `motion_server/server.py`

## 목표 구조 및 구현 범위

- backend와 device profile capability를 명시적인 interface 또는 immutable capability object로 표현한다.
- 필수 method와 선택 기능을 startup validation에서 구분한다.
- 암묵적인 `hasattr()` fallback을 제거한다.

### Axis Restart Capability 및 명칭 계약

- 전체 선택 기능은 `DeviceCapability.AXIS_RESTART`로 표현한다.
- 상위 profile 동작은 다음 이름으로 통일한다.
  - `request_axis_restart(...)`: restart request를 확실한 `0 -> 1` 전이로 발생시킨다.
  - `clear_axis_restart_request(...)`: startup 또는 복구 전에 남아 있을 수 있는 request를 `0`으로 초기화한다.
- 실제 OD command write primitive가 필요하면 `write_axis_restart_command(master, axis_index, value)`를 사용한다.
- `command`라는 단어는 저수준 OD write에만 사용하고, 상위 동작에는 `request`를 사용한다.
- 기존 `restart_axis(...)`와 `clear_axis_restart_command(...)` 명칭은 위 계약으로 변경한다.
- `AXIS_RESTART` capability를 선언한 profile은 request와 clear-request 동작을 모두 제공해야 하며,
  누락 시 startup validation에서 실패한다.

의도한 계층은 다음과 같다.

```text
DeviceCapability.AXIS_RESTART
  -> request_axis_restart()
       -> write_axis_restart_command(..., 0)
       -> write_axis_restart_command(..., 1)
  -> clear_axis_restart_request()
       -> write_axis_restart_command(..., 0)
```

## 검증 계획

- mock/PySOEM backend의 capability 선언과 필수 method 일치 여부를 테스트한다.
- capability 누락과 지원하지 않는 기능 요청의 오류를 테스트한다.
- axis restart request가 `0 -> 1`, startup clear가 `0`을 기록하는지 테스트한다.
- capability 선언과 request/clear-request method가 불일치하면 startup 전에 실패하는지 테스트한다.

## 완료 증거

완료 시 interface 정의, migration 결과와 자동 테스트 링크를 기록한다.
