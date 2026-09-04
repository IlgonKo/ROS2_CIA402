# RF-018 Gamepad Manual Multi-Axis Velocity Control

- 등록일: 2026-09-04
- 상태: `planned`
- 우선순위: 보통
- 선행 작업: TD-034
- 구현 위치: `reference_clients/gamepad`

## 배경

DualSense 같은 gamepad를 사용하여 Motion Server 축을 수동으로 조작한다. 주 목적은
3축 + rotation을 사람이 스틱으로 동시에 움직이는 manual velocity pendant를 제공하는 것이다.
단축 수동 조작도 보조 모드로 함께 제공한다.

Gamepad 입력은 Motion Server core 기능이 아니라 외부 reference client로 구현한다. Motion Server와는
기존 TCP API만 사용하며, command authority, runtime/fault 상태, motion limit와 software limit는
기존 서버 계약을 그대로 따른다.

## 핵심 구조

```text
DualSense / Gamepad
→ reference_clients/gamepad
→ Motion Server TCP API
→ system/axes/move_vel
→ Axis velocity control
```

Motion Server core에는 OS별 HID/gamepad dependency를 추가하지 않는다.

## 운전 모드

### Multi-axis mode

기본 모드다. X/Y/Z/Rotation role을 동시에 velocity 제어한다.

```text
Left Stick X/Y  → X/Y velocity
Right Stick Y/X → Z/Rotation velocity
```

Motion Server에는 기존 `system/axes/move_vel`로 한 번에 전달한다.

### Single-axis mode

선택된 축 하나만 velocity 제어한다. 장비 setup, 단일 축 확인, 축별 방향 검증에 사용한다.

```text
D-pad left/right → selected axis 변경
Left Stick Y 또는 Right Stick Y → selected axis velocity
```

Single-axis mode에서도 L1 deadman, speed scale, deadzone, timeout, stop 정책은 Multi-axis mode와
동일하게 적용한다. Motion Server에는 기존 `system/axis/move_vel` 또는 selected axis만 포함한
`system/axes/move_vel`을 사용한다.

mode 전환 입력은 구현 전에 최종 확정한다. 후보는 `Touchpad click`, `L3/R3 click`, 또는
설정 파일의 startup mode다.

## 1차 입력 매핑

### 공통

```yaml
L1 hold          : Deadman / Armed

D-pad up/down    : speed scale 변경
Cross            : mapped axes enable
Circle           : mapped axes disable
Square           : mapped axes fault_reset
Triangle         : mapped axes stop
Options          : authority request/release
Create           : all axes stop
```

### Multi-axis mode

```yaml
Left stick X     : X velocity
Left stick Y     : Y velocity
Right stick Y    : Z velocity
Right stick X    : Rotation velocity
```

### Single-axis mode

```yaml
D-pad left/right : selected axis 변경
Left stick Y     : selected axis velocity
Right stick Y    : selected axis velocity alternative
```

축 번호는 하드코딩하지 않고 client 설정으로 매핑한다.

```yaml
axes:
  x: 0
  y: 1
  z: 2
  rotation: 3
```

Single-axis mode의 선택 가능 축 범위도 설정 또는 서버 feedback의 axis count로 제한한다.

## Velocity 계산

stick 입력은 role별 axis velocity로 변환한다.

```text
velocity[role] = stick_value * max_velocity[role] * speed_scale
```

권장 설정 항목:

```yaml
deadzone: 0.08
update_period_ms: 50
speed_scale_default: 0.1
speed_scales: [0.05, 0.1, 0.25, 0.5, 1.0]
max_velocity:
  x: 50.0
  y: 50.0
  z: 20.0
  rotation: 30.0
```

linear axis velocity는 mm/s, rotary axis velocity는 deg/s 기준으로 Motion Server API에 전달한다.

## Safety 계약

- L1 deadman이 눌린 상태에서만 velocity command를 보낸다.
- deadman release 시 mapped axes stop을 즉시 요청한다.
- input timeout, gamepad disconnect, server disconnect 시 mapped axes stop을 우선 수행한다.
- 재연결 후 command authority는 자동 요청하지 않고 사용자가 명시적으로 다시 요청한다.
- velocity command는 기존 Motion Server의 command authority, enabled state, fault state,
  motion limit, software limit와 timeout safety를 우회하지 않는다.

## Motion Server API 사용

1차 구현은 신규 gamepad 전용 API를 만들지 않고 기존 `system/axes/move_vel`을 사용한다.

예:

```json
{
  "cmd": "system/axes/move_vel",
  "axes": [0, 1, 2, 3],
  "velocities": [10.0, 0.0, -2.0, 5.0]
}
```

Linear/rotary axis 모두에서 `move_vel`을 사용할 수 있도록 하는 서버 측 계약 정리는
[TD-034](../td/TD-034-linear-rotary-velocity-command.md)가 담당한다.

## 제외 범위

- absolute move
- relative move
- homing
- sequence start
- parameter write
- safety bypass
- force/torque control
- trajectory generation
- Motion Server core의 gamepad/HID dependency
- 신규 Motion Server gamepad 전용 API

## 완료 조건

- `reference_clients/gamepad`에 gamepad manual velocity client가 구현된다.
- DualSense 기준 L1 deadman과 stick/button mapping이 동작한다.
- axis role-to-index, single-axis 선택 범위, deadzone, update period, speed scale과 max velocity가 설정 가능하다.
- mapped axes에 대해 `system/axes/move_vel`, enable/disable/fault_reset/stop/authority request/release를 호출한다.
- Single-axis mode에서 선택 축 변경과 선택 축 velocity command가 동작한다.
- deadman release, input timeout, gamepad disconnect와 server disconnect에서 stop 우선 정책이 검증된다.
- Linear/rotary velocity command 계약은 TD-034 완료 상태를 전제로 한다.
