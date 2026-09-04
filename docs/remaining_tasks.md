# Remaining Tasks

이 문서는 앞으로 구현할 기능과 현재 코드에 남아 있는 기술 부채를 관리한다.
완료된 작업 이력은 [Work Log](worklog.md)에 기록한다.

마지막 전체 점검: 2026-08-27

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

- 상태: `complete`
- 우선순위: 높음
- 요약: 실장치와 동일한 설정 및 API로 시험할 수 있는 CPX-AP-I-EC Virtual I/O를 제공한다.
- 선행 작업: `TD-030`
- 완료 조건:
  - DI/DO/AI/AO/IO-Link process image와 AP module layout이 설정대로 생성된다.
  - ESI 기반 station/module OD, slot-dependent object와 선택된 `0x6F00`/`0x7F00` PDO block이
    설정대로 구성된다.
  - metadata 기반 공통 Virtual AP Module이 output process image와 독립 input state를
    Model_Update 시점에 처리한다.
  - station SDO와 AP parameter request/response 전달 경계가 동작한다.
  - IO-Link ISDU gateway는 TD-032에서 확정한 module slot/index stride 규칙으로 dispatch된다.
  - Motion Server와 IO Control Panel의 virtual I/O 회귀 테스트가 통과한다.
  - 실장치 profile과 virtual profile의 지원 범위 및 차이가 문서화된다.
- 상세: [RF-001 기능 명세](tasks/rf/RF-001-cpx-virtual-io.md)

### RF-002 Low-code Reference Client

- 상태: `complete`
- 우선순위: 높음
- 요약: 패널 없이 Motion Server API를 사용할 수 있는 Node-RED 및 Python reference client를 제공한다.
- 완료 조건:
  - JSON-lines 연결, 재연결과 request/response correlation이 구현된다.
  - authority, feedback, axis motion, I/O output과 parameter access 예제가 제공된다.
  - Node-RED 공통/Scenario Flow와 Python client smoke test가 동일한 공개 API 및 correlation 계약을
    검증한다.
  - clean environment에서 설치·실행 절차가 재현되고 자동 또는 scripted smoke test가 통과한다.
- 상세: [RF-002 기능 명세](tasks/rf/RF-002-low-code-client.md)

### RF-003 예약된 Bus 및 I/O 관리 API

- 상태: `reserved`
- 우선순위: 보통
- 요약: 예약된 bus rescan과 I/O reset/restart/parameter-save API의 계약과 구현을 완성한다.
- 완료 조건:
  - 각 명령의 device별 의미, authority, lifecycle과 PDO 처리 정책이 결정 문서에 확정된다.
  - API specification, validation, handler와 응답 형식이 구현된다.
  - 성공, 지원하지 않는 device, 실행 중 충돌과 복구 실패 경로가 자동 테스트된다.
  - 지원 장치의 virtual 또는 실장치 smoke test와 API 문서가 제공된다.
- 상세: [RF-003 기능 명세](tasks/rf/RF-003-bus-io-management.md)

### RF-004 AP Parameter Catalog

- 상태: `blocked`
- 우선순위: 낮음
- 요약: APDD 기반 AP module parameter catalog 조회와 write 사전 validation을 제공한다.
- 완료 조건:
  - 지원 module의 APDD source, version 식별과 cache 정책이 확정된다.
  - parameter metadata 조회 API와 type/range/access validation이 구현된다.
  - APDD 누락, version mismatch와 unsupported parameter 오류가 구분된다.
  - 대표 module catalog fixture와 실장치 parameter read/write 검증이 통과한다.
- 상세: [RF-004 기능 명세](tasks/rf/RF-004-ap-parameter-catalog.md)

### RF-005 Runtime Fault 및 Recovery 모델 완성

- 상태: `complete`
- 우선순위: 보통
- 요약: runtime Fault 상태와 fault-reset/reconnect/restart 복구 모델을 완성한다.
- 완료 조건:
  - normal, initialization-error, bus-disconnected와 fault 상태 및 전이가 명세된다.
  - source별 fault-reset, bus reconnect와 process restart의 책임 및 허용 조건이 구현된다.
  - Bus disconnect/reconnect 중 기존 runtime, TCP client와 authority 유지 정책이 일관되게 적용된다.
  - PySOEM Axis restart 완료·timeout·재연결 결과가 TD-025 cache refresh 호출 경계에 전달된다.
  - mock 오류 주입과 대표 실장치 복구 시나리오가 모두 통과한다.
- 상세: [RF-005 기능 명세](tasks/rf/RF-005-runtime-recovery.md)

### RF-006 배포 구성 최종 검증

- 상태: `planned`
- 우선순위: 보통
- 요약: Windows package와 Linux Docker 배포 구성을 clean system에서 최종 검증한다.
- 완료 조건:
  - Windows package의 server, panel, tools, manual과 catalog 구성이 정의대로 포함된다.
  - 사용자 IODD 저장 및 검색 폴더 `device/io_link/iodd`와 Node-RED reference client/sample flow가
    Windows package에 포함된다.
  - Linux `.env`와 Windows `config.txt`의 지원 설정 및 기본값 차이가 문서화된다.
  - ESI/IODD 포함, 검색과 version 선택 규칙이 두 환경에서 검증된다.
  - 새 Windows/Linux PC에서 Basic mode 설치 및 smoke-test 절차가 그대로 재현된다.
