# Test Procedure

이 문서는 Motion Server 프로젝트에서 수정, 리팩토링, 기능 추가 후 배포 전에 수행할
테스트 항목과 절차 초안이다.

목표는 변경 영향 범위를 빠뜨리지 않고 확인하는 것이다. 모든 항목을 매번 같은 강도로
수행할 필요는 없지만, Windows package 또는 Linux Docker 배포 전에는 해당 환경의
절차를 반드시 완료한다.

## RF-015 IO-Link 입력 디코딩 회귀

- 자동 검증: `python -m unittest tests.test_io_link_decoding` 및 전체 unittest를 실행한다.
  기본 타입, flat Record/DatatypeRef, metadata scale, 독립 raw fixture, qualifier 및 무효 입력,
  포트 격리, mock/실장치용 codec parity와 4-port payload/처리 비용을 확인한다.
- mock으로 시험할 때 RF-014 input_write에는 module 전체 raw를 넣는다. Variant 32는
  4개 port × 32byte 후 qualifier 4byte이며 시험 포트 qualifier를 `0xA0`으로 설정한다.
  다음 cycle의 io_link_channels에서 raw/qualifier/decoded를 확인한다. qualifier를 0으로 바꾸면
  raw는 남고 decoded=null, decode_status=invalid_data여야 한다.
- 실센서 대조는 별도 수행한다. 설정 profile과 장치의 실제 process-data mode가 같음을 확인하고,
  vendor tool의 값/단위와 Feedback을 비교한다. API는 장치 mode를 자동 변경하지 않는다.
  케이블 단절 시 stale 값이 정상으로 표시되지 않는지도 확인한다.
- 신규 String/Array/nested/vendor datatype이 나오면 raw가 유지되고 unsupported로 보고되는지
  확인한다. 타입 지원 확대는 실제 IODD 근거와 fixture를 추가한 후 수행한다.

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
   - CPX firmware에 따라 slot-dependent module PDO index 간격이 다르면
     `MOTION_SERVER_IO_<io>_MODULE_PDO_INDEX_STRIDE`를 설정한다.
     예: module slot PDO가 `0x7001/0x6001`, `0x7002/0x6002`가 아니라
     `0x7010/0x6010`, `0x7020/0x6020`으로 보이면 `0x0010`.
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

5. Virtual input simulation 확인 (`mock` 전용)

   - `04 Virtual I/O Simulation` Dashboard에서 Refresh를 눌렀을 때
     `MOTION_SERVER_SIMULATION_API_ENABLED=1`과 `mock` 조건에서 API가 available로 표시되는지 확인한다.
   - DI checkbox, AI raw integer와 IO-Link hexadecimal payload를 설정한다.
   - 설정 직후 다음 PDO cycle의 기존 I/O feedback에 동일 값이 표시되는지 확인한다.
   - Reset Module은 선택 module만, Reset Station은 해당 station 전체 입력을 초기화하는지 확인한다.
   - command authority를 다른 client가 보유해도 simulation input 변경이 가능한지 확인한다.
   - API 비활성 또는 `pysoem` backend에서는 Dashboard가 not available을 표시하고 API가 거부되는지
     확인한다.

6. EtherCAT parameter 확인

   - IO Control Panel의 EC Parameter 탭에서 catalog load가 동작하는지 확인한다.
   - ESI에 존재하는 OD read가 성공하는지 확인한다.
   - ESI에 없는 OD는 서버에서 거부되는지 확인한다.
   - `VISIBLE_STRING`/`STRING(n)` 계열이 표시 가능한 문자열과 hex data로 함께 표시되는지 확인한다.

7. AP parameter 확인

   - 지원되는 AP parameter read/write가 `0x27F0` mailbox sequence로 수행되는지 확인한다.
   - `0x27F0:01` trigger가 마지막에 write되는지 확인한다.
   - `0x27F0:05` status가 `0xFFFF` busy에서 `0x0000` 또는 error로 전이되는지 확인한다.
   - write 가능한 parameter만 변경하고, read-only parameter write는 실패해야 한다.

8. IO-Link ISDU 확인

   - IODD binding이 있는 포트에서 catalog load와 process-data decoding이 동작하는지 확인한다.
   - `system/io/iol/param_catalog`의 `object_index`가 실제 firmware/module stride와 일치하는지
     확인한다. 예: `MOTION_SERVER_IO_io0_MODULE_PDO_INDEX_STRIDE=0x0010`이고 IOL module이
     slot 1이면 `0x2011`.
   - `system/io/iol/param_read`로 대표 read 가능한 ISDU parameter를 읽는다.
   - `system/io/iol/param_write`는 쓰기 가능한 parameter에서만 수행하거나, read-only parameter에
     대해 정확한 device reject/permission failure가 반환되는지 확인한다.
   - 실패 시 Fail detail에 `isdu_step`, `sdo_index`, `sdo_subindex`, `sdo_value`,
     device code/status가 포함되는지 확인한다.

## Windows Package Test

대상: Windows 실행 파일, `config.txt`, Tools, Manual 포함 규칙.

