# Remaining Tasks

이 문서는 앞으로 구현할 기능과 현재 코드에 남아 있는 기술 부채를 관리한다.
완료된 작업 이력은 [Work Log](worklog.md)에 기록한다.

마지막 전체 점검: 2026-08-20

점검 범위는 Python source, shell/PowerShell script, Docker Compose, 설정 예제와 Markdown 문서다.
외부 제공 ESI/IODD, PDF/packet capture, build/install/dist 산출물은 구조 분석 대상에서 제외했다.

관리 규칙:

- 기능은 `RF-*`, 기술 부채는 `TD-*` 식별자를 사용한다.
- 임시 fallback 또는 legacy 경로를 코드에 추가할 때는
  `TECH_DEBT[TD-xxx]` 주석과 이 문서의 항목을 같은 변경에서 함께 추가한다.
- 기술 부채에는 남겨 둔 이유와 제거 조건을 반드시 기록한다.
- 항목을 해결하면 코드 표식은 제거하되 문서 항목은 삭제하지 않고 `상태: complete`로 변경한다.
  완료 이력은 Work Log에도 함께 남긴다.
- 단순한 예외 처리나 방어 코드에는 표식을 붙이지 않는다. 교체 또는 제거 계획이 있는
  임시 호환 로직에만 사용한다.

기능 상태 값은 `planned`, `reserved`, `blocked`, `in_progress`, `complete`를 사용한다.
Tech Debt 상태 값은 `open`, `in_progress`, `complete`를 사용한다.
완료된 Tech Debt도 추적 이력을 위해 이 문서에 유지한다.

## Remaining Feature

### RF-001 CPX-AP-I-EC Virtual I/O

- 상태: `planned`
- 우선순위: 높음
- 목표: 실제 CPX-AP-I-EC가 없어도 동일한 설정과 API로 Remote I/O를 시험할 수 있게 한다.
- 범위:
  - `MOTION_SERVER_IO_<io>_MODULES`와 `MOTION_SERVER_IO_<io>_IOL_PORTS`를 그대로 사용한다.
  - DI/DO/AI/AO/IO-Link process image와 AP module layout을 모사한다.
  - EtherCAT SDO, AP parameter access, IO-Link ISDU의 테스트 가능한 가상 동작을 제공한다.
  - Motion Server와 IO Control Panel에서 실장치와 가상 장치를 같은 API로 다룬다.
- 완료 조건: 실장치 없이 IO feedback, output write, parameter read/write의 회귀 테스트가 통과한다.

### RF-002 Low-code Reference Client

- 상태: `planned`
- 우선순위: 높음
- 목표: Node-RED 같은 low-code 환경에서 Motion Server TCP JSON API를 바로 사용할 수 있게 한다.
- 범위:
  - JSON-lines 연결, 재연결, request/response correlation 예제를 제공한다.
  - authority request/release, `system/feedback`, axis motion, IO output, parameter access를 포함한다.
  - Basic mode 기준 Node-RED flow와 최소 Python reference client를 제공한다.
- 완료 조건: 사용자 코드가 패널 없이 Motion Server를 연결하고 축과 I/O를 제어할 수 있다.

### RF-003 예약된 Bus 및 I/O 관리 API

- 상태: `reserved`
- 우선순위: 보통
- 현재 미구현 API:
  - `system/bus/rescan`
  - `system/io/reset`
  - `system/io/restart`
  - `system/io/param_save`
- 선행 결정: 각 명령의 장치별 의미, authority 요구 여부, 실행 중 PDO 처리와 복구 정책을 확정한다.
- 완료 조건: API 문서, handler, 실장치 또는 virtual-device 검증이 함께 제공된다.

### RF-004 AP Parameter Catalog

- 상태: `blocked`
- 우선순위: 낮음
- 현재 상태: AP parameter read/write는 구현되어 있지만 catalog 조회와 사전 validation은 미구현이다.
- 이유: CPX EtherCAT ESI의 `0x27F0` 정보는 AP parameter access mailbox 형식만 설명하며,
  AP 하위 모듈별 parameter catalog는 APDD가 필요하다.