- 상세: [RF-006 기능 명세](tasks/rf/RF-006-deployment-validation.md)

### RF-007 CMMT ESI/PDO 실장치 검증 확대

- 상태: `complete`
- 우선순위: 높음
- 요약: CMMT-AS/ST ESI catalog와 PDO configuration을 다양한 실장치 구성에서 검증한다.
- 완료 조건:
  - 지원 AS/ST model 및 ESI revision별 catalog parsing 결과가 기록된다.
  - required OD와 축별 PDO assignment/mapping readback이 기대값과 일치한다.
  - 6축 및 AS/ST 혼합 구성의 startup, enable과 motion smoke test가 통과한다.
  - 실패 fixture와 실장치 시험 절차가 회귀 가능한 형태로 보존된다.
- 상세: [RF-007 기능 명세](tasks/rf/RF-007-cmmt-hardware-validation.md)

### RF-008 ROS Bridge 후속 이관 및 테스트

- 상태: `reserved`
- 우선순위: 보통
- 요약: Motion Server API 안정화 후 ROS Bridge와 ROS 실행 구성을 최신 계약으로 이관한다.
- 완료 조건:
  - command, authority, feedback과 axis/I/O status가 최신 API specification과 일치한다.
  - Motion Server mm/deg와 ROS SI unit 변환 경계가 문서화되고 자동 테스트된다.
  - ROS Docker, Control Panel과 connection 설정이 최신 configuration model을 사용한다.
  - mock 및 실장치 기준 trajectory/feedback smoke test 절차가 재현된다.
- 상세: [RF-008 기능 명세](tasks/rf/RF-008-ros-bridge-migration.md)

### RF-009 Motion Server Trajectory API 정리

- 상태: `reserved`
- 우선순위: 보통
- 요약: 다축 trajectory command의 API 계약, mode별 동작과 책임 경계를 정리한다.
- 완료 조건:
  - trajectory/stop payload, 단위, validation과 완료·중단 응답이 명세된다.
  - PP/PV/CSP별 지원 범위와 반복 동작, 단축 move, ROS 입력의 책임 경계가 확정된다.
  - handler, feedback와 cancel/error path가 구현되고 virtual backend 자동 테스트가 통과한다.
  - 지원 mode의 실장치 smoke test 및 안전 제한 조건이 문서화된다.
- 상세: [RF-009 기능 명세](tasks/rf/RF-009-trajectory-api.md)

### RF-010 사용자 문서 최신화

- 상태: `planned`
- 우선순위: 보통
- 요약: 사용자 및 설치 매뉴얼을 최신 Motion Server 기능과 배포 구성에 맞춘다.
- 완료 조건:
  - User Manual이 최신 API, authority, feedback, parameter access와 Basic mode를 설명한다.
  - Installation Manual이 Windows/Linux 설치, 설정과 ESI/IODD 규칙을 설명한다.
  - 문서 파일명, 내부 링크와 packaging 포함 검사가 통과한다.
  - 신규 사용자가 문서만으로 두 환경의 Basic mode 설치와 smoke test를 재현한다.
- 상세: [RF-010 기능 명세](tasks/rf/RF-010-user-documentation.md)

### RF-011 Windows Service 실행 및 파일 로그 옵션

- 상태: `planned`
- 우선순위: 보통
- 요약: Windows에서 Motion Server를 선택적으로 service로 자동 실행하고 운영 로그를 파일로 보존한다.
- 완료 조건:
  - Windows Service 설치, 제거, 시작, 중지, 재시작과 상태 확인 절차가 제공된다.
  - 기존 foreground/console 실행과 service 실행이 동일한 Motion Server 설정을 사용한다.
  - service 로그의 저장 경로, level, rotation, retention과 오류 시 fallback 정책이 설정 가능하다.
  - clean Windows PC에서 부팅 자동 시작, 정상 종료, 장애 후 재시작과 로그 보존 검증이 통과한다.
- 상세: [RF-011 기능 명세](tasks/rf/RF-011-windows-service-logging.md)

### RF-012 CPX-AP 선택형 상세 Diagnostic

- 상태: `reserved`
- 우선순위: 낮음 (Optional Item)
- 요약: CPX-AP의 선택형 Diagnosis TxPDO를 사용하여 I/O station의 상세 Diagnostic을 제공한다.
- 완료 조건:
  - `0x1AF1` TxPDO의 활성화 여부, PDO assignment와 process-image 배치가 설정 계약으로 확정된다.
  - `0x6102` Category Status, active count, module number와 diagnosis code의 해석 기준이 문서화된다.
  - station 단위 Alarm/Fault 변환과 상세 module 정보의 표현 방식이 실제 장치 동작을 기준으로 검증된다.
  - 선택형 PDO를 사용하지 않는 구성의 기존 I/O 동작과 real/mock parity가 유지된다.
- 상세: [RF-012 기능 명세](tasks/rf/RF-012-cpx-ap-optional-diagnostic.md)

### RF-013 Virtual AP Module 및 IO-Link Parameter Device

