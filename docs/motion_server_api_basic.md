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

`profile_velocity`는 `0x6081`이 RxPDO에 포함된 PDO configuration에서는 device SDO readback 값만을
의미하지 않는다. 이 경우 Motion Server는 `system/axis/profile` 요청 시 `0x6081` SDO write와
RxPDO `profile_velocity` command value 갱신을 함께 수행하며, status의 `profile_settings[0]`은
앞으로 cyclic PDO로 송신할 effective profile velocity default를 표시한다.

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
system/axis/fault_reset
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
{"cmd": "system/axis/fault_reset", "axis": 0}
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

`system/axis/restart`는 대상 장치 재발견, process image 재구성 및 parameter refresh가 완료된
뒤에 응답한다. 시작 전에 모든 Axis를 현재 위치에 hold하고 disable하며 진행 중에는 전체 Bus
motion이 제한된다. 완료 후에도 이전 motion을 재개하거나 Axis를 자동 enable하지 않는다.
별도 recovery worker를 사용하지 않으므로 이 요청이 끝날 때까지 같은 서버의 다른 API 응답도
일시 정지한다. 기존 TCP 연결과 command authority는 유지된다.
`system/axis/manualCW`는 Advanced mode에서만 사용하는 수동 Control Word 명령이다.

## Axes Commands

다축 명령은 모두 `axes` 배열을 사용한다.

```text
system/axes/status
system/axes/enable
system/axes/disable
system/axes/fault_reset
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
{"cmd": "system/axes/fault_reset", "axes": [0, 1, 2]}
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
system/io/iol/param_read
system/io/iol/param_write
```

`system/io/ethercat/param_catalog`는 CPX-AP-I-EC 본체 EtherCAT OD catalog를 반환한다.
AP module별 parameter catalog는 이 API에 섞지 않고 `system/io/ap/param_catalog`에서 별도로
다룬다. 따라서 `system/io/ethercat/param_catalog`는 `module` 또는 `slot` 입력을 사용하지 않는다.
응답의 `scope`는 `station`이고, 각 object에는 `station`, `identity`, `diagnosis`, `sync`,
`pdo_mapping` 같은 `group`이 포함된다.

### IO-Link Input Decoding (RF-015)

`system/feedback.io.devices[]`, `system/io/status.devices[]`, `system/io/input_read`의
`modules[].inputs.io_link_channels[]`는 다음 형태이다. `output_write` 응답의 input도 동일하다.

```json
{
  "port": 0,
  "data": "3f800000c00000003f000000000000004080000040a0000041d6666600800000",
  "qualifier": 160,
  "decode_status": "ok",
  "decoded": {
    "profile": 1,
    "profile_name": "Vibration Velocity",
    "values": [
      {"subindex": 1, "name": "PD v-RMS X", "value": 1.0, "unit": "mm/s"}
    ],
    "status_bits": [
      {"subindex": 16, "bit_offset": 23, "name": "Severity Zone A", "active": true}
    ]
  }
}
```

위 예시는 values/status_bits를 축약했다. 실제 응답은 inactive bit도 포함한 전체 지원 field를 제공한다.
`profile`은 설정의 숫자 Condition value이며 무조건부 profile은 null이다. scalar subindex는 0,
RecordItem은 IODD subindex를 사용한다. field 식별에는 IO id/module slot/port/subindex를 조합한다.

| decode_status | 의미 |
|---|---|
| `ok` | 선택된 profile의 기본 숫자/Boolean/flat Record 디코딩 성공 |
| `not_configured` | 해당 포트에 IODD binding 없음 |
| `unsupported` | 지원하지 않는 datatype/구조 또는 해석할 수 없는 metadata |
| `invalid_data` | 공통 process-data 무효, qualifier 무효/누락, 길이 부족 또는 비정상 float |

`ok`가 아니면 decoded는 null이고 raw/qualifier는 유지된다. 미설정 포트는 데이터 유효성과 관계없이
not_configured이다. 설정된 포트는 데이터 유효성 검사 후 지원 여부를 판정한다.
CPX PQ(bit7), DevCom(bit5)가 모두 1이어야 유효하며 DevErr(bit6)만으로 무효화하지 않는다.
qualifier byte 자체가 없으면 null이다. Bus 단절 시에는 stale 값이 정상 측정값으로 제공되지 않는다.

raw `data`는 variant padding을 포함하지만 decoder는 IODD 유효 길이만 사용한다.
`inputs.io_link` module raw는 유지하며 별도 `inputs.io_link_qualifiers` 배열은 제거했다.
outputs의 `io_link_channels`는 기존 port/data 형식 그대로이다.
단위는 확인된 표에 없으면 null이며 값은 반올림하지 않는다. 타입/단위 지원 범위는
[RF-015](tasks/rf/RF-015-io-link-feedback-decoding.md)를 참조한다.

### Virtual I/O Simulation

Virtual CPX 입력 주입은 일반 I/O 명령과 분리된 개발·시험용 namespace를 사용한다.