- 재개 조건: APDD를 안정적으로 확보하고 버전별로 캐시하는 정책이 확정된다.
- 비고: ESI의 EtherCAT OD catalog를 AP parameter catalog로 오인하지 않는다.

### RF-005 Runtime Fault 및 Recovery 모델 완성

- 상태: `planned`
- 우선순위: 보통
- 범위:
  - 정상, initialization-error, bus-disconnected, recoverable-fault 상태를 명시한다.
  - `system/server/reset`, `system/bus/reconnect`, server restart의 책임 경계를 확정한다.
  - runtime 재구성 후 authority와 client notification 정책을 검증한다.
- 완료 조건: 상태 전이와 API 응답이 문서화되고 mock/실장치 복구 시험이 통과한다.

### RF-006 배포 구성 최종 검증

- 상태: `planned`
- 우선순위: 보통
- 범위:
  - Windows 패키지의 Motion Server, Axis Control Panel, IO Control Panel, Tools, Manual 구성을 검증한다.
  - Linux Docker 설정과 Windows `config.txt`의 지원 항목을 맞춘다.
  - CMMT-AS/ST 및 CPX-AP-I-EC ESI/IODD 포함 규칙을 확정한다.
- 완료 조건: 새 Windows PC와 새 Linux PC에서 Basic mode 설치 절차가 그대로 재현된다.

### RF-007 CMMT ESI/PDO 실장치 검증 확대

- 상태: `in_progress`
- 우선순위: 높음
- 범위:
  - CMMT-AS/ST catalog, required OD, 축별 PDO configuration을 실제 구성에서 검증한다.
  - remap 후 assignment와 mapping entry readback을 비교한다.
  - 다른 ESI revision에서도 record/subindex parsing이 유지되는지 확인한다.
- 완료 조건: 6축 구성과 AS/ST 혼합 구성의 startup 및 motion smoke test가 통과한다.

### RF-008 ROS Bridge 후속 이관 및 테스트

- 상태: `reserved`
- 우선순위: 보통
- 보류 정책: 별도 언급 전까지 개발하지 않는다.
- 목표: Motion Server API와 설정 구조가 안정된 뒤 ROS Bridge를 최신 Motion Server 구조에 맞게 이관한다.
- 범위:
  - Motion Server command namespace, authority, feedback, axis/io status 변경을 ROS Bridge에 반영한다.
  - Motion Server의 mm/deg API 단위 정책과 ROS command/trajectory 단위 변환 경계를 재검토한다.
  - ROS Docker 구성, ROS Control Panel, Bridge connection 설정을 최신 Motion Server 설정과 맞춘다.
  - mock/virtual backend와 실장치 backend 기준으로 ROS Bridge smoke test를 수행한다.
- 완료 조건: ROS Bridge가 최신 Motion Server API로 축 command, feedback, authority 처리를 수행하고
  Docker 환경에서 재현 가능한 테스트 절차가 문서화된다.

### RF-009 Motion Server Trajectory API 정리

- 상태: `reserved`
- 우선순위: 보통
- 보류 정책: 별도 언급 전까지 개발하지 않는다.
- 목표: 다축 trajectory command API의 책임 범위와 구현을 Motion Server API 구조에 맞게 정리한다.
- 범위:
  - `system/axes/trajectory`와 `system/axes/trajectory_stop`의 payload, 단위, 완료/중단 응답을 확정한다.
  - PP/PV/CSP mode별 trajectory 지원 범위와 제한 조건을 정리한다.
  - 반복 동작, 단축 move, ROS trajectory 입력과의 책임 경계를 명확히 한다.
  - virtual backend 기반 자동 테스트와 실장치 smoke test 절차를 추가한다.
- 완료 조건: Trajectory API 문서, handler, validation, feedback 연동, 테스트가 함께 정리된다.

### RF-010 사용자 문서 최신화

- 상태: `planned`
- 우선순위: 보통
- 목표: 최근 Motion Server, Axis/IO Control Panel, EtherCAT device profile, Remote I/O 변경 내용을
  사용자 문서에 반영한다.
