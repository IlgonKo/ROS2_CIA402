# Motion Server Basic Mode API Manual

이 문서는 Basic mode 기준 Motion Server TCP API 사용 방법을 설명한다. 요청은 JSON object 한 줄로 전송하며, 각 메시지는 newline으로 끝난다.

```text
TCP connect -> send JSON + "\n" -> receive JSON lines
```

요청 메시지는 `cmd` 필드를 사용한다. 응답 메시지는 `type` 필드로 메시지 종류를 구분한다.

## Connection

기본 포트는 `.env`의 `AXIS_SERVER_PORT`로 설정한다. 일반 기본값은 `15000`이다.

```python
import json
import socket

sock = socket.create_connection(("127.0.0.1", 15000))
sock.sendall((json.dumps({"cmd": "system/status"}) + "\n").encode("utf-8"))
print(sock.recv(8192).decode("utf-8"))
```

서버는 연결된 client마다 주기적으로 `system/feedback`을 송신한다. 클라이언트는 요청 응답과 주기 feedback이 같은 TCP stream에 섞여 들어온다는 점을 고려해야 한다.

## Axis Selection

축을 지정하는 명령은 다음 형식을 사용한다.

```json
{"cmd": "axis/enable", "axis": 0}
```

여러 축을 지정할 때는 `axes`를 사용한다.

```json
{"cmd": "axis/enable", "axes": [0, 1, 2]}
```

`axis`와 `axes`가 모두 없으면 대부분의 axis 명령은 전체 축을 대상으로 처리한다. 단, `axis/status`, `axis/jog_start`, `axis/jog_stop`, `axis/param_read`, `axis/param_save`처럼 단일 축만 허용하는 명령은 축을 하나만 지정해야 한다.

## Units

Motion Server API 단위는 다음과 같다.

```text
linear position          mm
rotary position          deg
linear velocity          mm/s
rotary velocity          deg/s
linear acceleration      mm/s^2
rotary acceleration      deg/s^2
linear jerk              mm/s^3
rotary jerk              deg/s^3
```

드라이브 내부 단위 변환은 서버가 처리한다.

예:

```json
{"cmd": "axis/move_abs", "axis": 0, "position": 50.0}
```

0번 축이 linear axis이면 50 mm 위치로 이동한다. rotary axis이면 50 deg 위치로 이동한다.

## Command Authority

쓰기 명령은 command authority가 필요하다. 읽기/status 명령은 authority 없이 가능하다.

### Acquire

```json
{"cmd": "authority/acquire"}
```

성공 응답:

```json
{
  "type": "authority/acquire",
  "ok": true,
  "granted": true,
  "owner": 2,
  "owned_by_this_client": true,
  "available": false,
  "reason": null,
  "message": "Command authority granted."
}
```

필드 의미:

```text
owner                 현재 authority owner client id
owned_by_this_client  이 응답을 받은 client가 owner인지 여부
available             owner가 없는 free 상태인지 여부
```

`available=false`는 반드시 제어 불가를 뜻하지 않는다. `owned_by_this_client=true`이면 현재 client가 제어권을 가진 상태이다.

### Release

```json
{"cmd": "authority/release"}
```

### Status

```json
{"cmd": "authority/status"}
```

다른 client가 이미 authority를 가진 상태에서 acquire하면 `reason=authority_busy`로 거부된다.

## Status and Feedback

### system/status

전체 시스템 full snapshot을 요청한다.

```json
{"cmd": "system/status"}
```

주요 응답 필드:

```json
{
  "type": "system/status",
  "drive_initialized": true,
  "target_positions": [0.0],
  "actual_positions": [0.0],
  "actual_velocities": [0.0],
  "statuswords": [33831],
  "motion_modes": ["pp"],
  "motion_limits": [100.0, -100.0, 1000.0, 1000.0],
  "profile_settings": [100.0, 1000.0, 1000.0, 0.0],
  "software_position_limits": [-1000.0, 1000.0],
  "axis_metadata": [],
  "diagnostics": [],
  "command_authority": {}
}
```

`motion_limits`, `profile_settings`, `software_position_limits`는 축별 값이 flat array로 전달된다.

```text
motion_limits per axis:
  [positive_velocity_limit, negative_velocity_limit, max_acceleration, max_deceleration]

profile_settings per axis:
  [profile_velocity, profile_acceleration, profile_deceleration, profile_jerk]

software_position_limits per axis:
  [negative_limit, positive_limit]
```