```text
system/simulation/io/input_read
system/simulation/io/input_write
system/simulation/io/input_reset
```

`.env`에서 아래 두 조건이 모두 만족될 때만 사용할 수 있다.

```env
MOTION_SERVER_BACKEND=mock
MOTION_SERVER_SIMULATION_API_ENABLED=1
```

이 명령은 command authority를 요구하지 않는다. 설정한 값은 다음 PDO cycle부터 기존
`system/feedback`, `system/io/status`, `system/io/input_read`에 반영된다.

Digital Input:

```json
{
  "cmd": "system/simulation/io/input_write",
  "io": "io0",
  "slot": 2,
  "kind": "digital",
  "channel": 0,
  "value": true
}
```

Analog Input:

```json
{
  "cmd": "system/simulation/io/input_write",
  "io": "io0",
  "slot": 4,
  "kind": "analog",
  "channel": 0,
  "value": 1234
}
```

IO-Link Input Process Data는 module 전체 raw payload로 지정한다.

```json
{
  "cmd": "system/simulation/io/input_write",
  "io": "io0",
  "slot": 5,
  "kind": "io_link",
  "payload": "0001020304050607"
}
```

현재 상태 조회에서 `io`를 생략하면 모든 Virtual CPX station을 반환한다.

```json
{"cmd": "system/simulation/io/input_read"}
```

Module 또는 station 입력 초기화:

```json
{"cmd": "system/simulation/io/input_reset", "io": "io0", "slot": 2}
{"cmd": "system/simulation/io/input_reset", "io": "io0"}
```

입력은 client 연결이 끊겨도 유지되며 reset, bus reconnect 또는 server restart 시 기본값으로
초기화된다. `pysoem` backend 또는 API 비활성 상태에서는 `UNSUPPORTED_OPERATION` Failure를
반환한다.

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
`module`은 Motion Server의 public module 번호다. `module=0`은
CPX-AP-I-EC base/interface module이고, `module=1..N`은
`MOTION_SERVER_IO_<id>_MODULES`에서 선언한 AP module 번호다.
Motion Server는 이 번호를 장치의 `0x27F0:02 Module` 필드에 맞게
내부 변환한다.

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

### IO-Link Parameters

IO-Link device catalog와 process-data decoding은 `system/io/iol/*` namespace를 사용한다.

```text
system/io/iol/param_catalog
system/io/iol/param_read
system/io/iol/param_write
```

`system/io/iol/param_catalog`는 설정된 IODD binding과 해당 IO-Link port의 parameter catalog를
반환한다. 응답의 `object_index`는 CPX-AP-I-EC firmware별 module index stride를 반영한 내부
ISDU Access object다. 예를 들어 `MOTION_SERVER_IO_io0_MODULE_PDO_INDEX_STRIDE=0x0010`이고
IOL module이 slot 1이면 `object_index`는 `0x2011`이다.

`system/io/iol/param_read`와 `system/io/iol/param_write`는 이 ISDU Access object를 통해 실행된다.
사용자는 EtherCAT OD subindex를 직접 다루지 않고 `module`, `port`, IO-Link `index/subindex`,
`data_type`, `length/value`를 지정한다.

```json
{
  "cmd": "system/io/iol/param_read",
  "io": "io0",
  "module": 1,
  "port": 1,
  "index": 81,
  "subindex": 0,
  "length": 1,
  "data_type": "uint8"
}
```

대표 응답:

```json
{
  "type": "system/io/iol/param_read",
  "ok": true,
  "io": "io0",
  "object_index": "0x2011",
  "module": 1,
  "port": 1,
  "index": 81,
  "index_hex": "0x0051",
  "subindex": 0,
  "subindex_hex": "0x00",
  "data_type": "uint8",
  "status": 0,
  "length": 1,
  "data": "01",
  "value": 1
}
```

ISDU parameter는 IODD catalog에 선언된 access 권한과 subindex 범위 안에서만 허용한다.

## Server and Bus Management

Server와 Bus의 Fault 처리 및 recovery 명령은 다음과 같다.

```text
system/server/fault_reset
system/server/restart
system/bus/fault_reset
system/bus/reconnect
system/bus/rescan
```

`system/bus/rescan`은 아직 구현되지 않았다. Bus reconnect는 현재 runtime과 TCP client를
유지하며 transport/process image/parameter refresh를 동기 수행한다. Server restart만 새
process와 Diagnostic 저장소를 만든다. Bus reconnect는 `initialization_error`,
`bus_disconnected`, `fault` 상태에서만 허용되고 `normal` 상태에서는 거부된다. 별도 recovery
worker가 없으므로 reconnect가 완료될 때까지 status/stop을 포함한 다른 API 요청 처리는
일시 정지하지만 기존 TCP socket과 command authority는 유지된다. Parameter refresh는 PRE-OP에서
완료하며 OP 진입 후 expected WKC가 3회 연속 확인되어야 Success를 반환한다.

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
4. system/axis/fault_reset 필요 시 수행
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
