# Test Procedure

이 문서는 Motion Server 프로젝트에서 수정, 리팩토링, 기능 추가 후 배포 전에 수행할
테스트 항목과 절차 초안이다.

목표는 변경 영향 범위를 빠뜨리지 않고 확인하는 것이다. 모든 항목을 매번 같은 강도로
수행할 필요는 없지만, Windows package 또는 Linux Docker 배포 전에는 해당 환경의
절차를 반드시 완료한다.

## 적용 범위

- Motion Server
- Axis Control Panel
- IO Control Panel
- EtherCAT CMMT drive profile
- CPX-AP-I-EC Remote I/O profile
- Windows standalone package
- Linux Docker deployment

별도 지시 전까지 ROS Bridge와 Trajectory API 개발은 보류한다. 단, Motion Server API
namespace, feedback 형식, 단위 정책을 변경한 경우에는 이후 ROS Bridge와 Trajectory API
재개 시 반영해야 할 내용을 [Remaining Tasks](remaining_tasks.md)에 기록한다.

## 테스트 레벨

### Level 1: 코드 변경 후 기본 검사

대상: 모든 코드 변경, 문서 외 설정 변경.

1. Python 문법 검사

   ```powershell
   cd C:\Users\Festo\Documents\motion-server
   python -B -m compileall -q motion_server ethercat device control_panel interfaces ros packaging diagnostics
   ```

2. Legacy 제품명 검사

   ```powershell
   python -B diagnostics/check_legacy_names.py
   ```

3. 공백/줄바꿈 검사

   ```powershell
   git diff --check
   ```

4. Tech Debt 표식 검사

   - 새 임시 fallback 또는 legacy 경로가 있으면 `TECH_DEBT[TD-xxx]` 주석을 남긴다.
   - 같은 변경에서 [Remaining Tasks](remaining_tasks.md)의 `Tech Debt` 항목도 추가하거나 갱신한다.
   - 기능성 미완료 항목은 `Remaining Feature`에 `RF-*`로 기록한다.

5. 공개 API 영향 확인

   - command namespace가 변경되었는지 확인한다.
   - request/response 필드명이 변경되었는지 확인한다.
   - `system/feedback`, `system/axis/status`, `system/io/status` 형식이 변경되었는지 확인한다.
   - 변경되었다면 `docs/motion_server_api_basic.md`와 User Manual 갱신 필요 여부를 기록한다.

### Level 2: Mock/Virtual Backend Smoke Test

대상: Motion Server runtime, API, Control Panel, Virtual Servo 변경.

1. 설정 확인

   - root 설정에서 `MOTION_SERVER_BACKEND=mock` 또는 virtual backend 구성이 의도대로 되어 있는지 확인한다.
   - virtual servo 설정에서 축별 linear/rotary 설정과 software position limit이 의도대로 되어 있는지 확인한다.

2. Motion Server 기동

   ```powershell
   cd C:\Users\Festo\Documents\motion-server
   python motion_server/server.py
   ```

   기대 결과:

   - 서버가 initialization-error 없이 listen 상태가 된다.
   - 설정된 축 수가 `system/server/status` 또는 panel에서 일치한다.
   - 주기 `system/feedback`이 송신된다.

3. Authority 확인

   - Axis Control Panel에서 서버에 연결한다.
   - command authority를 요청한다.
   - authority 획득 전 write command가 거부되는지 확인한다.
   - authority 획득 후 write command가 수락되는지 확인한다.
   - authority release 후 write command가 다시 거부되는지 확인한다.

4. Axis 기본 동작

   각 축에 대해 확인한다.

   - `system/axis/enable`
   - `system/axis/home`
   - `system/axis/mode`로 PP/PV 전환
   - PP absolute move
   - PP relative move
   - PV jog start/stop
   - stop 중 moving bit와 actual velocity가 정상적으로 내려가는지 확인
   - software position limit 밖 command가 virtual servo에서 거부되는지 확인
   - referenced 되지 않은 상태에서 position move가 거부되는지 확인