- 상태: `planned`
- 우선순위: 보통
- 요약: Virtual CPX gateway 뒤에 AP module parameter와 IO-Link ISDU runtime 공간을 가진 가상 장치를 제공한다.
- 완료 조건:
  - 설정된 AP module별 parameter/instance runtime 공간과 IO-Link module/port별 ISDU runtime 공간이 생성된다.
  - gateway OD 요청이 Model_Update 시점에 대상 virtual device로 전달되고 data/status 응답에 반영된다.
  - 기존 Motion Server AP parameter 및 IO-Link ISDU API의 read/write와 Failure 계약이 그대로 동작한다.
  - 초기값, access, reset 정책과 지원 장치 범위가 문서화되고 자동 테스트가 통과한다.
- 상세: [RF-013 기능 명세](tasks/rf/RF-013-virtual-ap-iol-parameter-devices.md)

### RF-014 Virtual Device Simulation API

- 상태: `complete`
- 우선순위: 보통
- 요약: Control Panel과 외부 simulator에서 Virtual CPX의 DI/AI/IO-Link input을 조작하는 별도 API를 제공한다.
- 완료 조건:
  - virtual I/O id, module, channel/port 기준 input 설정·조회·초기화 계약이 확정된다.
  - 주입한 DI/AI/IO-Link input이 다음 Model_Update cycle의 기존 I/O feedback에 반영된다.
  - virtual backend 및 명시적 활성화 조건이 적용되고 real backend에서는 안전하게 거부된다.
  - Control Panel과 외부 reference client 시나리오 및 자동 테스트가 통과한다.
- 상세: [RF-014 기능 명세](tasks/rf/RF-014-virtual-device-simulation-api.md)

### RF-015 IO-Link IODD 기반 Feedback 디코딩

- 상태: `complete`
- 우선순위: 보통
- 요약: IO-Link 포트별 raw 데이터와 qualifier를 유지하면서 선택된 IODD profile의 측정값·단위·상태 bit 해석 결과를 Feedback에 제공한다.
- 검증: 디코딩 16개 포함 전체 unittest 374개 통과. 4-port snapshot/JSON 약 0.15ms·14KB. 실센서 대조와 EXE 재빌드는 미수행.
- 완료 조건:
  - 포트별 raw/qualifier/decoded 응답 구조, 필드 식별자와 데이터 유효성 정책이 확정되고 API 문서에 반영된다.
  - 숫자로 선택한 profile 및 생략 시 첫 profile의 IODD metadata로 측정값과 상태 bit를 정확히 해석한다.
  - 미설정 IODD, 미지원 형식과 무효 입력을 정상 측정값과 구분하며 raw 데이터와 나머지 Feedback은 유지한다.
  - 독립 raw fixture, 다중 포트 격리, real/mock parity와 주기 Feedback 성능 회귀 검증이 통과한다.
- 상세: [RF-015 기능 명세](tasks/rf/RF-015-io-link-feedback-decoding.md)

### RF-016 Hidden Expert Mode

- 상태: `complete`
- 우선순위: 보통
- 요약: 개발자 전용 숨김 모드에서 Motion Server의 일부 raw access guard를 우회하여 실장치 진단과 commissioning 조사를 쉽게 한다.
- 검증: 전체 unittest 382개 통과.
- 완료 조건:
  - `MOTION_SERVER_EXPERT_MODE` 단일 숨김 설정이 추가되고 기본값은 off다.
  - 공개 README, 공개 API 문서, `.env.example`, Control Panel과 Node-RED Dashboard에는 일반 사용자 기능으로 노출하지 않는다.
  - normal mode에서는 CPX 내부 조사 후보 OD 등 Motion Server가 보호하던 raw access 차단을 유지한다.
  - expert mode에서는 command authority, runtime 상태 확인, transport 연결 확인, 장치 reject와 fault 처리는 유지한 채 API abstraction guard만 선택적으로 우회한다.
  - expert mode raw write는 로그에 명확히 남기고, read/write 실패는 기존 Success/Fail 및 typed Exception 계약으로 반환한다.
  - TD-032 같은 실장치 IO-Link ISDU 조사 절차에서 임시 probe script 없이 필요한 raw SDO 접근을 수행할 수 있다.
- 상세: [RF-016 기능 명세](tasks/rf/RF-016-hidden-expert-mode.md)

## Tech Debt

### TD-003 Axis Server 과거 명칭 잔존

- 상태: `complete`
- 우선순위: 보통
- 요약: 서버를 가리키는 과거 `Axis Server` 명칭을 `Motion Server`로 통일한다.
- 완료 조건:
  - 사용자 노출 로그, 문서, script와 packaging 명칭이 `Motion Server`로 통일된다.
  - 호환성을 위해 유지하는 식별자는 목록과 제거 정책이 문서화된다.
  - 전체 저장소 명칭 검사가 허용 목록 외의 과거 명칭을 발견하지 않는다.
- 상세: [TD-003 기술 명세](tasks/td/TD-003-axis-server-naming.md)

### TD-004 Backend Capability Fallback과 오래된 Servo Interface

- 상태: `complete`
- 우선순위: 보통
- 요약: backend와 device profile의 선택 기능을 명시적인 capability 계약으로 표현한다.
- 완료 조건:
  - 지원 capability와 필수 method가 명시적인 interface 또는 object로 정의된다.
  - MockMaster와 PySOEMMaster가 동일한 staged startup 필수 lifecycle 계약을 구현한다.
  - capability 판단을 위한 `hasattr()` fallback이 제거된다.
  - axis restart는 `AXIS_RESTART` capability와 request/clear-request 계약으로 일관되게 표현된다.
  - mock 전용 `Axis` wrapper와 실제 공통 계약이 아닌 `ServoInterface`가 제거된다.
  - 필수 capability 누락은 startup 단계에서 구체적인 오류로 검증된다.
  - mock과 PySOEM backend의 capability 계약 자동 테스트가 통과한다.
