# Work Log

이 문서는 현재 Git 이력과 대화 맥락에서 파악 가능한 범위의 작업 기록이다.
날짜는 기본적으로 Git commit 날짜를 기준으로 정리했고, 아직 commit되지 않은 작업은 현재 작업일 기준으로 별도 기록한다.
미완료 기능과 기술 부채는 [Remaining Tasks](remaining_tasks.md)에서 별도로 관리한다.

## 2026-08-21

### 완료

- TD-004를 완료하여 backend staged lifecycle과 device capability 계약을 명시적으로 정의했다.
- MockMaster와 PySOEMMaster startup을 PRE-OP 설정 후 OP 진입 순서로 통일하고 method 존재 여부에
  따른 startup fallback을 제거했다.
- CMMT axis restart의 `AXIS_RESTART` capability 계약을 request/clear-request로 정리하고,
  write-command는 profile 내부 저수준 helper로 분리하여 `0 -> 1` request 전이를 자동 테스트로 고정했다.
- mock 전용 Axis wrapper와 공통 계약이 아니었던 ServoInterface를 제거하고 MockSlave가
  Virtual Servo 및 OD Model/Bridge를 직접 사용하도록 변경했다.
- backend/capability 자동 테스트를 포함한 15개 테스트와 CMMT-AS mock 전체 초기화를 통과했다.
- TD-016을 완료하여 MockMaster의 device-specific SDO index, datatype 및 reset/save 처리를 제거하고
  slave routing과 raw payload 전달만 담당하도록 정리했다.
- MockSlave object access를 Virtual OD Bridge에 위임하고, SDO/PDO가 동일 OD runtime value를
  공유하도록 통일했다.
- SDO datatype 변환과 reset/parameter save 부작용을 profile OD metadata와 role 기반으로 처리하고
  generic slave routing 및 Virtual Servo 회귀 테스트를 포함한 자동 테스트 8개를 통과했다.
- CMMT-AS 1축 mock 전체 초기화에서 CiA402 Operation Enabled 상태 진입을 확인했다.
- TD-015를 완료하여 Virtual Servo의 OD Model을 선택된 profile/ESI 기반의 전체 OD definition과
  runtime value 단일 저장소로 전환했다.
- required OD와 RxPDO/TxPDO metadata 공급을 device profile 계약으로 이동하고 Virtual Servo의
  CMMT 구현 모듈 직접 의존을 제거했다.
- mock과 실축이 동일한 축별 PDO configuration 선택 정책을 사용하도록 통일하고 잘못된 이름은
  startup error로 처리했다.
- OD direct access, RxPDO와 TxPDO가 같은 runtime value를 사용하는 자동 테스트 4개와
  CMMT-AS 1축 mock runtime smoke test를 통과했다.
- TD-003을 완료하고 server, Control Panel, ROS, script와 현재 문서의 사용자 노출 명칭을
  `Motion Server` 또는 `Axis Control Panel`로 통일했다.
- 기존 Linux 설치 호환성을 위해 `ros-cia402-axis-server.service` 식별자는 유지하고 TD-020에서 추적하게 했다.
- `diagnostics/check_legacy_names.py`를 추가해 허용 목록 밖의 과거 명칭이 다시 추가되지 않게 했다.

### 등록

- 가상축 생성 직후 서버 motion limit 설정이 required OD 초기값을 덮어쓰는 실축과의 startup 정책 비대칭을 `TD-023`으로 등록했다.
- 프로젝트·설치 경로 migration을 `TD-019`, legacy 실행 식별자 migration을 `TD-020`으로 등록했다.
- ROS package 식별자는 `RF-008`, 사용자 노출 Axis Server 명칭은 `TD-003`에서 처리하도록 범위를 분리했다.
- Windows launcher의 `PYTHONPATH` 중복 누적과 과도한 진단 출력을 `TD-021`로 등록했다.
- Motion Server 초기화 로그의 조건부 설정 출력과 device 상태 분리를 `TD-022`로 등록했다.
- Windows Service 자동 실행과 운영 로그 파일 보존 옵션을 `RF-011`로 등록했다.