5. Axis Control Panel 표시 확인

   - 선택 축만 command/limit/trace가 갱신되는지 확인한다.
   - statusword lamp가 bit별로 올바르게 표시되는지 확인한다.
   - target position, actual position, actual velocity trace가 feedback과 일치하는지 확인한다.
   - Diagnosis 탭의 SDO catalog UI가 열리고 수동 read/write 입력이 깨지지 않는지 확인한다.

## CMMT Real Drive Test

대상: CMMT profile, EtherCAT master, PDO configuration, unit conversion, real drive 관련 변경.

주의: 모터 전원, STO, drive alarm, software limit, 기구 안전 상태를 먼저 확인한다.

1. EtherCAT NIC 확인

   Windows package:

   ```powershell
   cd "C:\Motion Server\Tools"
   powershell -ExecutionPolicy Bypass -File .\list_ethercat_nics.ps1
   ```

   Linux Docker:

   ```bash
   ip link
   ```

2. 설정 확인

   - `MOTION_SERVER_BACKEND=pysoem`
   - `MOTION_SERVER_BUS`의 CMMT-AS/ST 선언과 실제 slave 순서가 일치하는지 확인한다.
   - `device/cmmt/config.txt` 또는 `device/cmmt/.env`에서 축별 상세 device type과 PDO configuration이 의도대로 되어 있는지 확인한다.
   - `PYSOEM_INTERFACE`가 실제 EtherCAT NIC 이름과 일치하는지 확인한다.

3. 서버 기동 확인

   기대 로그:

   - EtherCAT network가 PRE_OP/SAFE_OP/OP로 정상 진행된다.
   - CMMT ESI catalog와 실제 slave identity가 일치한다.
   - 각 slave에 RxPDO/TxPDO mapping write 로그가 표시된다.
   - remap 후 실제 PDO readback이 설정과 일치한다.
   - unit object `0x216E`, `0x2194` read가 성공한다.

4. CiA402 상태 전이 확인

   - fault 상태가 아니어야 한다.
   - Shutdown, Switch on, Enable operation 순서로 statusword가 이동한다.
   - `system/axis/fault_reset`으로 fault reset이 동작하는지 확인한다.
   - alarm이 해제되지 않으면 drive alarm code와 STO/motor power 상태를 먼저 확인한다.

5. Unit conversion 확인

   Linear axis:

   - API `position=50.0`은 50 mm 의미다.
   - drive unit exponent가 position `-6`, SI unit `m`이면 drive raw command는 50000 count 계열이어야 한다.
   - API velocity 100은 100 mm/s 의미다.

   Rotary axis:

   - API `position=50.0`은 50 deg 의미다.
   - drive user unit이 deg/rev 계열인지 확인한다.
   - PV mode는 drive unit이 rad/degree/rev 계열일 때만 허용된다.

6. PP/PV 동작 확인

   - PP absolute move가 target에 도달한다.
   - PP profile velocity, acceleration, deceleration이 drive에 반영된다.
   - PV jog start/stop이 software limit과 warning bit 동작을 포함해 의도대로 동작한다.
   - Basic mode에서 CSP가 숨겨지는지 확인한다.

7. Axis restart 확인

   - `system/axis/restart`는 모든 Axis의 homing/trajectory를 중단하고 현재 위치를 hold한 뒤
     전체 Axis를 disable한다.
   - disable 후 지정된 대기 시간이 적용된다.
   - CMMT restart command가 전송된다.
   - Axis restart 응답 전에 slave 재발견, process image 재구성 및 해당 축 parameter refresh가
     완료되는지 확인한다.
   - 완료 후 모든 Axis가 자동 enable되지 않고 이전 trajectory도 재개되지 않는지 확인한다.
   - restart 처리 중 기존 TCP 연결은 유지되지만 다른 status/stop 요청 응답은 완료 시점까지
     대기하는지 확인한다.

## CPX-AP-I-EC Remote I/O Test

대상: CPX AP module layout, PDO image, AP parameter, IO-Link ISDU, IO Control Panel 변경.