- 상세: [TD-004 기술 명세](tasks/td/TD-004-backend-capability.md)

### TD-005 예외 경계와 오류 형식 불균일

- 상태: `complete`
- 우선순위: 높음
- 요약: 계층별 오류 유형과 Motion Server API 오류 응답 형식을 통일한다.
- 완료 조건:
  - transport, protocol, validation과 runtime 오류 유형이 구분된다.
  - 오류 유형별 API failure code와 Fail 응답 형식이 문서화된다.
  - broad exception은 승인된 최상위 경계로 제한되고 허용 위치가 검사된다.
  - 대표 오류와 복구 가능 여부를 검증하는 자동 테스트가 통과한다.
- 상세: [TD-005 기술 명세](tasks/td/TD-005-error-boundary.md)

### TD-006 설정 로더와 Bus Parser 중복

- 상태: `complete`
- 우선순위: 보통
- 요약: 모든 실행 경로가 공통 설정 loader와 동일한 bus model을 사용하게 한다.
- 완료 조건:
  - Motion Server와 packaging이 공통 parser 및 bus model을 사용한다.
  - ROS의 독자적인 프로젝트 설정 및 bus parser가 제거되고, 공통 model 연동은 후속 작업으로 분리된다.
  - continuation, indexed entry와 `axis:`/`io:` bus 형식의 해석 결과가 적용 경로에서 같다.
  - 중복 `.env`/bus parser가 제거된다.
  - 정상·오류 설정 fixture 기반 자동 테스트가 통과한다.
- 상세: [TD-006 기술 명세](tasks/td/TD-006-config-loader.md)

### TD-007 Control Panel 중복 및 대형 모듈

- 상태: `complete`
- 우선순위: 보통
- 요약: Control Panel의 중복 변환 로직과 대형 GUI 모듈을 책임별로 분리한다.
- 완료 조건:
  - catalog 변환은 하나의 공통 utility와 테스트로 관리된다.
  - IO/ROS Panel이 connection, state, parameter tab과 view builder 책임으로 분리된다.
  - 기존 사용자 동작을 검증하는 panel smoke test 또는 동등한 자동 검증이 통과한다.
  - 공개 entrypoint와 packaging 실행 방식이 유지된다.
- 상세: [TD-007 기술 명세](tasks/td/TD-007-control-panel-modules.md)

### TD-008 Device 및 Runtime 책임이 큰 모듈

- 상태: `complete`
- 우선순위: 보통
- 요약: device와 runtime 대형 모듈을 lifecycle 책임별 컴포넌트로 분리한다.
- 완료 조건:
  - catalog/configuration, PRE_OP setup, runtime PDO, diagnostics와 recovery 책임 경계가 문서화된다.
  - 각 책임이 독립적인 interface와 모듈로 분리된다.
  - 기존 public 동작을 고정하는 mock 회귀 테스트가 통과한다.
  - CMMT와 CPX 실장치 smoke test 절차 및 결과가 기록된다.
- 상세: [TD-008 기술 명세](tasks/td/TD-008-device-runtime-responsibility.md)

### TD-009 API 문서와 구현 불일치

- 상태: `open`
- 우선순위: 높음
- 요약: 공개 API와 동작 설명이 구현에서 자동 검증되도록 한다.
- 완료 조건:
  - API specification, handler registry와 공개 문서의 command 목록이 일치한다.
  - 문서의 지원 여부, PDO 정책와 단위 설명이 현재 구현과 일치한다.
  - 문서 예제의 parse 또는 smoke test가 자동으로 실행된다.
  - CI가 API specification/handler/documentation 불일치를 실패로 검출한다.
- 상세: [TD-009 기술 명세](tasks/td/TD-009-api-documentation.md)

### TD-010 자동 테스트 부재

- 상태: `open`
- 우선순위: 높음
- 요약: mock 회귀 테스트와 별도의 실장치 smoke-test 체계를 구축한다.
- 완료 조건:
  - 설정, ESI/IODD, PDO codec, API와 virtual servo 핵심 경로의 자동 테스트가 제공된다.
  - mock 회귀 테스트가 clean environment의 CI에서 통과한다.
  - 실장치 시험은 별도 marker/profile과 실행 절차를 가진다.
  - 실패 시 대상 기능과 원인을 식별할 수 있는 테스트 보고가 생성된다.
- 상세: [TD-010 기술 명세](tasks/td/TD-010-automated-tests.md)

### TD-014 Import 시점 전역 설정 로딩

- 상태: `complete`
- 우선순위: 보통
- 요약: import side effect를 제거하고 immutable configuration을 runtime에 주입한다.
- 완료 조건:
  - project module import가 파일이나 환경변수를 읽거나 변경하지 않는다.
  - 명시적인 loader가 server, EtherCAT/cycle/DC, motion, logging 및 device instance의
    immutable typed configuration을 생성하고 검증한다.
  - `MotionServerApplication`은 composition root로만 사용되고 하위 component는 필요한
    typed projection만 명시적으로 주입받는다.
  - 실제/가상 backend가 동일한 device instance config를 사용하며 전역 device profile,
    active configuration과 장치 코드의 환경 변수 접근이 제거된다.
  - 공통 pre-logging on/off와 length, command log 제외 계약이 검증된다.
  - derived velocity와 설명용 configured index가 설정, state와 공개 API에서 제거된다.
  - 서로 다른 configuration 두 개가 같은 process에서 격리되고 Windows/Linux entrypoint
    smoke test 및 전체 회귀 테스트가 통과한다.
  - 서로 다른 설정을 같은 process에서 격리하는 자동 테스트가 통과한다.