### 문서 및 운영

- 공개 계약과 내부 helper의 경계를 `DEC-014`로 확정하고, TD 계약표·추적표 작성 규칙과
  최소 구현체/누락/내부 helper 부재 테스트 원칙을 문서 가이드에 추가했다.
- Codex가 구현 전에 계약 범위와 제외 범위를 확인하고 합의 없는 계약 확대를 중단하도록
  저장소 루트 `AGENTS.md`에 구현 규칙을 추가했다.
- TD-023의 MotionController 제한 기준을 device OD readback으로 확정하고 기존
  `MOTION_SERVER_MAX_VELOCITY`, `ACCELERATION`, `DECELERATION` fallback 제거와
  필수 readback 실패의 initialization error 처리를 완료 조건에 반영했다.
- profile/ESI 기반 OD Model을 SDO, PDO와 Virtual Servo의 단일 상태 경계로 사용하는 구조를
  `DEC-013`으로 확정하고 TD-004/015/016의 공통 정리 방향으로 연결했다.
- staged startup을 모든 backend의 필수 lifecycle 계약으로, device별 선택 기능만 capability로 다루는
  원칙을 `DEC-012`와 TD-004 상세 명세에 확정했다.
- TD-004의 axis restart capability를 `AXIS_RESTART`로 확정하고 상위 request/clear-request와
  저수준 command write의 명칭 및 책임을 상세 명세에 기록했다.
- `docs/README.md`를 추가하여 프로젝트 문서의 진입점, 문서별 책임과 갱신 규칙을 정리했다.
- `decisions.md`를 추가하여 기존 구현과 문서에서 확인되는 핵심 설계 결정을 `DEC-###` 형식으로 기록했다.
- 프로젝트 README에서 설계, API, 시험, 결정, 작업 목록과 작업 이력 문서로 바로 이동할 수 있게 연결했다.
- 공식 프로젝트명을 Motion Server로 확정하고 RF/TD 단위의 작업 브랜치 운영 원칙을 기록했다.
- `remaining_tasks.md`의 TD 항목을 상태, 우선순위, 요약, 강화된 완료 조건과 상세 링크 중심으로 간소화했다.
- TD별 현재 구조, 위험, 구현 범위와 검증 계획을 `docs/tasks/td` 상세 문서로 분리했다.
- `remaining_tasks.md`의 RF 항목도 동일한 형식으로 통일하고 완료 조건을 검증 가능한 결과로 강화했다.
- RF별 사용자 가치, 구현 범위, 제약과 검증 계획을 `docs/tasks/rf` 상세 문서로 분리했다.
- Work Log를 최신 날짜 우선으로 정렬하고 당일 기록을 완료, 등록, 문서 및 운영으로 구분했다.
- Work Log의 주요 설계 결정 요약을 `decisions.md`의 정식 DEC 항목으로 통합했다.

## 2026-08-20

- Axis Control Panel Diagnosis SDO Read/Write에 parameter catalog loading 기능 추가.
- 새 API `system/axis/param_catalog` 추가.
- Axis catalog는 선택된 축의 device profile과 CMMT ESI catalog를 기준으로 반환하도록 구현.
- Axis Control Panel Diagnosis 탭에 다음 UI 추가:
  - Catalog dropdown
  - Load Catalog 버튼
  - parameter 상세 정보 표시창
  - string SDO 접근용 Length 입력칸
- Catalog 항목 선택 시 `Index`, `Subindex`, `Type`, `Length`가 자동 입력되도록 구현.
- CMMT ESI parser 문제 수정:
  - 기존 parser는 `Object 0x1600`의 root object를 `SubIdx 0` 정보로 덮어써서 catalog 표시가 잘못되는 문제가 있었음.
  - `root_objects`와 `objects[(index, subindex)]`를 분리.
  - Catalog 표시는 root object 기준으로, 실제 SDO subindex 조회는 `object_info(index, subindex)` 기준으로 유지.
  - 예: 0x1600은 `receive PDO Mapping / DT1600 / 17 subitems`로 정상 파싱됨.