1. 설정 확인

   - `MOTION_SERVER_BUS`에 `io:cpx_ap_i_ec:<io_id>`가 실제 slave 순서와 일치하게 선언되어 있는지 확인한다.
   - `MOTION_SERVER_IO_<io>_MODULES`가 실제 AP module 구성과 일치하는지 확인한다.
   - IO-Link 장치가 있으면 `MOTION_SERVER_IO_<io>_IOL_PORTS`가 실제 포트 구성과 일치하는지 확인한다.
   - ESI와 IODD 파일이 device folder 규칙에 맞게 배치되어 있는지 확인한다.

2. CPX slave 초기화 확인

   기대 로그:

   - CPX-AP-I-EC ESI catalog가 로딩된다.
   - configured module ident와 detected module ident가 일치한다.
   - IOL variant가 설정과 일치한다.
   - TxPDO/RxPDO byte size가 장치 PDO와 일치한다.

3. IO feedback 확인

   - `system/feedback`에 `io` block이 포함되는지 확인한다.
   - IO Control Panel이 `system/io/status`를 주기 polling하지 않고 feedback으로 상태를 표시하는지 확인한다.
   - DI/DO 상태가 module/slot/channel별로 올바르게 표시되는지 확인한다.
   - IOL input/output data가 포트별로 표시되는지 확인한다.

4. DO/AO output 확인

   - command authority 없이 output write가 거부되는지 확인한다.
   - command authority 획득 후 `system/io/output_write`가 정상 수행되는지 확인한다.
   - 실제 DO lamp 또는 연결 부하가 command와 일치하는지 확인한다.

5. EtherCAT parameter 확인

   - IO Control Panel의 EC Parameter 탭에서 catalog load가 동작하는지 확인한다.
   - ESI에 존재하는 OD read가 성공하는지 확인한다.
   - ESI에 없는 OD는 서버에서 거부되는지 확인한다.
   - `VISIBLE_STRING`/`STRING(n)` 계열이 표시 가능한 문자열과 hex data로 함께 표시되는지 확인한다.

6. AP parameter 확인

   - 지원되는 AP parameter read/write가 `0x27F0` mailbox sequence로 수행되는지 확인한다.
   - `0x27F0:01` trigger가 마지막에 write되는지 확인한다.
   - `0x27F0:05` status가 `0xFFFF` busy에서 `0x0000` 또는 error로 전이되는지 확인한다.
   - write 가능한 parameter만 변경하고, read-only parameter write는 실패해야 한다.

7. IO-Link ISDU 확인

   - IODD binding이 있는 포트에서 catalog load가 동작하는지 확인한다.
   - port 입력은 필수다.
   - binding이 없는 포트는 명확한 오류를 반환한다.
   - 지원되는 ISDU read가 성공한다.
   - 지원되지 않는 index/subindex는 서버에서 거부된다.

## Windows Package Test

대상: Windows 실행 파일, `config.txt`, Tools, Manual 포함 규칙.

1. Package layout 확인

   기대 구조:

   ```text
   Motion Server\
     motion_server.exe
     config.txt
     device\
     Tools\
       axis_control_panel\
       io_control_panel\
       list_ethercat_nics.ps1
       Npcap installer
     Manual\
   ```

2. 사전 준비 확인

   - Npcap 설치 여부를 확인한다.
   - Windows 방화벽에서 Motion Server TCP port 접근이 필요한 경우 허용한다.
   - EtherCAT NIC이 다른 네트워크와 공유되지 않는지 확인한다.

3. 실행 확인

   - `motion_server.exe`가 같은 폴더의 `config.txt`를 읽는지 확인한다.
   - Axis Control Panel과 IO Control Panel이 각자 폴더의 `config.txt`를 읽는지 확인한다.
   - Panel에서 서버 IP/port를 입력해 연결할 수 있는지 확인한다.
   - Panel close가 container/process lifecycle을 예상과 다르게 종료시키지 않는지 확인한다.

4. Manual 포함 확인

   - `docs`의 User Manual과 Installation Manual이 package의 `Manual` 폴더에 포함되는지 확인한다.
   - 파일명 suffix가 `_KR`, version, English 등으로 바뀌어도 지정된 prefix 규칙으로 포함되는지 확인한다.

## Linux Docker Test

대상: Linux EtherCAT host Docker deployment.