- 상세: [TD-014 기술 명세](tasks/td/TD-014-import-time-config.md)

### TD-015 Virtual Servo Device Profile 기반 OD/PDO 구성 정리

- 상태: `complete`
- 우선순위: 보통
- 요약: Virtual Servo의 OD/PDO 구성을 선택된 device profile 계약에 연결한다.
- 완료 조건:
  - device profile이 required OD role과 PDO configuration registry를 제공한다.
  - Virtual Servo에서 CMMT 모듈에 대한 직접 의존이 제거된다.
  - 축별 PDO configuration의 명시적 선택, 기본값과 잘못된 설정 오류가 지원된다.
  - mock과 실축 profile의 OD/PDO 선택 정책을 비교하는 자동 테스트가 통과한다.
  - SDO와 PDO가 동일한 profile/ESI 기반 OD Model의 runtime value를 사용한다.
- 상세: [TD-015 기술 명세](tasks/td/TD-015-virtual-servo-profile.md)

### TD-016 MockMaster의 Device-specific SDO 처리

- 상태: `complete`
- 우선순위: 높음
- 요약: MockMaster에서 device-specific SDO 의미를 제거하고 virtual device에 위임한다.
- 완료 조건:
  - MockMaster는 generic SDO transport만 담당한다.
  - 각 virtual device가 object access interface를 구현한다.
  - device-specific OD/PDO mapping이 해당 device package에서 관리된다.
  - MockSlave가 OD Bridge를 통해 SDO와 PDO 접근을 동일한 OD Model에 위임한다.
  - 기존 virtual servo SDO/PDO 동작과 신규 virtual device 확장 테스트가 통과한다.
- 상세: [TD-016 기술 명세](tasks/td/TD-016-mock-master-sdo.md)

### TD-017 Motion Server API Layer 구조 정리

- 상태: `complete`
- 우선순위: 보통
- 요약: API protocol boundary와 기능별 handler의 책임을 분리한다.
- 완료 조건:
  - API 처리 흐름이 `decoder -> validator -> router -> handler -> encoder`로 정리된다.
  - `api`에는 protocol boundary만 남고 기능별 handler가 별도 package에 배치된다.
  - registry와 API specification mismatch가 startup 전에 검출된다.
  - 구조 변경 후 syntax 및 registry import 검증이 통과한다.
- 상세: [TD-017 완료 기록](tasks/td/TD-017-api-layer.md)

### TD-018 Runtime 생성 단계 Initialization Error 처리

- 상태: `complete`
- 우선순위: 높음
- 요약: runtime 생성 오류에서도 진단과 복구 API를 제공하는 degraded server를 유지한다.
- 완료 조건:
  - configuration/profile/catalog 검증 실패가 initialization-error 상태로 표현된다.
  - runtime 생성 실패 후에도 TCP server와 진단·reset·reconnect API가 응답한다.
  - API와 server log가 동일한 원인 식별자와 오류 메시지를 제공한다.
  - mock 단계별 오류 주입, reconnect/reset lifecycle과 대표 CPX 설정 오류 테스트가 통과한다.
- 상세: [TD-018 기술 명세](tasks/td/TD-018-runtime-initialization-error.md)

### TD-019 프로젝트·저장소 및 설치 경로 변경

- 상태: `complete`
- 우선순위: 보통
- 요약: `ROS2_CIA402/virtual_ethercat` 기반 프로젝트·저장소·설치 경로를 Motion Server 명칭으로 이관한다.
- 완료 조건:
  - GitHub repository, 로컬 workspace와 Linux 설치 경로의 목표 명칭이 결정 문서에 확정된다.
  - Windows/Linux script와 문서가 새 경로를 기본값으로 사용한다.
  - 기존 경로에서 새 경로로 이전하는 절차와 rollback 방법이 제공된다.
  - Windows와 Linux clean checkout 및 Linux Basic mode startup 검증이 새 경로에서 통과한다.
- 상세: [TD-019 기술 명세](tasks/td/TD-019-project-path-migration.md)

### TD-020 Legacy 실행 식별자 Migration

- 상태: `complete`
- 우선순위: 보통
- 요약: 과거 프로젝트명을 포함한 container, image와 service 식별자를 직접 변경한다.
- 완료 조건:
  - legacy 실행 식별자와 신규 식별자의 mapping 및 직접 migration 절차가 문서화된다.
  - Docker/systemd/환경변수에서 신규 식별자만 사용한다.
  - 기존 설치의 일회성 cleanup과 신규 Linux 설치가 검증된다.
  - ROS 전용 legacy 식별자는 RF-008 범위로 명확히 제외된다.
- 상세: [TD-020 기술 명세](tasks/td/TD-020-legacy-runtime-identifiers.md)

### TD-021 Windows 실행 스크립트의 PYTHONPATH 중복 및 진단 출력 정리