- Work Log에서 미완료 작업을 `remaining_tasks.md`로 분리.
- Remaining Feature와 Tech Debt에 안정적인 식별자를 부여하고, 임시 호환 코드의
  `TECH_DEBT[TD-*]` 표식 규칙을 도입.
- `tmp_test_logs/`를 Git ignore 대상에 추가하여 로컬 시험 산출물이 작업 트리에 나타나지 않게 정리.
- `TD-001 Legacy 환경변수와 설정 계층 혼재` 정리 완료:
  - 실행 코드, Docker Compose, Windows/Linux script, packaging runtime, ROS 설정 경로에서
    `AXIS_SERVER_*`, `PYSOEM_BUS`, `PYSOEM_DEVICE_CONFIG_ROOT` legacy fallback을 제거.
  - 서버 레벨 설정은 `MOTION_SERVER_*`로 통일하고, EtherCAT master 고유 설정인
    `PYSOEM_INTERFACE`, `PYSOEM_CYCLE_TIME`, DC/Sync 관련 설정은 유지.
  - `TD-001` 항목과 코드의 `TECH_DEBT[TD-001]` 표식을 제거.
  - 후속 전수 점검에서 발견한 Windows runtime의 `.env` fallback과
    `PYSOEM_CONTAINER_NAME`도 제거하여 `config.txt` 및
    `MOTION_SERVER_CONTAINER_NAME`으로 최종 통일.
- `TD-002 수동 CSP Count Scale 경로 잔존` 정리 완료:
  - `MOTION_SERVER_CSP_COUNTS_PER_UNIT`, `PYSOEM_CSP_COUNTS_PER_UNIT`,
    `ROS_BRIDGE_POSITION_COUNTS_PER_UNIT` 설정 경로를 제거.
  - Motion Server는 실축의 `0x216E`, `0x2194` readback과 virtual servo profile/config로
    축별 `axis_position_counts_per_api_unit`를 계산하도록 통일.
  - CSP trajectory generation, trajectory validation, diagnostic logging이 global scale 대신
    축별 scale을 사용하도록 수정.
  - ROS Bridge는 Motion Server API 단위를 다시 count로 변환하지 않고 direct API unit으로 처리.
  - README의 manual CSP scale 설정 예제를 제거하고 자동 scale 정책 설명으로 교체.
- Virtual Servo Drive 파일명 정리:
  - `drive.py`를 `servo_model.py`로 변경하여 가상 서보 동작 모델 역할을 명확히 함.
  - `object_dictionary.py`를 `od_model.py`로 변경하여 virtual OD model/storage 역할을 명확히 함.
  - `pdo_adapter.py`를 `od_bridge.py`로 변경하여 MockSlave와 servo model 사이의 OD/PDO bridge 역할 확장 의도를 명확히 함.
- `TD-013 Common Object Dictionary 패키지 명칭 부정확` 정리 완료:
  - `device/common_object_dictionary`를 `device/pdo_metadata`로 변경.
  - `ObjectDictionaryEntry`, padding, PDO mapping entry, data type metadata helper import를 새 패키지로 갱신.
  - README와 Motion Server architecture 문서의 폴더 설명을 새 이름과 실제 역할에 맞게 수정.
- `TD-012 IO-Link API Namespace 불일치` 정리 완료:
  - 공개 IO-Link parameter API를 `system/io/iol/param_catalog`,
    `system/io/iol/param_read`, `system/io/iol/param_write`로 통일.
  - 기존 `system/io/iolink/isdu_read/write` route와 Panel 호출부를 제거.
  - 내부 구현 파일을 `io_link_parameters.py`로 변경하고, ISDU는 내부 CPX access protocol 용어로만 유지.
  - API 문서와 test procedure의 IO-Link 명령 목록을 새 namespace로 갱신.