1. 설정 확인

   - Linux EtherCAT NIC 이름을 확인한다.
   - `.env`와 device별 `.env`가 Linux host 기준으로 구성되어 있는지 확인한다.
   - Docker Compose가 host network 또는 EtherCAT raw socket 접근에 필요한 권한을 갖는지 확인한다.

2. Docker build/up

   ```bash
   cd /home/festo/Documents/motion-server
   docker compose -f docker/motion_server/compose.yaml up -d --build
   ```

3. 상태 확인

   ```bash
   docker compose -f docker/motion_server/compose.yaml logs -f motion_server
   ```

   기대 결과:

   - Motion Server container가 restart loop에 빠지지 않는다.
   - EtherCAT slave count와 configured bus가 일치한다.
   - feedback 주기가 설정값과 일치한다.

4. Boot service 확인

   - Linux 부팅 후 Motion Server container가 자동 시작되는지 확인한다.
   - `docker ps`에서 container가 running 상태인지 확인한다.
   - systemd service failure가 없는지 확인한다.

## API Regression Checklist

다음 명령은 변경 후 최소 1회 이상 확인한다. 실제 payload는 대상 축/I/O 구성에 맞춘다.

- `system/feedback`
- `system/authority/status`
- `system/authority/request`
- `system/authority/release`
- `system/server/status`
- `system/server/fault_reset`
- `system/server/restart`
- `system/bus/status`
- `system/bus/fault_reset`
- `system/bus/reconnect`
- `system/axis/status`
- `system/axis/enable`
- `system/axis/disable`
- `system/axis/fault_reset`
- `system/axis/restart`
- `system/axis/home`
- `system/axis/stop`
- `system/axis/move_abs`
- `system/axis/move_rel`
- `system/axis/move_vel`
- `system/axis/jog_start`
- `system/axis/jog_stop`
- `system/axis/profile`
- `system/axis/motion_limits`
- `system/axis/software_position_limits`
- `system/axis/mode`
- `system/axis/param_read`
- `system/axis/param_write`
- `system/axis/param_save`
- `system/axes/status`
- `system/io/status`
- `system/io/input_read`
- `system/io/output_write`
- `system/io/param_read`
- `system/io/param_write`
- `system/io/ethercat/param_catalog`
- `system/io/ap/param_read`
- `system/io/ap/param_write`
- `system/io/ap/param_catalog`
- `system/io/iol/param_catalog`
- `system/io/iol/param_read`
- `system/io/iol/param_write`

현재 reserved 상태인 API는 배포 blocking 항목으로 보지 않는다. 단, 문서에 reserved 또는
not implemented 상태가 명확히 표시되어야 한다.

Bus recovery 회귀에서는 다음을 추가 확인한다.

- `normal` 상태의 `system/bus/reconnect`는 거부된다.
- cable 분리 시 transport exception이 발생하는 경로와 WKC가 0으로 반복되는 경로 모두
  `bus_disconnected`로 전환된다.
- reconnect 중 TCP socket과 authority는 유지되지만 동기 recovery가 반환되기 전에는 같은
  server loop의 다른 API 응답이 일시 정지한다.
- reconnect 중 parameter SDO refresh가 PRE-OP에서 수행되고, OP 진입 후 WKC가 expected 값과
  3회 연속 일치한 뒤에만 Success를 반환하는지 확인한다.
- 상태 입력은 수신되지만 출력 PDO가 승인되지 않는 WKC 상태에서는 Axis Fault Reset을 시도하지
  않고 reconnect Fail 및 `bus_disconnected`로 처리되는지 확인한다.

## 배포 승인 기준

배포 전 다음 조건을 만족해야 한다.

- Level 1 검사가 통과한다.
- 변경 영향이 있는 backend의 smoke test가 통과한다.
- Windows package 또는 Linux Docker 중 배포 대상 환경 절차가 통과한다.
- User Manual, Installation Manual, API 문서 갱신 필요 여부를 확인했다.
- 새 Remaining Feature 또는 Tech Debt가 있으면 [Remaining Tasks](remaining_tasks.md)에 기록했다.
- 실장치 테스트에서 alarm, following error, PDO mismatch, SDO timeout이 남아 있지 않다.