### system/feedback

서버가 주기적으로 송신하는 전체 시스템 cyclic feedback이다.

```json
{
  "type": "system/feedback",
  "target_positions": [0.0],
  "actual_positions": [0.0],
  "actual_velocities": [0.0],
  "statuswords": [33831],
  "mode_displays": [1],
  "command_authority": {}
}
```

주기 feedback은 빠른 표시용이다. limits, unit metadata, diagnostics 같은 설정성 정보가 필요하면 `system/status` 또는 `axis/status`를 요청한다.

### axis/status

특정 축의 full snapshot을 요청한다.

```json
{"cmd": "axis/status", "axis": 0}
```

응답은 system/status에서 해당 축에 해당하는 값을 scalar 형태로 제공한다.

```json
{
  "type": "axis/status",
  "axis": 0,
  "target_position": 0.0,
  "actual_position": 0.0,
  "actual_velocity": 0.0,
  "statusword": 33831,
  "mode_display": 1,
  "motion_mode": "pp",
  "motion_limits": [100.0, -100.0, 1000.0, 1000.0],
  "profile_settings": [100.0, 1000.0, 1000.0, 0.0],
  "software_position_limits": [-1000.0, 1000.0],
  "axis_metadata": {},
  "diagnostics": {},
  "command_authority": {}
}
```

## System Commands

### system/stop

전체 축을 controlled stop한다.

```json
{"cmd": "system/stop"}
```

지원 mode:

```json
{"cmd": "system/stop", "mode": "controlled"}
```

Basic mode에서는 `controlled`만 사용한다.

### system/reset

전체 축 fault reset sequence를 수행한다.

```json
{"cmd": "system/reset"}
```

## Axis Power and State Commands

### axis/enable

지정 축을 Operation Enabled controlword로 만든다.

```json
{"cmd": "axis/enable", "axis": 0}
```

### axis/disable

지정 축을 disable한다. 현재 위치 hold도 함께 수행한다.

```json
{"cmd": "axis/disable", "axis": 0}
```

### axis/reset

지정 축 fault reset sequence를 수행한다.

```json
{"cmd": "axis/reset", "axis": 0}
```

### axis/home

지정 축 homing을 시작한다.

```json
{"cmd": "axis/home", "axis": 0}
```

Homing 중 서버는 해당 축을 homing mode로 전환한다. 완료 후 원래 motion mode로 복귀한다.

### axis/stop

지정 축을 controlled stop한다.

```json
{"cmd": "axis/stop", "axis": 0}
```

PP/CSP 계열은 halt bit 기반 정지, PV 계열은 velocity 0 command 기반 정지를 사용한다.

## Motion Mode

### axis/mode

축 motion mode를 변경한다.

```json
{"cmd": "axis/mode", "axis": 0, "mode": "pp"}
```

Basic mode에서 일반적으로 사용하는 mode:

```text
pp    Profile Position
pv    Profile Velocity
```

`csp`는 Advanced mode에서만 노출하는 것을 권장한다. PV mode는 드라이브의 user position unit이 rotary 계열일 때만 허용된다.

## Position and Velocity Commands

### axis/move_abs

절대 위치 이동 명령이다.

```json
{"cmd": "axis/move_abs", "axis": 0, "position": 50.0}
```

여러 축:

```json
{"cmd": "axis/move_abs", "axes": [0, 1], "positions": [50.0, 20.0]}
```

선택 필드:

```json
{
  "cmd": "axis/move_abs",
  "axis": 0,
  "position": 50.0,
  "profile_velocity": 100.0
}
```

절대 위치 이동은 referenced 상태가 필요하다. referenced bit가 없으면 서버가 명령을 거부한다.

### axis/move_rel

현재 위치 기준 상대 이동 명령이다.

```json
{"cmd": "axis/move_rel", "axis": 0, "distance": 10.0}
```

여러 축:

```json
{"cmd": "axis/move_rel", "axes": [0, 1], "distances": [10.0, -5.0]}
```

### axis/move_vel

PV mode에서 속도 명령을 보낸다.

```json
{"cmd": "axis/move_vel", "axis": 0, "velocity": 30.0}
```

여러 축:

```json
{"cmd": "axis/move_vel", "axes": [0, 1], "velocities": [30.0, -20.0]}
```