- `TD-011 API Command Registry 중복` 정리 완료:
  - command/status/authority, advanced-only, initialization-error 허용 여부를
    하나의 command spec에서 정의.
  - dispatcher의 command/status 분류 set을 command spec에서 생성하도록 변경.
  - routes와 command spec 간 누락/오타를 import 시점에 검증하도록 추가.
- `TD-017 Motion Server API Layer 구조 정리` 정리 완료:
  - API 처리 흐름을 `decoder -> validator -> router -> handler -> encoder` 구조로 재배치.
  - `api/decoder.py`, `api/validator.py`, `api/router.py`, `api/encoder.py` 중심으로 정리.
  - 기존 `motion_server/commands` command handler를 `motion_server/handlers/command`로 이동.
  - status handler와 authority handler를 `motion_server/handlers/status`,
    `motion_server/handlers/authority` 하위 폴더로 분리.
  - authority, status, command handler entrypoint를 모두 `registry.py` 기준으로 통일.
  - 외부 entrypoint 함수 이름을 `handle_authority`, `handle_status`, `handle_command`로 통일.
  - parameter read/catalog handler는 status 계층으로, parameter write/save handler는 command 계층으로 분류.
  - parameter 관련 파일명을 `<api target>_<api operation>.py` 기준으로 정리.
  - command handler 파일명을 `axis_state.py`, `axis_settings.py`, `io_output_write.py`,
    `axis_parameter_write.py`, `axis_parameter_save.py`, `io_ethercat_parameter_write.py`,
    `io_ap_parameter_write.py`, `io_iol_parameter_write.py`처럼 API target/operation 기준으로 정리.
  - status handler 파일명을 `axis_status.py`, `bus_status.py`, `server_status.py`,
    `io_status.py`, `io_input_read.py`, `io_ethercat_parameter_read.py`,
    `io_ap_parameter_read.py`, `io_iol_parameter_read.py`, `io_ethercat_parameter_catalog.py`,
    `io_ap_parameter_catalog.py`, `io_iol_parameter_catalog.py`처럼 API target/operation 기준으로 정리.
  - 공통 SDO/AP/IOL 접근 구현은 `handlers/parameter_access/ethercat.py`,
    `handlers/parameter_access/ap.py`, `handlers/parameter_access/iol.py`로 분리.
  - CPX-specific ESI/IODD catalog 해석은 공개 API 파일인
    `handlers/status/io_ethercat_parameter_catalog.py`와
    `handlers/status/io_iol_parameter_catalog.py`에 흡수하고,
    별도의 CPX 전용 handler 파일은 제거.
  - authority/status/command registry 모두 API specification과 handler 목록을 import 시점에 검증하도록 정리.
  - 기존 serializer 역할은 `api/encoder.py`에 통합.
  - `system/axis/param_read` command spec 누락을 보완하여 registry/spec 검증 기준을 맞춤.
- `TD-018 Runtime 생성 단계 Initialization Error 처리` 등록:
  - `initialize_drive()` 이전의 `create_axis_runtime()` 단계에서 CPX layout/ESI 검증 실패가 발생하면
    현재는 Motion Server 프로세스가 종료되는 문제를 기록.
  - 향후 설정/profile/catalog 검증 실패도 degraded server 상태로 노출하여 Panel/API에서 확인하고
    reset/restart/reconnect 명령을 보낼 수 있도록 정리 예정.

## 2026-08-19

- CMMT 관련 hard-coded OD/PDO 설정을 ESI + device 설정 기반으로 전환하는 작업 시작.
- CMMT-AS / CMMT-ST ESI catalog parser 추가.
- `.env`와 `device/cmmt/.env`에서 CMMT variant와 축별 PDO configuration을 읽는 구조 추가.
- CMMT profile identity를 실제 slave identity와 비교하는 로직 추가.
- Motion Server가 CMMT PDO mapping을 항상 remap하고, remap 후 실제 PDO mapping을 다시 읽어 설정과 비교하는 정책으로 변경.
- CMMT PDO configuration을 `motion_server_default`, `profile_position_basic`, `csp_basic` 등의 predefined configuration으로 분리.
- `required_od.py`를 추가하여 PDO가 아닌 Motion Server 필수 OD를 별도 관리하는 방향으로 변경.
- 기존 `device/cia402/object_dictionary.py`, `device/common_object_dictionary/ethercat.py`, `device/cmmt/object_dictionary.py`, `device/cpx_ap_i_ec/object_dictionary.py` 제거 방향으로 정리.
- Virtual Servo도 CMMT 설정과 ESI/PDO configuration을 따라가도록 구조 조정.