- 범위:
  - User Manual에 최신 API namespace, authority, axis/io feedback, parameter access, Basic mode 동작을 반영한다.
  - Installation Manual에 Windows package와 Linux Docker 설치/설정 절차, `config.txt`/`.env` 구조,
    ESI/IODD 배치 규칙을 반영한다.
  - 문서 파일명과 패키징 포함 규칙이 `docs` 폴더 기준으로 유지되는지 확인한다.
- 완료 조건: 최신 코드 기준으로 사용자 매뉴얼과 설치 매뉴얼을 검토하고,
  Windows/Linux Basic mode 절차가 문서만 보고 재현 가능하다.

## Tech Debt

### TD-003 Axis Server 과거 명칭 잔존

- 우선순위: 보통
- 현재 상태: 서버 로그, script 문구, 문서, 변수와 class 이름 일부에 `Axis Server`가 남아 있다.
- 범위 제외: 제품명이 확정된 `Axis Control Panel`은 변경 대상이 아니다.
- 대표 위치: `README.md`, `motion_server/config.py`, `motion_server/server.py`,
  `motion_server/api/dispatcher.py`, `scripts/host/*`, `scripts/windows/*`, packaging 문서.
- 제거 조건: 서버 자체를 가리키는 사용자 노출 명칭과 내부 설정명이 `Motion Server`로 통일된다.

### TD-004 Backend Capability Fallback과 오래된 Servo Interface

- 우선순위: 보통
- 현재 상태:
  - `ServoInterface`와 `Axis`가 virtual servo 중심의 오래된 계약을 유지한다.
  - 선택 기능을 `hasattr()`로 확인해 호출하는 경로가 있다.
  - startup이 backend method 존재 여부로 staged startup과 restart 지원을 판단한다.
- 대표 위치: `interfaces/servo_interface.py`, `motion_server/control/axis.py`,
  `motion_server/app/startup.py`, `motion_server/server.py`.
- 제거 조건: backend/device profile capability가 명시적인 interface 또는 capability object로 표현되고
  필수 메서드 누락이 startup 시점에 검증된다.

### TD-005 예외 경계와 오류 형식 불균일

- 우선순위: 높음
- 현재 상태: EtherCAT master, startup, SDO/AP/IOL parameter command, panel에서 broad `except Exception`이 다수 사용된다.
- 위험: mailbox timeout, unsupported OD, protocol validation, programming error가 같은 문자열 오류로 합쳐질 수 있다.
- 대표 위치: `ethercat/pysoem_master.py`, `ethercat/sdo_access.py`,
  `motion_server/app/startup.py`, `motion_server/handlers/command/io_parameters.py`,
  `motion_server/handlers/command/io_link_parameters.py`, 두 Control Panel.
- 제거 조건: transport/protocol/validation/runtime 오류 타입과 API error code를 구분하고,
  복구 가능한 오류만 해당 계층에서 처리한다.

### TD-006 설정 로더와 Bus Parser 중복

- 우선순위: 보통
- 현재 상태: 공통 `config_file.py` 외에 ROS runtime이 자체 `.env` parser와 단순 bus parser를 가진다.
- 위험: continuation, indexed entry, explicit `axis:`/`io:` 형식 해석이 실행 경로마다 달라질 수 있다.
- 대표 위치: `config_file.py`, `motion_server/config.py`, `ros/axis_runtime_config.py`,
  `packaging/windows_runtime.py`, panel별 `config.py`.
- 제거 조건: 모든 실행 경로가 공통 parser와 동일한 bus model을 사용한다.

### TD-007 Control Panel 중복 및 대형 모듈

- 우선순위: 보통
- 현재 상태:
  - IO Control Panel이 약 1,200줄의 단일 모듈이다.
  - Axis Diagnosis와 IO Panel이 catalog data type/length/label 변환을 중복 구현한다.
  - ROS Control Panel도 약 1,200줄의 단일 모듈이다.
- 대표 위치: `control_panel/io_control_panel/control_panel.py`,
  `control_panel/axis_control_panel/diagnosis.py`, `ros/control_panel.py`.
- 제거 조건: 공통 catalog utility를 도입하고 IO/ROS Panel을 connection, state, parameter tabs,
  view builder 단위로 분리한다.

### TD-008 Device 및 Runtime 책임이 큰 모듈

