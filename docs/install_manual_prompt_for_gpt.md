# Motion Server 설치 매뉴얼 작성 요청 프롬프트

아래 내용을 바탕으로 한국어 설치 매뉴얼을 작성해줘.

## 작성 목적

Motion Server 프로젝트 사용자가 다음 두 가지 환경에서 Basic mode 기준으로 설치하고 설정할 수 있도록 안내하는 설치 매뉴얼을 작성한다.

1. Windows 실행 패키지 버전
2. Linux Docker 버전

매뉴얼은 개발자 내부 문서가 아니라, 사용자가 실제 설치와 설정을 따라 할 수 있는 문서여야 한다.

## 프로젝트 개요

Motion Server는 CiA402 기반 디바이스를 제어하기 위한 TCP JSON 서버다.

Axis Control Panel은 Motion Server에 TCP로 접속하여 축 상태를 확인하고, Basic mode 기준의 profile position/profile velocity motion, limit 설정, diagnosis 기능을 제공하는 GUI다.

Basic mode에서는 CSP/trajectory 같은 advanced cyclic command는 설명하지 않는다.

## 공통 전제

- Motion Server public API 단위:
  - Linear axis position: `mm`
  - Rotary axis position: `deg`
- Basic mode 기준:
  - `MOTION_SERVER_MODE=basic`
  - 일반 운전 모드는 PP mode 중심
  - PV mode는 rotary unit 계열에서만 사용 가능
  - CSP/trajectory/advanced 기능 설명은 제외하거나 “Advanced mode 기능”으로만 짧게 언급
- 설정 파일은 초 단위 값을 사용한다.
  - 예: `PYSOEM_CYCLE_TIME=0.01`
  - 예: `MOTION_SERVER_FEEDBACK_PERIOD=0.05`

## Windows 실행 패키지 버전

### 패키지 개요

Windows 패키지는 Docker 없이 실행된다.

예상 패키지 구조:

```text
Motion Server
  motion_server.exe
  config.txt
  config.example.txt
  device
    cmmt
      config.txt
      config.example.txt
    cpx_ap_i_ec
      config.example.txt
    virtual_servo_drive
      config.txt
      config.example.txt
  Manual
    Motion_Server_Installation_Manual_*.*
    Motion_Server_User_Manual_*.*
  Reference
    cmmt_error_catalog.json
  Tools
    axis_control_panel
      axis_control_panel.exe
      config.txt
      config.example.txt
    list_ethercat_nics.ps1
    npcap-*.exe
```

### Windows 사전 준비

포함할 내용:

- Windows 10/11 권장
- 실제 EtherCAT device 사용 시 Npcap 설치 필요
- Npcap 설치 시 WinPcap API-compatible mode 옵션 권장
- 관리자 권한 PowerShell이 필요할 수 있음
- EtherCAT용 NIC는 일반 네트워크와 분리 권장

### Windows 설정 파일

주 설정 파일:

```text
Motion Server\config.txt
```

Axis Control Panel 설정 파일:

```text
Motion Server\Tools\axis_control_panel\config.txt
```

Device profile 설정 파일:

```text
Motion Server\device\<profile>\config.txt
```

예:

```text
Motion Server\device\cmmt\config.txt
```

### Windows 주요 설정 항목

`config.txt`에서 설명해야 할 항목:

```text
MOTION_SERVER_BACKEND=pysoem
MOTION_SERVER_MODE=basic
PYSOEM_INTERFACE=\Device\NPF_{...}
MOTION_SERVER_BUS=cmmt
MOTION_SERVER_DEVICE_CONFIG_ROOT=device
MOTION_SERVER_PORT=15000
PYSOEM_CYCLE_TIME=0.01
MOTION_SERVER_FEEDBACK_PERIOD=0.05
```

설명:

- `MOTION_SERVER_BACKEND`
  - `pysoem`: 실제 EtherCAT device
  - `mock`: virtual servo drive