## 2026-08-18

- CPX IO catalog configuration support 추가.
- CPX-AP-I-EC ESI 파일을 device 폴더 아래로 이동하고, ESI 파일명 matching 규칙을 정리.
- ESI 파일명은 대소문자, underscore, dash 차이를 구분하지 않고 prefix matching하도록 정리.
- CPX module catalog와 ESI parser를 정리.
- CPX-AP-I-EC interface ident와 AP module ident를 비교하여 실제 구성과 설정 구성이 맞는지 검증.
- IO-Link variant 설정과 IOL process data size 관련 처리를 개선.
- IO Control Panel에서 module 구성 표시, IOL channel 표시, parameter catalog dropdown 표시를 개선.

## 2026-08-14

- CPX IO-Link parameter support 추가.
- AP Parameter Access와 IO-Link ISDU Access API 구현.
- `system/io/ap/param_read`, `system/io/ap/param_write` 구현.
- `system/io/iolink/isdu_read`, `system/io/iolink/isdu_write` 구현.
- IO Control Panel에 EC Parameter, AP Parameter, IOL Parameter UI를 분리.
- IO-Link IODD 기반 parameter catalog 방향을 정리.
- IO-Link port별 IODD device binding 구조 추가.

## 2026-08-13

- CPX-AP-I-EC remote I/O 지원 추가.
- `.env`에서 EtherCAT bus layout과 CPX-AP-I-EC I/O station 구성을 선언하는 구조 도입.
- CPX AP module layout parser 구현.
- DI/DO/AI/AO/IO-Link 모듈 선언을 기반으로 CPX RxPDO/TxPDO layout을 생성하는 구조 구현.
- IO Control Panel 초기 구조 추가.
- IO 상태를 `system/feedback`에 포함하고, IO Panel은 주기적 `system/io/status` polling 대신 feedback을 수신해 표시하는 방향으로 정리.

## 2026-07-27

- Axis Panel config formatting 정리.
- Motion Server feedback period 설정 추가.
- 전체 API namespace를 `system/*` 구조로 재정리.
- API command 구조를 다음 방향으로 정리:
  - `system/authority/*`
  - `system/server/*`
  - `system/bus/*`
  - `system/axis/*`
  - `system/axes/*`
  - `system/io/*`
- `axis/*`는 단축 명령, `axes/*`는 다축 명령으로 분리.
- `system/server/reset`, `system/server/restart`, `system/bus/reconnect`, `system/axis/restart` 구현 및 Panel 버튼 추가.

## 2026-07-23

- Axis Control Panel 리팩토링.
- 거대한 단일 모듈을 client, diagnosis, motion, motion_limits, trace, panel_update_data, ui_builders 등으로 분리.
- Single-axis view, panel layout, connection 관련 UI builder를 분리.
- Update GUI 흐름을 보조 메서드로 나누어 유지보수성을 개선.
- Packaging docs와 사용자 문서 갱신.

## 2026-07-22

- Windows Motion Server package 개선.
- 설정 파일명을 `.env` 대신 Windows 사용자에게 더 익숙한 `config.txt`로 사용하는 방향으로 변경.
- 패키지 산출물 폴더 이름을 `Motion Server`로 정리.
- Manual 문서를 패키지에 포함하는 규칙을 정리.

## 2026-07-21