- 우선순위: 보통
- 현재 상태: CMMT profile, CPX module layout, virtual servo, PySOEM master와 server가 여러 책임을 가진다.
- 대표 위치: `device/cmmt/profile.py`, `device/cpx_ap_i_ec/module_layout.py`,
  `device/virtual_servo_drive/servo_model.py`, `ethercat/pysoem_master.py`, `motion_server/server.py`.
- 제거 조건: catalog/configuration, PRE_OP setup, runtime PDO, diagnostics와 recovery 책임을 분리하고
  각 모듈의 public interface를 테스트로 고정한다.

### TD-009 API 문서와 구현 불일치

- 우선순위: 높음
- 현재 상태:
  - API 문서는 `system/axis/restart`, server reset/restart, bus reconnect와 IO-Link ISDU를
    미구현으로 설명하지만 route에는 구현되어 있다.
  - README는 Motion Server가 PDO remap을 하지 않는다고 설명하지만 현재 정책은 항상 remap이다.
  - 과거 Axis Server 명칭과 manual CSP count scale 설명이 남아 있다.
- 대표 위치: `docs/motion_server_api_basic.md`, `README.md`, `docs/motion_server_architecture.md`.
- 제거 조건: command registry에서 API 목록을 검증하거나 생성하고, 문서 예제에 자동 smoke test를 연결한다.

### TD-010 자동 테스트 부재

- 우선순위: 높음
- 현재 상태: `diagnostics/pysoem_single_axis_smoke_test.py` 외에 독립적인 test suite가 없다.
- 우선 테스트 대상:
  - config continuation과 bus/module/IODD parser
  - CMMT ESI root/subindex와 PDO configuration 검증
  - CPX process image offset과 codec
  - API authority, routing, serialization, unit conversion
  - virtual servo state machine, homing, limit, stop/jog
- 제거 조건: mock backend 기반 회귀 테스트가 CI에서 실행되고 실장치 smoke test가 별도 profile로 구분된다.

### TD-014 Import 시점 전역 설정 로딩

- 우선순위: 보통
- 현재 상태: `motion_server/config.py` import가 `.env`와 device config를 읽어 `os.environ`을 변경한다.
- 위험: 테스트 격리, 여러 runtime 구성, packaging entrypoint의 동작을 예측하기 어렵게 한다.
- 제거 조건: 명시적인 configuration loader가 immutable config object를 만들고 runtime에 주입한다.

### TD-015 Virtual Servo Device Profile 기반 OD/PDO 구성 정리

- 우선순위: 보통
- 현재 상태:
  - Virtual Servo는 실제 slave SDO readback이 없으므로 내부 OD storage를 초기화해야 한다.
  - 현재 초기값은 `device/cmmt/required_od.py`의 `default` 값을 사용한다.
  - `device/virtual_servo_drive/od_model.py`가 `device.cmmt.required_od`를 직접 import한다.
  - Virtual Servo의 PDO configuration 선택 정책이 실축 CMMT의 축별 PDO configuration 정책과 명확히 분리되어 있지 않다.
  - 실축은 같은 required OD default로 drive 값을 덮어쓰지 않고, 실제 device SDO readback을 사용한다.
- 위험:
  - `required_od.py`가 “Motion Server 필수 OD 역할 정의”와 “Virtual Servo 초기 OD seed” 역할을 동시에 가진다.
  - Virtual Servo가 CMMT에 직접 의존하여 root `.env`의 `MOTION_SERVER_BUS`에서 선택한 device profile과
    virtual OD/PDO seed가 어긋날 수 있다.
  - 가상축별 PDO configuration을 명시적으로 선택하지 못하면 mock backend와 실축 backend의 PDO 검증/동작 조건이 달라질 수 있다.
- 대표 위치: `device/cmmt/required_od.py`,
  `device/cmmt/pdo_configuration.py`, `device/virtual_servo_drive/.env`,
  `device/virtual_servo_drive/od_model.py`, `ethercat/mock_slave.py`, `ethercat/mock_master.py`.