- 상태: `complete`
- 우선순위: 낮음
- 요약: Windows 실행 스크립트가 프로젝트 경로를 `PYTHONPATH`에 중복 추가하지 않고 실제 project root만 출력하게 한다.
- 완료 조건:
  - Motion Server, Axis Control Panel과 IO Control Panel script가 project root를 한 번만 추가한다.
  - 같은 PowerShell process에서 반복 실행해도 `PYTHONPATH` 항목이 증가하지 않는다.
  - 정상 실행 로그는 전체 `PYTHONPATH` 대신 `Project root: <path>`만 출력한다.
  - 기존 외부 `PYTHONPATH` 항목의 순서와 값이 보존되고 PowerShell 구문 및 실행 검사가 통과한다.
- 상세: [TD-021 기술 명세](tasks/td/TD-021-windows-pythonpath.md)

### TD-022 Motion Server 초기화 로그의 책임 및 조건부 출력 정리

- 상태: `complete`
- 우선순위: 낮음
- 요약: 서버 초기화 로그에는 실제 적용된 server/runtime 설정만 출력하고 축별 device 상태는 분리한다.
- 완료 조건:
  - 초기화 INFO 로그가 server/runtime 요약 필드만 포함한다.
  - DC와 CSP 세부 parameter는 해당 기능의 실제 활성 조건에서만 출력된다.
  - `statuswords`, software position limits와 actual positions가 서버 초기화 요약에서 제거된다.
  - backend, DC와 motion-mode 조합별 출력 테스트가 실제 적용 상태 및 필드 계약을 검증한다.
- 상세: [TD-022 기술 명세](tasks/td/TD-022-startup-log-boundary.md)

### TD-023 Virtual Servo OD 초기값의 Startup 덮어쓰기

- 상태: `complete`
- 우선순위: 보통
- 요약: 가상축 생성 직후 서버 motion limit 설정이 profile의 OD 초기값을 덮어쓰는 실축과의 비대칭을 제거한다.
- 완료 조건:
  - required non-PDO OD 존재 계약과 이름 있는 Non-PDO configuration이 분리된다.
  - slave별 Non-PDO configuration으로 가상축의 linear/rotary, 단위와 motion limit를 독립적으로 초기화한다.
  - Virtual Servo 생성 및 runtime reset 시 선택된 Non-PDO configuration이 적용된다.
  - 같은 configuration의 축은 공통값으로 초기화되고 writable OD만 SDO를 통해 축별 변경할 수 있다.
  - `MOTION_SERVER_MAX_VELOCITY`, `MOTION_SERVER_ACCELERATION`, `MOTION_SERVER_DECELERATION`과 대응 command-line option 및 fallback이 제거된다.
  - CSP jerk는 메인 설정의 `MOTION_SERVER_CSP_PROFILE` 다음 `MOTION_SERVER_CSP_JERK`와 `MotionConfig.csp_jerk`로 관리된다.
  - MotionController의 velocity, acceleration과 deceleration 제한은 device OD readback으로 구성된다.
  - profile/motion limit readback 실패는 장치 값을 덮어쓰지 않고 0 기반 안전 fallback으로 처리된다.
  - user position unit과 converting unit readback 실패도 잘못된 scale로 계속하지 않고 initialization error로 처리된다.
  - device OD parameter는 명시적인 설정 명령을 실행할 때만 변경된다.
  - mock과 실축 startup이 기존 device parameter를 동일하게 읽어 runtime 상태를 구성한다.
  - 서버 제어용 축 parameter는 단일 typed runtime cache에 보관되고 startup, 설정 변경과 reset 후 OD readback으로 동기화된다.
  - Non-PDO configuration validation, startup/reset 이후 값, readback 실패와 명시적 설정 변경을 검증하는 자동 테스트가 통과한다.
- 상세: [TD-023 기술 명세](tasks/td/TD-023-virtual-od-startup-defaults.md)

### TD-024 Axis Control Panel 초기 임시 연결 제거

- 상태: `complete`
- 우선순위: 높음
- 요약: Axis Control Panel의 일회성 연결을 제거하고 상시 연결의 첫 feedback으로 축 topology를 초기화한다.
- 완료 조건:
  - Control Panel 시작 시 `system/axes/status`를 위한 별도 임시 TCP 연결을 만들지 않는다.
  - 상시 연결의 첫 feedback 배열 길이로 축 수를 확정하고 로컬 설정/default로 축 이름을 만든다.
  - 축 수 확정 전에는 연결과 Server health를 표시하는 bootstrap 화면만 제공한다.
  - UI 생성 후 한 번 요청한 full status로 단위·설정·metadata를 보완한다.
  - 시작 과정에서 동일 status 요청과 client 연결이 중복되지 않는다.
  - 정상적인 Control Panel 시작·종료가 서버에서 connection reset 오류로 기록되지 않는다.
  - 연결 실패와 지연 feedback에서 임의의 1축 fallback을 확정하지 않는다.
  - UI 생성 후 축 수 변경은 동적으로 재구성하지 않고 Panel 재시작 필요 상태와 제어 제한으로 처리한다.
  - 정상·Bus 단절·초기화 실패 feedback과 bootstrap 회귀 자동 테스트가 통과한다.
- 상세: [TD-024 기술 명세](tasks/td/TD-024-axis-panel-bootstrap-connection.md)

### TD-025 Runtime Parameter Cache 관리 체계 확장