- Motion Server API와 Virtual Servo 동작 보강.
- Virtual Servo software limit, warning bit, moving bit, homing 상태 동작을 개선.
- `system/feedback`, `system/axis/status`, `system/axes/status`의 역할을 정리.
- Feedback message는 주기적으로 TxPDO 대응 값 중심으로 보내고, full snapshot은 status command로 요청하는 방향을 정리.

## 2026-07-20

- Device profile 구조 리팩토링.
- CPX-AP-I-EC remote I/O 지원의 초기 기반 추가.
- CMMT와 CPX-AP-I-EC를 device profile로 분리.
- EtherCAT bus layout에서 motion axis와 I/O device를 함께 선언하는 구조 도입.
- CPX-AP-I-EC ESI 기반 module ident 검증 방향을 정리.

## 2026-07-16

- Motion Server architecture 리팩토링.
- Axis Server라는 이름에서 Motion Server 개념으로 확장하는 방향을 정리.
- Server, runtime, device manager, command routing, API response 구조를 더 명확히 분리.
- Axis Control Panel 설정 파일과 Motion Server 설정 파일을 분리하는 방향으로 정리.

## 2026-07-09

- Windows runtime packaging 작업 시작.
- Windows 실행 패키지에 Motion Server와 Axis Control Panel 실행 파일을 포함하는 방향으로 구성.
- Npcap installer와 NIC discovery tool 추가.
- Windows EtherCAT NIC 이름 지정 방식 정리.
- Connection 기반 command authority API로 변경.
- Client가 command authority를 request/release하고, 권한이 없을 때 명령이 거부되는 흐름 정리.

## 2026-07-08

- Axis Server motion control 개선.
- PP/PV/CSP mode 처리 보강.
- PV mode 지원을 Axis Control Panel에 추가.
- Basic mode에서는 CSP를 숨기고, PP/PV 중심의 실축 운용 흐름을 정리.
- Virtual Servo에서 homing, referenced bit, software limit, stop/jog 동작을 실제 servo에 가깝게 조정.

## 2026-07-07

- Axis Server command API와 motion module 구조 리팩토링.
- 기존 axis/control 흐름을 보다 명확한 command handler 구조로 나눔.
- command authority 구조에 대해 논의하고, 다중 client 상황에서 제어권 개념을 정리.

## 2026-07-06

- EtherCAT CSP diagnostics와 setpoint feedback 개선.
- CMMT device profile과 runtime environment 설정 구조를 리팩토링.
- CMMT 단위 변환 관련 SDO read, user position unit, converting unit exponent 처리 방향 정리.
- API 단위 정책을 linear=mm, rotary=deg 기준으로 잡고 drive unit과 API unit 사이 변환 로직을 조정.

## 2026-07-02

- EtherCAT sync 및 ROS Bridge configuration 보강.
- CSP 동작 안정성, interpolation 설정, DC/free-run 운용 관련 실험 진행.
- Linux Docker 및 Windows 실행 환경을 오가며 EtherCAT master 실행 구조를 정리.

## 2026-06-29

- Axis Control Panel에 motion limit 관련 기능 추가.
- CSP feedback 표시 및 trace 관련 기능 보강.
- 실제 EtherCAT/CMMT-AS 연결 테스트를 진행하며 PDO mapping, CiA402 state transition, fault reset, mode display 관련 문제를 조사.
- Festo CMMT-AS-C4의 RxPDO/TxPDO mapping을 실제 장치에서 확인하고 서버 쪽 PDO codec/parser를 맞춤.

## 2026-06-26

- Axis Server와 ROS Docker control stack 구조 정리.
- Axis Control Panel과 ROS 관련 실행 흐름을 Docker 기준으로 정리.
- 초기 GUI 기반 축 설정/명령/피드백 표시 구조를 다듬기 시작.

## 2026-06-25

- Virtual EtherCAT 프로젝트 초기 구조 생성.
- CiA402 기반 가상 EtherCAT 구동 실험을 위한 기본 코드 구성.
- 초기 Axis Server, mock/virtual servo, ROS 연동 실험의 출발점 마련.
