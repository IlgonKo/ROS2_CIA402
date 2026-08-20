# Motion Server Software Architecture

이 문서는 Motion Server의 내부 소프트웨어 구조를 설명한다. 현재 GUI와 일부 로그에는 과거 명칭인 Axis Server가 남아 있지만, 역할 기준으로는 EtherCAT/CiA402 축 제어를 담당하는 Motion Server로 본다.

## 목적

Motion Server는 상위 클라이언트가 EtherCAT 세부 구현을 직접 다루지 않고, TCP JSON API로 CiA402 기반 축을 제어할 수 있게 하는 중간 계층이다.

주요 책임은 다음과 같다.

- TCP 클라이언트 연결 관리
- 명령 제어권 관리
- API 단위와 드라이브 단위 변환
- 축별 motion mode 관리
- CiA402 controlword/statusword 기반 상태 제어
- mock backend와 pysoem backend 선택
- 주기 feedback 송신

## 전체 흐름

```text
Client
  -> TCP JSON line
  -> motion_server.api.router
  -> motion_server.handlers.*
  -> motion_server.app.runtime.AxisRuntime
  -> motion_server.device_manager.DeviceManager
  -> EtherCAT master backend
       -> pysoem real drive
       -> mock virtual servo drive
```

## 주요 폴더

```text
motion_server/
  server.py                 Main server loop
  config.py                 CLI/env 설정과 feature mode
  api/                      TCP API decode, validation, routing, encoding
  app/                      Runtime loop, startup, process data cycle
  handlers/                 status/authority handler
    authority/              command authority handler
    status/                 status/feedback handler
    command/                system/axis/io command handler
  control/                  motion controller, unit conversion helpers
  device_manager/           EtherCAT device groups, logical selector, SDO access

ethercat/
  pysoem_master.py          Real EtherCAT master backend
  mock_master.py            Virtual EtherCAT-like backend
  mock_slave.py             Mock slave wrapper

device/
  cmmt/                     Festo CMMT profile, PDO, OD, codec
  virtual_servo_drive/      Virtual CiA402 servo drive
  cia402/                   CiA402 공통 state machine
  pdo_metadata/             PDO mapping entry와 data type metadata helper
  cpx_ap_i_ec/              CPX AP I EC profile 준비 영역

control_panel/
  axis_control_panel/       Motion axis monitoring/control GUI
  io_control_panel/         Remote I/O monitoring/control GUI

docker/
  motion_server/            Motion Server image
  axis_panel/               Motion Server Control Panel image

scripts/
  host/                     Linux EtherCAT host 실행/서비스 스크립트
  windows/                  Windows 직접 실행/패키징 보조 스크립트
```

## Runtime 계층

### server.py

`motion_server/server.py`는 메인 루프를 가진다.

- EtherCAT process data cycle 실행
- 클라이언트 accept
- 클라이언트 메시지 dispatch
- 주기 `system/feedback` 송신
- homing/trajectory/diagnostic 상태 업데이트

### AxisRuntime

`motion_server/app/runtime.py`의 `AxisRuntime`은 motion controller와 drive manager를 묶는 facade이다.

상위 command 계층은 가능하면 backend가 pysoem인지 mock인지 직접 알 필요 없이 `runtime.slaves`, `runtime.sdo`, `runtime.set_target_positions()` 같은 API를 사용한다.

### DeviceManager

`motion_server/device_manager/device_manager.py`는 전체 EtherCAT device와 논리 device group을 관리한다.

- `AxisDeviceGroup`: axis index와 EtherCAT slave index 바인딩, 축 feedback, 축 단위 변환, motion command 적용
- `IoDeviceGroup`: I/O id 또는 I/O index와 EtherCAT slave index 변환
- `LogicalSdoAccess`: `runtime.sdo.axis.*`, `runtime.sdo.io.*` typed SDO 접근 제공

상위 command 계층은 가능한 한 EtherCAT slave index를 직접 다루지 않고 `axis` 또는 `io` selector를 사용한다.