## Jog

### axis/jog_start

단일 축 jog를 시작한다.

```json
{"cmd": "axis/jog_start", "axis": 0, "direction": "positive", "speed": "slow"}
```

필드:

```text
direction: positive, negative, +, -
speed: slow, fast, two_phase
```

### axis/jog_stop

Jog를 멈추고 이전 motion mode로 복귀한다.

```json
{"cmd": "axis/jog_stop", "axis": 0}
```

## Profile and Limit Settings

### axis/profile

축 profile 설정을 변경한다.

```json
{
  "cmd": "axis/profile",
  "axis": 0,
  "profile_velocity": 100.0,
  "profile_acceleration": 1000.0,
  "profile_deceleration": 1000.0,
  "profile_jerk": 0.0
}
```

짧은 alias도 지원한다.

```json
{
  "cmd": "axis/profile",
  "axis": 0,
  "velocity": 100.0,
  "acceleration": 1000.0,
  "deceleration": 1000.0,
  "jerk": 0.0
}
```

PV mode에서는 profile velocity와 jerk는 의미가 제한적이며 acceleration/deceleration 중심으로 사용한다.

### axis/motion_limits

축 motion limit을 변경한다.

```json
{
  "cmd": "axis/motion_limits",
  "axis": 0,
  "positive_velocity_limit": 100.0,
  "negative_velocity_limit": -100.0,
  "max_acceleration": 1000.0,
  "max_deceleration": 1000.0
}
```

### axis/software_position_limits

축 software position limit을 변경한다.

```json
{
  "cmd": "axis/software_position_limits",
  "axis": 0,
  "negative_limit": -100.0,
  "positive_limit": 100.0
}
```

## Parameters

### axis/param_read

축 기준 SDO parameter를 읽는다. 읽기 명령은 authority 없이 사용할 수 있다.

```json
{
  "cmd": "axis/param_read",
  "axis": 0,
  "index": "0x6041",
  "subindex": "0x00",
  "data_type": "uint16"
}
```

지원 data type:

```text
uint8
int8
uint16
int32
uint32
udint
float32
```

응답:

```json
{
  "type": "axis/param_read",
  "ok": true,
  "axis": 0,
  "index": 24641,
  "subindex": 0,
  "data_type": "uint16",
  "value": 33831,
  "hex": "0x00008427"
}
```

### axis/param_write

축 기준 SDO parameter를 쓴다. Authority가 필요하다.

```json
{
  "cmd": "axis/param_write",
  "axis": 0,
  "index": "0x6081",
  "subindex": "0x00",
  "data_type": "uint32",
  "value": 1000
}
```

### axis/param_save

장치 parameter save 동작을 수행한다.

```json
{"cmd": "axis/param_save", "axis": 0}
```

## Rejection Response

명령이 거부되면 일반적으로 다음 형식의 응답을 받는다.

```json
{
  "type": "command_rejected",
  "ok": false,
  "reason": "authority_required",
  "command": "axis/move_abs",
  "owner": null,
  "available": true,
  "owned_by_this_client": false,
  "message": "Command authority is required."
}
```

자주 보는 reason:

```text
authority_required   아무 client도 authority를 갖고 있지 않음
authority_busy       다른 client가 authority를 갖고 있음
```

일부 validation error는 `reason` 없이 `message`만 포함할 수 있다.

## Recommended Basic Flow

가장 단순한 위치 이동 flow:

```text
1. TCP connect
2. system/status 확인
3. authority/acquire
4. axis/reset 필요 시 수행
5. axis/enable
6. axis/home
7. axis/mode -> pp
8. axis/profile 또는 axis/motion_limits 설정
9. axis/move_abs
10. system/feedback 또는 axis/status로 상태 확인
11. authority/release
```

예시:

```json
{"cmd": "system/status"}
{"cmd": "authority/acquire"}
{"cmd": "axis/enable", "axis": 0}
{"cmd": "axis/home", "axis": 0}
{"cmd": "axis/mode", "axis": 0, "mode": "pp"}
{"cmd": "axis/profile", "axis": 0, "profile_velocity": 100.0, "profile_acceleration": 1000.0, "profile_deceleration": 1000.0}
{"cmd": "axis/move_abs", "axis": 0, "position": 50.0}
{"cmd": "authority/release"}
```