- 상태: `open`
- 우선순위: 보통
- 요약: TD-023의 CMMT 축 parameter cache를 장치 공통 refresh·validity·Diagnostic 체계로 확장한다.
- 완료 조건:
  - parameter definition, source, validity와 갱신 시각 모델이 확정된다.
  - 축/항목별 명시적 refresh와 일반 parameter write 후 cache 연동이 구현된다.
  - RF-005의 PySOEM Axis restart 완료 후 해당 축 cache refresh와 invalid 처리가 수행된다.
  - readback 실패, 외부 commissioning 변경과 다중 항목 갱신 정책이 정의된다.
  - CMMT 외 장치 확장 경계와 Diagnostic 연동 자동 테스트가 통과한다.
- 상세: [TD-025 기술 명세](tasks/td/TD-025-runtime-parameter-cache.md)

### TD-026 실장치 Identity 불일치의 초기화 오류 경계 정리

- 상태: `open`
- 우선순위: 보통
- 요약: 실제 slave identity와 설정 profile의 예상 가능한 불일치를 typed initialization failure로 분류하고 일반 traceback 노출을 제거한다.
- 완료 조건:
  - adapter 연결, topology/layout과 device identity 불일치의 안정적인 cause 경계가 결정된다.
  - 예상된 identity mismatch는 구조화된 초기화 실패로 보고되고 Python traceback을 출력하지 않는다.
  - 예상하지 못한 내부 exception만 최상위 초기화 경계에서 traceback을 한 번 기록한다.
  - 실패 후 불완전 runtime이나 가상축 없이 degraded server 상태·Diagnostic·복구 계약이 유지된다.
  - CMMT-AS/CMMT-ST mismatch와 정상 startup/reconnect 회귀 테스트가 통과한다.
- 상세: [TD-026 기술 명세](tasks/td/TD-026-device-identity-initialization-boundary.md)

### TD-027 Control Panel의 Motion Server 상태 및 Axis 오류 표시 보완

- 상태: `complete`
- 우선순위: 높음
- 요약: Axis/IO Control Panel에서 Motion Server의 runtime·Diagnostic 상태를 지속적으로 확인하고 Axis Panel Motion Tab에 선택 축의 오류 상세를 표시한다.
- 완료 조건:
  - Axis 및 IO Control Panel이 TCP 연결 상태와 별도로 Server initialized/runtime/Diagnostic 상태를 표시한다.
  - initialization-error, bus-disconnected, fault와 normal 전환이 두 Panel에 지연 없이 일관되게 반영된다.
  - Axis Panel Motion Tab의 `Error` 항목이 선택 축의 활성 Fault/Alarm과 Drive 오류 상세를 표시한다.
  - 오류 해제·fault-reset·reconnect 후 낡은 오류 표시가 남지 않고 정상 상태로 복귀한다.
  - 정상, Axis Fault, Bus 단절, Initialization Error 및 재연결 UI 갱신 자동 테스트가 통과한다.
- 상세: [TD-027 기술 명세](tasks/td/TD-027-control-panel-status-diagnostics.md)

### TD-028 Virtual OD Bridge의 장치 시퀀스 책임 제거

- 상태: `complete`
- 우선순위: 높음
- 요약: Virtual OD Bridge에서 Servo reset/save 의미를 제거하고 실축과 동일한 Motion Server
  시퀀스와 Virtual Device 내부 반응을 분리한다.
- 완료 조건:
  - `VirtualOdBridge`는 OD access, SDO 변환과 PDO 동기화만 담당한다.
  - Bridge에서 device reset, parameter save와 Servo 전용 role 분기가 제거된다.
  - Motion Server와 DeviceProfile의 restart/save 시퀀스는 Mock/PySOEM backend에서 동일하게 유지된다.
  - Virtual Servo는 명령 OD write에 대한 장치 내부 반응만 담당한다.
  - `MockSlave`는 장치 의미를 해석하지 않는다.
  - Bridge 단독 접근에는 side effect가 없고 Model_Update 경로에서는 기존 virtual device 동작이
    유지되는 자동 테스트가 통과한다.
- 상세: [TD-028 기술 명세](tasks/td/TD-028-virtual-od-bridge-boundary.md)

### TD-029 Virtual OD Bridge의 PDO/SDO-OD 연결 복원

- 상태: `complete`
- 우선순위: 높음
- 요약: SDO 직접 주소와 `PDO_Configuration` mapping을 공통 Virtual OD Bridge에서 하나의
  OD Model에 연결하고 Virtual Device를 PDO 객체로부터 분리한다.
- 완료 조건:
  - SDO는 요청의 index/sub-index로 OD Model을 직접 read/write한다.
  - PDO는 선택된 `PDO_Configuration`을 mapping 단일 원본으로 사용한다.
  - Mock/PySOEM Master의 공통 MasterPdoRuntime이 DeviceProfile PdoCodec으로 PDO 객체와 raw
    payload를 변환한다.
  - raw RxPDO payload-to-OD와 OD-to-raw TxPDO payload 연결은 공통 Bridge가 담당한다.
  - Virtual Device는 PDO 객체나 OD write callback이 아니라 Model_Update 시점의 OD 상태에만
    반응한다.
  - MockSlave는 장치별 구현과 role 의미에 의존하지 않는다.
  - SDO/PDO 공유 OD 값, cycle 순서와 reset/save 회귀 자동 테스트가 통과한다.