- `MOTION_SERVER_MODE`
  - 설치 매뉴얼에서는 `basic` 기준
- `PYSOEM_INTERFACE`
  - Windows Npcap adapter 이름
  - 예: `\Device\NPF_{906A65C9-C606-4B1F-8384-2625829A4D18}`
  - `{}` 안의 GUID만 쓰는 것이 아니라 전체 `\Device\NPF_{...}` 형식 사용
- `MOTION_SERVER_BUS`
  - EtherCAT slave profile 순서
  - 예: `cmmt`
  - 예: `cmmt,cmmt`
  - I/O 포함 예: `cmmt,cmmt,io:cpx_ap_i_ec`
- `MOTION_SERVER_DEVICE_CONFIG_ROOT`
  - 기본값 `device`
  - Motion Server가 `MOTION_SERVER_BUS`에 등장한 profile을 보고 `device/<profile>/config.txt`를 자동 로드
- `MOTION_SERVER_PORT`
  - TCP server port
- `PYSOEM_CYCLE_TIME`
  - process-data cycle time, seconds
- `MOTION_SERVER_FEEDBACK_PERIOD`
  - Axis Control Panel/Client로 보내는 `system/feedback` 주기, seconds

Axis Control Panel 설정:

```text
MOTION_SERVER_HOST=127.0.0.1
MOTION_SERVER_PORT=15000
AXIS_CONTROL_PANEL_AXIS_NAMES=
AXIS_PANEL_AUTO_SDO_READS=0
```

설명:

- Panel과 Motion Server가 같은 PC면 `MOTION_SERVER_HOST=127.0.0.1`
- 다른 PC의 Motion Server에 접속하면 해당 PC IP 입력
- 축 수는 Panel이 Motion Server의 `system/axes/status` API로 자동 파악
- `AXIS_PANEL_AUTO_SDO_READS=0` 권장

### Windows 실행 방법

NIC 확인:

```powershell
powershell -ExecutionPolicy Bypass -File .\Tools\list_ethercat_nics.ps1
```

Motion Server 실행:

```powershell
.\motion_server.exe
```

Axis Control Panel 실행:

```powershell
.\Tools\axis_control_panel\axis_control_panel.exe
```

Mock/virtual servo 예:

```text
MOTION_SERVER_BACKEND=mock
MOTION_SERVER_BUS=cmmt,cmmt,cmmt
```

실제 EtherCAT 예:

```text
MOTION_SERVER_BACKEND=pysoem
PYSOEM_INTERFACE=\Device\NPF_{...}
MOTION_SERVER_BUS=cmmt
```

## Linux Docker 버전

### Linux 사전 준비

포함할 내용:

- Ubuntu PC 권장
- Docker Engine 및 Docker Compose plugin 필요
- 사용자가 docker group에 포함되어 있거나 sudo 사용
- EtherCAT NIC 이름 확인 필요
- 실제 EtherCAT device는 Linux PC에 직접 연결

NIC 이름 확인 예:

```bash
ip link
```

또는 프로젝트 스크립트:

```bash
bash scripts/host/adapters.sh
```

### Linux 프로젝트 위치

예:

```text
/home/festo/Documents/ROS_CIA402/virtual_ethercat
```

프로젝트 루트에서 실행한다고 가정한다.

### Linux 설정 파일

주 설정 파일:

```text
.env
```

Device profile 설정 파일:

```text
device/<profile>/.env
```

예:

```text
device/cmmt/.env
device/cpx_ap_i_ec/.env
device/virtual_servo_drive/.env
```

기본 생성:

```bash
cp .env.example .env
cp device/cmmt/.env.example device/cmmt/.env
```

필요 시:

```bash
cp device/virtual_servo_drive/.env.example device/virtual_servo_drive/.env
cp device/cpx_ap_i_ec/.env.example device/cpx_ap_i_ec/.env
```

### Linux 주요 설정 항목

`.env` 예:

```text
MOTION_SERVER_BACKEND=pysoem
MOTION_SERVER_MODE=basic
PYSOEM_INTERFACE=enp1s0
MOTION_SERVER_BUS=cmmt
MOTION_SERVER_DEVICE_CONFIG_ROOT=device
MOTION_SERVER_PORT=15000
PYSOEM_CYCLE_TIME=0.01
MOTION_SERVER_FEEDBACK_PERIOD=0.05
```

설명:

- `PYSOEM_INTERFACE`
  - Linux NIC 이름
  - 예: `enp1s0`
- `MOTION_SERVER_BUS`
  - 실제 EtherCAT slave 순서와 일치해야 함
- `MOTION_SERVER_DEVICE_CONFIG_ROOT=device`
  - `MOTION_SERVER_BUS` profile별 `.env` 자동 로드
- `MOTION_SERVER_MODE=basic`
  - 설치 매뉴얼 기준

### Linux Docker 실행

Motion Server 이미지 빌드 및 실행:

```bash
bash scripts/host/start.sh --build
```

이미 빌드되어 있으면:

```bash
bash scripts/host/start.sh
```

로그 확인:

```bash
docker logs -f ros_cia402_motion_server
```

중지:

```bash
bash scripts/host/stop.sh
```

Axis Control Panel 실행:

```bash
bash scripts/host/panel.sh --build
```

이미 빌드되어 있으면:

```bash
bash scripts/host/panel.sh
```

GUI 표시를 위해 X11 권한이 필요할 수 있음:

```bash
xhost +local:root
```

### Linux 부팅 자동 실행

systemd service 설치:

```bash
sudo bash scripts/host/service.sh install
```

상태 확인:

```bash
bash scripts/host/service.sh status
```

로그 확인:

```bash
bash scripts/host/service.sh logs
```

재시작:

```bash
sudo bash scripts/host/service.sh restart
```

중지:

```bash
sudo bash scripts/host/service.sh stop
```

제거:

```bash
sudo bash scripts/host/service.sh uninstall
```

## Device 설정 설명

### CMMT

파일:

Windows:

```text
device\cmmt\config.txt
```

Linux:

```text
device/cmmt/.env
```

주요 항목 예:

```text
PYSOEM_SYNC_MODE=0
MOTION_SERVER_MAX_VELOCITY=50.0
MOTION_SERVER_ACCELERATION=50.0
MOTION_SERVER_DECELERATION=50.0
MOTION_SERVER_JERK=100000.0
MOTION_SERVER_PP_JERK=100000
MOTION_SERVER_MOTION_MODE=pp
```

Basic mode 기준에서는 `MOTION_SERVER_MOTION_MODE=pp`를 권장한다.

## Troubleshooting 포함 요청

다음 문제와 점검 방법을 포함해줘.

### Windows

- `Npcap` 미설치 또는 WinPcap compatibility 미선택
- `PYSOEM_INTERFACE` 이름 오류
- PowerShell 실행 정책 문제
- Motion Server와 Panel의 port 불일치
- Panel이 다른 PC의 Motion Server에 접속할 때 방화벽 문제

### Linux Docker

- Docker daemon 미실행
- 사용자 docker group 권한 문제
- `PYSOEM_INTERFACE` NIC 이름 오류
- EtherCAT device가 다른 NIC에 연결됨
- 기존 container가 살아 있어서 재실행 충돌
- X11 권한 문제로 Axis Control Panel이 열리지 않음

## 문서 스타일 요구

- 한국어로 작성
- 사용자가 그대로 따라 할 수 있는 단계별 절차
- Windows와 Linux Docker를 명확히 분리
- Basic mode 기준으로 작성
- Advanced mode/CSP/MoveIt/ROS Bridge 내용은 설치 매뉴얼 본문에서 깊게 다루지 않음
- 설정 항목은 표 형태로 정리해도 좋음
- 명령어는 코드 블록으로 작성
- 최종 문서 제목 예:

```text
Motion Server 설치 매뉴얼 - Windows 패키지 및 Linux Docker Basic Mode
```