1. Package layout 확인

   기대 구조:

   ```text
   Motion Server\
     motion_server.exe
     config.txt
     device\
       io_link\
         iodd\
     Tools\
       axis_control_panel\
       io_control_panel\
       list_ethercat_nics.ps1
       Npcap installer
     Manual\
     Reference Clients\
       node_red\
         node-red-contrib-motion-server\
   ```

   - package build 후 프로젝트 `dist` 아래에는 최종 `Motion Server` 폴더만 남아야 한다.
   - `dist\pyinstaller`와 `build\pyinstaller` 같은 중간 산출물 폴더가 남지 않아야 한다.

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

5. Reference client와 IODD 폴더 포함 확인

   - 사용자 IODD 파일 저장용 `device\io_link\iodd` 폴더가 생성되는지 확인한다.
   - frozen Windows package에서 `device\io_link\iodd`가 bundled `_internal` IODD보다 먼저 검색되는지
     확인한다.
   - Node-RED reference client package가 `Reference Clients\node_red\node-red-contrib-motion-server`에
     포함되는지 확인한다.
   - sample flow `01_connection_and_authority.json`부터 `05_sample_motion_sequence.json`까지
     `examples\flows` 아래에 포함되는지 확인한다.
   - `node_modules`는 package에 포함하지 않고 대상 PC에서 npm install로 재구성한다.

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

## RF-002 Reference Client Test

Python package 자동 시험:

```powershell
python -m unittest tests.test_reference_python_client
```

Node-RED package 자동 시험과 production dependency audit:

```powershell
cd reference_clients/node_red/node-red-contrib-motion-server
npm install
npm test
npm audit --omit=dev
```

독립 설치 확인:

```powershell
python -m pip wheel --no-deps --wheel-dir .runtime/rf002-wheels reference_clients/python
cd reference_clients/node_red/node-red-contrib-motion-server
npm pack --dry-run
```

Mock Motion Server smoke test:

1. `.env`에서 `MOTION_SERVER_BACKEND=mock`으로 서버를 시작한다.
2. Python client로 `system/server/status` Success와 `system/feedback` 수신을 확인한다.
3. Node-RED에 package를 설치하고 `01_connection_and_authority.json`을 먼저 import한다.
4. Dashboard `/dashboard/server`의 compact server control bar에서 Host/Port를 입력하고 Connect를
   누른다. 연결 상태가 connected로 바뀌는지 확인하고 Disconnect 후 자동 재연결되지 않는지 확인한다.
5. 기능별 검증이 필요하면 `02`~`05` Flow를 추가 import한다. 모든 Motion Server node와 Dashboard
   Page가 `01`의 같은 Connection Config 및 Dashboard Base/Theme을 참조하는지 확인한다.
6. read-only status Inject 응답이 첫 번째 Request 출력으로
   전달되는지 확인한다.
7. Dashboard에서 Authority를 명시적으로 요청/해제하고 Bus Reconnect, Server Fault Reset과 Server
   Restart가 각각 대응 API를 호출하는지 확인한다. authority 및 Motion Server Status 표시가 feedback에
   따라 변경되고 재연결 후 authority가 자동 복원되지 않는지도 확인한다.
8. Axis flow의 position/velocity chart가 선택 축만 표시하고 축 선택 변경 및 disconnect에서
   초기화되는지 확인한다. 선택 축의 Profile parameters, Motion Limits와 Software Position Limits가
   status 값과 단위로 초기화되는지 확인하고 command authority 획득 후 각각 적용한다. 성공 후 장치
   readback 값으로 다시 표시되는지 확인한다. 선택 축의 parameter catalog/read/write/save도 확인한다.
9. I/O flow에서 device/module 상태와 Raw Image를 확인하고 command authority 획득 후 Digital Output을
   적용한다. EC/AP/IO-Link parameter read/write와 catalog를 확인하되 Virtual Input Simulation 항목이나
   `system/simulation/io/*` 요청이 포함되지 않았는지 확인한다.
10. Virtual I/O Dashboard에서 Refresh 후 Mock station/module 목록이 표시되는지 확인한다. 선택 module의
    DI, AI 또는 IO-Link 입력을 적용하고 현재 상태 표와 일반 I/O feedback에 반영되는지 확인한다.
    Module Reset과 Station Reset도 확인하며 command authority 없이 동작하는지 검증한다.
11. Sample Motion Sequence Flow가 별도 Sequence node 없이 기존 Request/Feedback node와 단계별
    Function node로 구성되어 있는지 확인한다. 각 단계의 임의 축·위치·속도와 I/O target을 시험 환경에
    맞게 수정한 뒤 Start한다. 각 완료 gate가 feedback 조건을 만족할 때만 다음 명령을 보내며 Stop이
    기존 `system/axes/stop` 요청을 전송하는지 확인한다.
12. 상태 변경, motion 및 output command가 deploy만으로 실행되지 않는지 확인한다.

실장치에서 Axis/I/O 명령 flow를 사용할 때는 target과 parameter를 먼저 검토하고 수동 Inject로만
실행한다. Python client와 Node-RED Connection 모두 단절 시 pending request를 실패 처리하며 자동
재전송하거나 command authority를 자동 재획득하지 않는다.

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