## Backend 구조

### pysoem backend

실제 EtherCAT 장치와 통신한다.

```text
PySOEMMaster
  -> physical EtherCAT NIC
  -> EtherCAT slaves
  -> device profile PDO codec
```

Motion Server는 PDO remap을 런타임에 수행하지 않는다. 사용할 PDO mapping은 장치 설정 단계에서 사전에 준비되어 있어야 한다. 서버는 설정된 PDO를 읽고 쓰며, 필요한 필드가 없으면 해당 기능을 거부한다.

### mock backend

실제 장치 없이 같은 API를 검증하기 위한 backend이다.

```text
MockMaster
  -> MockSlave
  -> Axis wrapper
  -> VirtualCiA402Servo
```

mock backend도 같은 TCP API, 같은 command path를 사용한다. 따라서 UI, ROS Bridge, 사용자 프로그램은 backend 차이를 크게 의식하지 않아도 된다.

## Device Profile

장치별 차이는 `device/<profile>/` 아래에 둔다.

- PDO 구조
- PDO codec
- vendor specific OD
- mode별 필요한 PDO field
- SDO write/read helper
- parameter save 방식

CMMT는 CiA402 servo drive profile을 기반으로 하며, CPX AP I EC처럼 servo가 아닌 장치는 별도 profile로 확장한다.

## Unit Conversion

Motion Server API 단위는 사용자 관점 단위로 정규화한다.

- linear axis position: mm
- rotary axis position: deg
- velocity: mm/s 또는 deg/s
- acceleration/deceleration: mm/s^2 또는 deg/s^2
- jerk: mm/s^3 또는 deg/s^3

축 내부 단위는 `AxisUnitConverter`가 장치의 unit object와 exponent를 기반으로 변환한다. 따라서 API 사용자는 CMMT 내부 count, SI exponent, rotary unit encoding을 직접 계산하지 않는다.

## Command Authority

Motion Server는 다중 TCP 클라이언트를 허용한다. 단, motion command 충돌을 막기 위해 쓰기 명령에는 command authority가 필요하다.

```text
system/authority/request
  -> owner가 없으면 현재 client가 owner
  -> 다른 client가 owner이면 거부

system/authority/release
  -> owner인 client만 반납 가능

client disconnect
  -> owner client가 끊기면 자동 반납
```

읽기/status 명령은 authority 없이 가능하다.

## API 분류

API namespace 의미는 다음 규칙을 따른다.

```text
system/*       전체 시스템 대상
axis/*         특정 축 대상
authority/*    command authority 대상
```

현재 Basic mode 기준 주기 feedback은 전체 시스템 값이므로 `system/feedback`을 사용한다. 특정 축의 full snapshot은 `system/axis/status`를 사용한다.

## Logging

서버 로그는 목적별로 나누어 켜고 끈다.

```text
MOTION_SERVER_COMMAND_LOGS=1  수신 JSON command 로그
MOTION_SERVER_STATUS_LOGS=1   authority, mode, homing, enable/disable, stop/reset,
                              client connection, periodic Axis status 로그
MOTION_SERVER_STATUS_LOG_PERIOD=1.0  periodic Axis status 로그 주기
```

일반 운전에서는 `MOTION_SERVER_STATUS_LOGS=0`으로 두고, 상태 변화 추적이 필요할 때만 켠다.

## Basic Mode와 Advanced Mode

Basic mode는 사용자 프로그램이 일반적인 축 제어를 수행하기 위한 모드이다.

Basic mode에서 사용하는 기능:

- authority
- status/feedback
- enable/disable/reset/home/stop
- PP/PV mode 선택
- absolute/relative/velocity/jog command
- profile/motion/software limits
- SDO parameter read/write/save

Advanced mode 전용 기능:

- CSP mode 노출
- trajectory command
- system/axis/manualCW

사용자 API 문서는 Basic mode 기준으로 별도 문서에 정리한다.