- 상세: [TD-029 기술 명세](tasks/td/TD-029-virtual-od-bridge-pdo-sdo-routing.md)

### TD-030 Mock/실축 PDO 직렬화 책임 비대칭

- 상태: `complete`
- 우선순위: 높음
- 요약: Mock/PySOEM 모두 Master 측에서 PDO를 직렬화하고 같은 prepare/send/receive cycle 계약을
  사용하도록 책임을 대칭화한다.
- 후속 작업: `RF-001`
- 완료 조건:
  - MockMaster와 PySOEMMaster가 공통 MasterPdoRuntime에서 RxPDO encode와 TxPDO decode를 수행한다.
  - `prepare`에서 output을 생성하고 `send`에서 snapshot을 확정하며 `receive`에서 input을 decode한다.
  - MockSlave는 raw PDO/SDO endpoint만 담당하고 RxPDO/TxPDO 객체와 PdoCodec을 소유하지 않는다.
  - VirtualOdBridge와 Virtual Device의 TD-029 책임 경계가 유지된다.
  - lifecycle, snapshot, 다중 slave, WKC와 timing field의 backend parity test가 통과한다.
  - Mock CMMT도 PRE-OP에서 기존 DeviceProfile sequence로 PDO assignment/mapping을 SDO write하고
    readback을 검증한 뒤 실제 mapping을 MasterPdoRuntime에 적용한다.
  - `DEC-034`, TD-029와 RF-001 문서가 최종 책임 구조와 일치한다.
- 상세: [TD-030 기술 명세](tasks/td/TD-030-mock-pdo-transport-parity.md)

### TD-031 Bus 단절 중 장치 조회 차단 및 요청 오류 격리

- 상태: `open`
- 우선순위: 높음
- 요약: Bus 단절 중 장치 통신이 필요한 조회를 차단하고 요청 오류가 서버 전체 중단으로 이어지지 않도록 예외 경계를 정리한다.
- 완료 조건:
  - 단절 중 AP/IOL/EtherCAT 장치 접근 조회가 SDO 호출 전에 기존 Fail로 거부되고 상태/Feedback/recovery는 유지된다.
  - 조회 검증 이후 transport가 닫혀도 통신 Fail로 처리되며 일반 RuntimeError로 오분류하지 않는다.
  - malformed request와 client 오류가 listener/다른 client를 종료하지 않고 normal/disconnected/degraded loop 회귀가 통과한다.
  - 동일 TCP의 후속 상태 조회와 reconnect 후 파라미터 조회를 검증하고, 실제 다운 신고와 최초 단절 원인의 확인/미확인 근거를 기록한다.
- 상세: [TD-031 기술 명세](tasks/td/TD-031-disconnected-request-isolation.md)

### TD-032 CPX IO-Link ISDU Parameter Read/Write 실패

- 상태: `open`
- 우선순위: 높음
- 요약: CPX-AP-I-EC 펌웨어 업데이트 이후 IO-Link ISDU Access object가
  `0x2001 + module_slot * module_index_stride` 규칙으로 접근 가능함을 확인했다. 예:
  `MOTION_SERVER_IO_io0_MODULE_PDO_INDEX_STRIDE=0x0010`이고 IOL module이 slot 1이면
  `0x2011`.
- 완료 조건:
  - 공개 `system/io/iol/param_read`와 `system/io/iol/param_write`가 configured module stride를
    반영한 ISDU Access object를 사용한다.
  - `system/io/iol/param_catalog`가 같은 object index를 표시한다.
  - IO-Link process data decoding과 CPX module parameter read/write는 계속 사용할 수 있다.
  - 대표 실장치 port에서 read smoke test가 성공하고, write 가능한 parameter 또는 read-only write
    rejection이 확인된다.
- 상세: [TD-032 기술 명세](tasks/td/TD-032-cpx-iol-isdu-parameter-access.md)

### TD-033 CPX EtherCAT Parameter Catalog 응답 일관화

- 상태: `complete`
- 우선순위: 보통
- 요약: CPX EC Parameter catalog가 AP module object 중심으로 응답하여 EtherCAT general object,
  identity, diagnosis history, sync/PDO assignment 같은 CPX-AP-I-EC 본체 OD가 catalog에 표시되지 않는다.
- 완료 조건:
  - `system/io/ethercat/param_catalog`가 설정된 CPX station의 station-level object를 반환한다.
  - `module` 또는 `slot` selector가 들어오면 `INVALID_ARGUMENT`로 거부한다.
  - catalog 응답에서 `station`, `identity`, `diagnosis`, `sync`, `pdo_mapping` 등 사용자가 구분할 수 있는
    `scope`/`group` 정보를 제공한다.
  - `ro p`는 `access: "ro"`로 표시하며 PDO mapping 구성용 `pdo_mapping` 필드는 추가하지 않는다.
  - `0x1000`, `0x1001`, `0x1018`, `0x10F1`, `0x10F3`, `0x10F8`, `0x1600...`,
    `0x1A00...`, `0x1C12...`, `0x1C13`, `0x1C32...` 계열 대표 object가 catalog에 노출된다.
  - IO Control Panel EC Parameter 탭에서 CPX 본체 EtherCAT parameter와 AP module parameter가 섞이지 않는다.
- 상세: [TD-033 기술 명세](tasks/td/TD-033-ec-parameter-catalog-scope.md)