- 제거 조건:
  - device profile이 `required_od_roles()` 또는 동등한 interface를 제공한다.
  - Virtual Servo는 CMMT를 직접 import하지 않고 `device_profile.required_od_roles()`를 통해 OD seed를 구성한다.
  - root `.env`의 `MOTION_SERVER_BUS`에서 선택된 device profile의 PDO configuration registry를 사용한다.
  - 실제 가상축별 PDO configuration 이름은 `device/virtual_servo_drive/.env`에서 cmmt와 같은 형식으로 지정한다.
  - 설정이 없으면 해당 device profile의 default PDO configuration을 사용하고, 잘못된 이름이면 startup error를 발생시킨다.
  - required OD는 index/subindex/type/access/role 검증 용도로만 사용한다.

### TD-016 MockMaster의 Device-specific SDO 처리

- 우선순위: 높음
- 현재 상태:
  - `ethercat/mock_master.py`가 가상축 SDO read/write에서 CMMT/Servo OD index와 PDO field 매핑을 직접 알고 있다.
  - 예: `0x216E`, `0x2194`, `0x607D`, `0x6081`, `0x2005` 등을 `MockMaster._read_object()`와
    `_write_object()` 내부에서 개별 처리한다.
- 위험:
  - EtherCAT master 계층이 device-specific object semantics를 알게 되어 실축 `PySOEMMaster` 구조와 일관성이 깨진다.
  - CMMT 외 다른 virtual device 또는 CPX virtual I/O를 추가할 때 `MockMaster`가 계속 커질 수 있다.
- 대표 위치: `ethercat/mock_master.py`, `ethercat/mock_slave.py`,
  `device/virtual_servo_drive/od_model.py`, `device/virtual_servo_drive/od_bridge.py`.
- 제거 조건:
  - MockMaster는 SDO transport 역할만 담당한다.
  - 각 mock slave 또는 virtual device가 `read_sdo()`/`write_sdo()` 같은 object access interface를 제공한다.
  - device-specific OD/PDO mapping은 device 폴더 아래 bridge/model로 이동한다.

### TD-017 Motion Server API Layer 구조 정리

- 상태: `complete`
- 우선순위: 보통
- 완료 전 상태:
  - `motion_server/api` 아래에 `dispatcher.py`, `messages.py`, `responses.py`, `serializers.py`,
    `selection.py`, `validation.py`, `authority.py`가 혼재되어 있다.
  - API 메시지 해석, command 검증, handler 선택, status 응답 생성, 출력 직렬화 책임이 파일명과
    1:1로 맞지 않는다.
  - handler 성격의 로직과 protocol 입출구 로직이 같은 `api` 패키지 안에 섞여 있다.
- 정리 방향:
  - `api` 패키지는 protocol 입출구만 담당하도록 `decoder.py`, `validator.py`, `router.py`,
    `encoder.py` 중심으로 단순화한다.
  - `decoder.py`는 raw JSON/API payload를 내부 command 표현으로 변환한다.
  - `validator.py`는 authority, initialization state, basic/advanced mode, 값 타입과 범위를 검증한다.
  - `router.py`는 검증된 command를 적절한 handler로 연결한다.
  - `encoder.py`는 API 응답 payload 생성과 JSON line 전송을 담당하며 기존 serializer 역할을 흡수한다.
  - status, command, authority handler는 `api`가 아닌 별도 handler 계층으로 이동한다.
- 대표 위치: `motion_server/api/dispatcher.py`, `motion_server/api/messages.py`,
  `motion_server/api/responses.py`, `motion_server/api/serializers.py`,
  `motion_server/api/selection.py`, `motion_server/api/validation.py`,
  `motion_server/api/authority.py`, `motion_server/handlers/command/registry.py`.
- 제거 조건:
  - API 처리 흐름이 `decoder -> validator -> router -> handler -> encoder`로 정리된다.
  - `api` 패키지에는 protocol boundary 역할만 남고, 기능별 handler는 별도 폴더로 이동한다.
  - command registry와 API specification 검증이 유지되어 미등록 command/spec mismatch를 startup 전에 감지한다.
