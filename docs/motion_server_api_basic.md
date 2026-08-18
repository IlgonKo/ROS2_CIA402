# Motion Server Basic Mode API Manual

이 문서는 Basic mode 기준 Motion Server TCP JSON API를 설명한다. 요청은 JSON object 한 줄로 전송하며, 각 메시지는 newline으로 끝난다.

```text
TCP connect -> send JSON + "\n" -> receive JSON lines
```

요청 메시지는 `cmd` 필드를 사용한다. 응답과 이벤트 메시지는 `type` 필드로 메시지 종류를 구분한다.

## Namespace Structure

Motion Server API는 `system`을 최상위 namespace로 사용한다.

```text
system/feedback
system/authority/*
system/server/*
system/bus/*
system/axis/*
system/axes/*
system/io/*
```

역할:

```text
system/feedback      전체 runtime feedback event
system/authority/*   command authority 제어
system/server/*      Motion Server 프로세스 상태/관리
system/bus/*         EtherCAT bus 상태/관리
system/axis/*        단일 축 명령
system/axes/*        다축 명령
system/io/*          I/O 장치 명령
```

## Connection

기본 포트는 `MOTION_SERVER_PORT`로 설정한다. 일반 기본값은 `15000`이다.

```python
import json
import socket

sock = socket.create_connection(("127.0.0.1", 15000))
sock.sendall((json.dumps({"cmd": "system/axes/status"}) + "\n").encode("utf-8"))
print(sock.recv(8192).decode("utf-8"))
```

서버는 연결된 client마다 주기적으로 `system/feedback`을 송신한다. 클라이언트는 요청 응답과 주기 feedback이 같은 TCP stream에 섞여 들어온다는 점을 고려해야 한다.

## Axis Selection

단일 축 명령은 `system/axis/*`를 사용하고 반드시 `axis` 필드를 포함한다.

```json
{"cmd": "system/axis/enable", "axis": 0}
```

다축 명령은 `system/axes/*`를 사용하고 반드시 `axes` 필드를 포함한다.

```json
{"cmd": "system/axes/enable", "axes": [0, 1, 2]}
```

`system/axis/*`는 `axes`를 받지 않고, `system/axes/*`는 `axis`를 받지 않는다.

## Units

Motion Server public API 단위는 다음과 같다.

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

## Command Authority

쓰기 명령은 command authority가 필요하다. 읽기/status 명령은 authority 없이 가능하다.

```text
system/authority/status
system/authority/request
system/authority/release
```

요청:

```json
{"cmd": "system/authority/request"}
```

성공 응답:

```json
{
  "type": "system/authority/request",
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

## Status and Feedback

### system/feedback

서버가 주기적으로 송신하는 전체 runtime feedback event다. I/O 장치가 설정되어 있으면 `io.devices`에 현재 process image 상태도 포함된다.

```json
{
  "type": "system/feedback",
  "target_positions": [0.0],
  "actual_positions": [0.0],
  "actual_velocities": [0.0],
  "statuswords": [33831],
  "mode_displays": [1],
  "io": {
    "devices": [
      {
        "id": "io0",
        "slave_index": 6,
        "profile": "cpx_ap_i_ec",
        "digital_inputs": [false, true],
        "digital_outputs": [true, false],
        "analog_inputs": [],
        "analog_outputs": [],
        "modules": []
      }
    ]
  },
  "command_authority": {}
}
```

### system/axes/status

전체 축 full snapshot을 요청한다. Axis Control Panel은 이 응답으로 축 수와 metadata를 파악한다.

```json
{"cmd": "system/axes/status"}
```

주요 응답 필드:

```json
{
  "type": "system/axes/status",
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

### system/axis/status

특정 축의 full snapshot을 요청한다.

```json
{"cmd": "system/axis/status", "axis": 0}
```

응답은 `system/axes/status`에서 해당 축에 해당하는 값을 scalar 형태로 제공한다.

```json
{
  "type": "system/axis/status",
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

### system/server/status

Motion Server 프로세스 상태 요약을 요청한다. 응답에는 server mode, 초기화 상태, axis count, cycle time 등이 포함된다.

```json
{"cmd": "system/server/status"}
```

### system/bus/status

EtherCAT bus 상태 요약을 요청한다. 응답에는 device count, axis count, WKC, expected WKC, statusword 요약 등이 포함된다.

```json
{"cmd": "system/bus/status"}
```

## Axis Commands

단일 축 명령은 모두 `axis` 필드를 사용한다.

```text
system/axis/status
system/axis/enable
system/axis/disable
system/axis/reset
system/axis/restart
system/axis/home
system/axis/stop
system/axis/move_abs
system/axis/move_rel
system/axis/move_vel
system/axis/jog_start
system/axis/jog_stop
system/axis/profile
system/axis/motion_limits
system/axis/software_position_limits
system/axis/mode
system/axis/manualCW
system/axis/param_read
system/axis/param_write
system/axis/param_save
```

Examples:

```json
{"cmd": "system/axis/enable", "axis": 0}
{"cmd": "system/axis/disable", "axis": 0}
{"cmd": "system/axis/reset", "axis": 0}
{"cmd": "system/axis/home", "axis": 0}
{"cmd": "system/axis/stop", "axis": 0}
{"cmd": "system/axis/mode", "axis": 0, "mode": "pp"}
```

절대 위치 이동:

```json
{"cmd": "system/axis/move_abs", "axis": 0, "position": 50.0}
```

상대 위치 이동:

```json
{"cmd": "system/axis/move_rel", "axis": 0, "distance": 10.0}
```

속도 이동:

```json
{"cmd": "system/axis/move_vel", "axis": 0, "velocity": 30.0}
```

Jog:

```json
{"cmd": "system/axis/jog_start", "axis": 0, "direction": "positive", "speed": "slow"}
{"cmd": "system/axis/jog_stop", "axis": 0}
```

Profile:

```json
{
  "cmd": "system/axis/profile",
  "axis": 0,
  "profile_velocity": 100.0,
  "profile_acceleration": 1000.0,
  "profile_deceleration": 1000.0,
  "profile_jerk": 0.0
}
```

Motion limits:

```json
{
  "cmd": "system/axis/motion_limits",
  "axis": 0,
  "positive_velocity_limit": 100.0,
  "negative_velocity_limit": -100.0,
  "max_acceleration": 1000.0,
  "max_deceleration": 1000.0
}
```

Software position limits:

```json
{
  "cmd": "system/axis/software_position_limits",
  "axis": 0,
  "negative_limit": -100.0,
  "positive_limit": 100.0
}
```

Parameter read/write/save:

```json
{
  "cmd": "system/axis/param_read",
  "axis": 0,
  "index": "0x6041",
  "subindex": "0x00",
  "data_type": "uint16"
}
```

```json
{
  "cmd": "system/axis/param_write",
  "axis": 0,
  "index": "0x6081",
  "subindex": "0x00",
  "data_type": "uint32",
  "value": 1000
}
```

```json
{"cmd": "system/axis/param_save", "axis": 0}
```

`system/axis/restart`는 API 이름만 예약되어 있으며, 현재 구현은 `not implemented` 응답을 반환한다.
`system/axis/manualCW`는 Advanced mode에서만 사용하는 수동 Control Word 명령이다.

## Axes Commands

다축 명령은 모두 `axes` 배열을 사용한다.

```text
system/axes/status
system/axes/enable
system/axes/disable
system/axes/reset
system/axes/stop
system/axes/move_abs
system/axes/move_rel
system/axes/move_vel
system/axes/trajectory
system/axes/trajectory_stop
```

Examples:

```json
{"cmd": "system/axes/enable", "axes": [0, 1, 2]}
{"cmd": "system/axes/disable", "axes": [0, 1, 2]}
{"cmd": "system/axes/reset", "axes": [0, 1, 2]}
{"cmd": "system/axes/stop", "axes": [0, 1, 2]}
```

다축 절대 위치 이동:

```json
{
  "cmd": "system/axes/move_abs",
  "axes": [0, 1],
  "positions": [50.0, 20.0]
}
```

다축 상대 위치 이동:

```json
{
  "cmd": "system/axes/move_rel",
  "axes": [0, 1],
  "distances": [10.0, -5.0]
}
```

다축 속도 이동:

```json
{
  "cmd": "system/axes/move_vel",
  "axes": [0, 1],
  "velocities": [30.0, -20.0]
}
```

Trajectory 명령은 Advanced mode 전용이다.

## IO Commands

I/O namespace는 CPX-AP-I 같은 I/O 장치를 위한 영역이다.
주기 모니터링은 `system/feedback`의 `io` 블록을 사용한다.
`system/io/status`와 `system/io/input_read`는 panel 초기화, 수동 refresh, full snapshot 요청처럼 단발성 조회가 필요할 때 사용한다.
`output_write`는 출력 process image를 변경한다.

```text
system/io/status
system/io/input_read
system/io/output_write
system/io/reset
system/io/restart
system/io/param_read
system/io/param_write
system/io/param_save
system/io/ethercat/param_catalog
system/io/iol/param_catalog
system/io/ap/param_read
system/io/ap/param_write
system/io/iolink/isdu_read
system/io/iolink/isdu_write
```

I/O SDO parameter access는 `axis`가 아니라 `io` selector를 사용한다.
`io`는 `MOTION_SERVER_BUS`에서 선언한 I/O id 또는 I/O index다.

```json
{
  "cmd": "system/io/param_read",
  "io": "io0",
  "index": "0x1000",
  "subindex": "0x00",
  "data_type": "uint32"
}
```

```json
{
  "cmd": "system/io/param_write",
  "io": "io0",
  "index": "0x8000",
  "subindex": "0x01",
  "data_type": "uint16",
  "value": "1"
}
```

### CPX-AP Module Parameters

CPX-AP-I-EC station의 AP module parameter는 일반 I/O SDO 명령 대신 AP 전용 명령을 사용한다.

```text
system/io/ap/param_read
system/io/ap/param_write
```

AP parameter access는 CPX-AP-I-EC의 `0x27F0 AP Parameter Access`
object를 통해 수행된다. 사용자는 EtherCAT OD subindex를 직접 다루지 않고
`module`, `parameter_id`, `instance`, `length`를 지정한다.
`module`은 `MOTION_SERVER_IO_<id>_MODULES`에서 선언한 AP module 번호다.
slot 0은 CPX-AP-I-EC interface module이므로 사용자가 접근하는 AP module은
1부터 시작한다. Motion Server는 이 번호를 장치의 `0x27F0:02 Module`
필드에 맞게 내부 변환한다.

```json
{
  "cmd": "system/io/ap/param_read",
  "io": "io0",
  "module": 1,
  "parameter_id": "0x00000001",
  "instance": 0,
  "length": 1,
  "data_type": "uint8"
}
```

```json
{
  "cmd": "system/io/ap/param_write",
  "io": "io0",
  "module": 1,
  "parameter_id": "0x00000001",
  "instance": 0,
  "data_type": "uint8",
  "value": "1"
}
```

응답에는 내부 access object index `0x27F0`과 AP parameter 정보가 포함된다.

```json
{
  "type": "system/io/ap/param_read",
  "ok": true,
  "io": "io0",
  "object_index": "0x27F0",
  "module": 1,
  "parameter_id": 1,
  "parameter_id_hex": "0x00000001",
  "instance": 0,
  "data_type": "uint8",
  "status": 0,
  "length": 1,
  "data": "01",
  "value": 1,
}
```

IO-Link ISDU API 이름은 예약되어 있으나 현재는 미구현이다.

```text
system/io/iolink/isdu_read
system/io/iolink/isdu_write
```

## Server and Bus Management

다음 명령은 namespace로 예약되어 있다. 현재 구현은 안전하게 `not implemented` 응답을 반환한다.

```text
system/server/reset
system/server/restart
system/bus/reconnect
system/bus/rescan
```

## Rejection Response

명령이 거부되면 일반적으로 다음 형식의 응답을 받는다.

```json
{
  "type": "command_rejected",
  "ok": false,
  "reason": "authority_required",
  "command": "system/axis/move_abs",
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
2. system/axes/status 확인
3. system/authority/request
4. system/axis/reset 필요 시 수행
5. system/axis/enable
6. system/axis/home
7. system/axis/mode -> pp
8. system/axis/profile 또는 system/axis/motion_limits 설정
9. system/axis/move_abs
10. system/feedback 또는 system/axis/status로 상태 확인
11. system/authority/release
```

예시:

```json
{"cmd": "system/axes/status"}
{"cmd": "system/authority/request"}
{"cmd": "system/axis/enable", "axis": 0}
{"cmd": "system/axis/home", "axis": 0}
{"cmd": "system/axis/mode", "axis": 0, "mode": "pp"}
{"cmd": "system/axis/profile", "axis": 0, "profile_velocity": 100.0, "profile_acceleration": 1000.0, "profile_deceleration": 1000.0}
{"cmd": "system/axis/move_abs", "axis": 0, "position": 50.0}
{"cmd": "system/authority/release"}
```