- 완료 내용:
  - `api/dispatcher.py`를 `api/router.py`로 변경하고 Motion Server 진입 경로를 갱신했다.
  - `api/messages.py`를 `api/encoder.py`로 변경하고 기존 serializer 역할을 흡수했다.
  - `api/selection.py`를 `api/decoder.py`로 변경하여 command name과 axis/io selector 해석을 담당하게 했다.
  - `api/validation.py`를 `api/validator.py`로 변경하고 authority, initialization state,
    basic/advanced mode guard를 추가했다.
  - `motion_server/commands` 아래 command handler를 `motion_server/handlers/command`로 이동했다.
  - status handler를 `motion_server/handlers/status` 폴더 아래
    `axis_status.py`, `bus_status.py`, `feedback.py`, `io_status.py`,
    `io_input_read.py`, `axis_parameter_read.py`, `io_ethercat_parameter_read.py`,
    `io_ap_parameter_read.py`, `io_iol_parameter_read.py`,
    `axis_parameter_catalog.py`, `io_ethercat_parameter_catalog.py`,
    `io_ap_parameter_catalog.py`, `io_iol_parameter_catalog.py`,
    `registry.py`, `server_status.py`로 분리했다.
  - command handler 파일명을 API target/operation 기준으로 정리했다.
    예: `axis_state.py`, `axis_settings.py`, `io_output_write.py`,
    `axis_parameter_write.py`, `axis_parameter_save.py`,
    `io_ethercat_parameter_write.py`, `io_ap_parameter_write.py`,
    `io_iol_parameter_write.py`.
  - authority handler를 `motion_server/handlers/authority` 폴더 아래
    `registry.py`, `rejections.py`, `status.py`로 분리했다.
  - authority, status, command 모두 `registry.py`를 handler entrypoint와 command mapping으로 사용한다.
  - 외부 entrypoint 함수 이름은 `handle_authority`, `handle_status`, `handle_command`로 통일했다.
  - read-only parameter/catalog 계열은 status handler로, write/save 계열은 command handler로 분류했다.
  - parameter 관련 entrypoint 파일은 `<api target>_<api operation>.py` 형태로 정리했다.
  - 실제 SDO/AP/IOL 접근 구현은 `motion_server/handlers/parameter_access` 아래
    `ethercat.py`, `ap.py`, `iol.py`로 분리했다.
  - CPX-specific ESI/IODD catalog 해석은 공개 API 파일인
    `io_ethercat_parameter_catalog.py`와 `io_iol_parameter_catalog.py`에 흡수하고,
    별도의 CPX 전용 handler 파일은 제거했다.
  - authority, status, command registry 모두 API specification과 handler 목록을 import 시점에 검증한다.
  - command handler registry와 specification mismatch 검증은 `handlers/command/registry.py`에서 유지했다.

### TD-018 Runtime 생성 단계 Initialization Error 처리

- 상태: `open`
- 우선순위: 높음
- 현재 상태:
  - `motion_server/server.py`는 `initialize_drive()` 실패만 degraded server loop로 전환한다.
  - `create_axis_runtime()` 중 발생하는 device profile/config/ESI 검증 오류는 degraded 처리 경계 밖에서 발생하여
    서버 프로세스가 기동 전에 종료된다.
  - 예: CPX-AP-I-EC module layout과 ESI PDO size mismatch가 발생하면 TCP server가 열리지 않고
    client가 `system/server/status`, `system/bus/reconnect`, `system/server/reset` 등을 보낼 수 없다.
- 위험:
  - 설정 오류나 ESI mismatch처럼 사용자가 Panel/API로 확인해야 하는 오류가 서버 기동 실패로만 노출된다.
  - 실장치 운전 중 bus reconnect/reset으로 복구 가능한 상태와 설정 검증 실패 상태의 사용자 경험이 달라진다.
- 대표 위치:
  - `motion_server/server.py`
  - `motion_server/app/startup.py`
  - `device/cpx_ap_i_ec/io_config.py`
  - `device/cpx_ap_i_ec/module_resolver.py`
- 제거 조건:
  - runtime 생성 단계의 설정/profile/catalog 검증 실패도 initialization-error 상태로 표현한다.
  - 최소 degraded runtime 또는 별도 degraded server state를 통해 TCP server는 계속 기동한다.
  - degraded 상태에서도 `system/server/status`, `system/bus/status`, `system/server/reset`,
    `system/server/restart`, `system/bus/reconnect` 응답이 가능하다.
  - device config 오류 메시지가 API response와 server log에 동일하게 표시된다.
