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
- 요약: 실장치와 동일한 설정 및 API로 시험할 수 있는 CPX-AP-I-EC Virtual I/O를 제공한다.
- 완료 조건:
  - DI/DO/AI/AO/IO-Link process image와 AP module layout이 설정대로 생성된다.
  - SDO, AP parameter와 IO-Link ISDU read/write가 실장치와 동일한 공개 API로 동작한다.
  - Motion Server와 IO Control Panel의 virtual I/O 회귀 테스트가 통과한다.
  - 실장치 profile과 virtual profile의 지원 범위 및 차이가 문서화된다.
- 상세: [RF-001 기능 명세](tasks/rf/RF-001-cpx-virtual-io.md)

### RF-002 Low-code Reference Client

- 상태: `planned`
- 우선순위: 높음
- 요약: 패널 없이 Motion Server API를 사용할 수 있는 Node-RED 및 Python reference client를 제공한다.
- 완료 조건:
  - JSON-lines 연결, 재연결과 request/response correlation이 구현된다.
  - authority, feedback, axis motion, I/O output과 parameter access 예제가 제공된다.
  - Node-RED flow와 Python client가 동일한 Basic mode 시나리오를 완료한다.
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

- 상태: `planned`
- 우선순위: 보통
- 요약: runtime fault state와 reset/reconnect/restart 복구 모델을 완성한다.
- 완료 조건:
  - 정상, initialization-error, bus-disconnected와 recoverable-fault 상태 및 전이가 명세된다.
  - server reset, bus reconnect와 process restart의 책임 및 허용 조건이 구현된다.
  - runtime 재구성 시 authority와 client notification 정책이 일관되게 적용된다.
  - mock 오류 주입과 대표 실장치 복구 시나리오가 모두 통과한다.
- 상세: [RF-005 기능 명세](tasks/rf/RF-005-runtime-recovery.md)

### RF-006 배포 구성 최종 검증

- 상태: `planned`
- 우선순위: 보통
- 요약: Windows package와 Linux Docker 배포 구성을 clean system에서 최종 검증한다.
- 완료 조건:
  - Windows package의 server, panel, tools, manual과 catalog 구성이 정의대로 포함된다.
  - Linux `.env`와 Windows `config.txt`의 지원 설정 및 기본값 차이가 문서화된다.
  - ESI/IODD 포함, 검색과 version 선택 규칙이 두 환경에서 검증된다.
  - 새 Windows/Linux PC에서 Basic mode 설치 및 smoke-test 절차가 그대로 재현된다.
- 상세: [RF-006 기능 명세](tasks/rf/RF-006-deployment-validation.md)

### RF-007 CMMT ESI/PDO 실장치 검증 확대

- 상태: `in_progress`
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

- 상태: `open`
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

- 상태: `open`
- 우선순위: 높음
- 요약: 계층별 오류 유형과 Motion Server API 오류 응답 형식을 통일한다.
- 완료 조건:
  - transport, protocol, validation과 runtime 오류 유형이 구분된다.
  - 오류 유형별 API error code와 응답 형식이 문서화된다.
  - broad exception은 승인된 최상위 경계로 제한되고 허용 위치가 검사된다.
  - 대표 오류와 복구 가능 여부를 검증하는 자동 테스트가 통과한다.
- 상세: [TD-005 기술 명세](tasks/td/TD-005-error-boundary.md)

### TD-006 설정 로더와 Bus Parser 중복

- 상태: `open`
- 우선순위: 보통
- 요약: 모든 실행 경로가 공통 설정 loader와 동일한 bus model을 사용하게 한다.
- 완료 조건:
  - Motion Server, ROS, packaging과 panel이 공통 parser를 사용한다.
  - continuation, indexed entry와 `axis:`/`io:` bus 형식의 해석 결과가 모든 경로에서 같다.
  - 중복 `.env`/bus parser가 제거된다.
  - 정상·오류 설정 fixture 기반 자동 테스트가 통과한다.
- 상세: [TD-006 기술 명세](tasks/td/TD-006-config-loader.md)

### TD-007 Control Panel 중복 및 대형 모듈

- 상태: `open`
- 우선순위: 보통
- 요약: Control Panel의 중복 변환 로직과 대형 GUI 모듈을 책임별로 분리한다.
- 완료 조건:
  - catalog 변환은 하나의 공통 utility와 테스트로 관리된다.
  - IO/ROS Panel이 connection, state, parameter tab과 view builder 책임으로 분리된다.
  - 기존 사용자 동작을 검증하는 panel smoke test 또는 동등한 자동 검증이 통과한다.
  - 공개 entrypoint와 packaging 실행 방식이 유지된다.
- 상세: [TD-007 기술 명세](tasks/td/TD-007-control-panel-modules.md)

### TD-008 Device 및 Runtime 책임이 큰 모듈

- 상태: `open`
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

- 상태: `open`
- 우선순위: 보통
- 요약: import side effect를 제거하고 immutable configuration을 runtime에 주입한다.
- 완료 조건:
  - project module import가 파일이나 환경변수를 읽거나 변경하지 않는다.
  - 명시적인 loader가 immutable configuration object를 생성한다.
  - server, packaging과 테스트가 configuration dependency를 명시적으로 주입한다.
  - 서로 다른 설정을 같은 process에서 격리하는 자동 테스트가 통과한다.
- 상세: [TD-014 기술 명세](tasks/td/TD-014-import-time-config.md)

### TD-015 Virtual Servo Device Profile 기반 OD/PDO 구성 정리

- 상태: `open`
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

- 상태: `open`
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

- 상태: `open`
- 우선순위: 높음
- 요약: runtime 생성 오류에서도 진단과 복구 API를 제공하는 degraded server를 유지한다.
- 완료 조건:
  - configuration/profile/catalog 검증 실패가 initialization-error 상태로 표현된다.
  - runtime 생성 실패 후에도 TCP server와 진단·reset·reconnect API가 응답한다.
  - API와 server log가 동일한 원인 식별자와 오류 메시지를 제공한다.
  - mock 오류 주입과 대표 CPX 설정 오류의 자동 복구 테스트가 통과한다.
- 상세: [TD-018 기술 명세](tasks/td/TD-018-runtime-initialization-error.md)

### TD-019 프로젝트·저장소 및 설치 경로 변경

- 상태: `open`
- 우선순위: 보통
- 요약: `ROS2_CIA402/virtual_ethercat` 기반 프로젝트·저장소·설치 경로를 Motion Server 명칭으로 이관한다.
- 완료 조건:
  - GitHub repository, 로컬 workspace와 Linux 설치 경로의 목표 명칭이 결정 문서에 확정된다.
  - Windows/Linux script와 문서가 새 경로를 기본값으로 사용한다.
  - 기존 경로에서 새 경로로 이전하는 절차와 rollback 방법이 제공된다.
  - clean checkout, Windows-to-Linux sync와 Basic mode startup 검증이 새 경로에서 통과한다.
- 상세: [TD-019 기술 명세](tasks/td/TD-019-project-path-migration.md)

### TD-020 Legacy 실행 식별자 Migration

- 상태: `open`
- 우선순위: 보통
- 요약: 과거 프로젝트명을 포함한 container, image, service와 환경변수 식별자를 단계적으로 변경한다.
- 완료 조건:
  - legacy 실행 식별자와 신규 식별자의 mapping, 호환 기간과 제거 version이 문서화된다.
  - Docker/systemd/환경변수에서 신규 식별자를 기본값으로 사용하고 legacy 입력을 명시적으로 지원한다.
  - 기존 설치의 upgrade, 신규 설치와 rollback scenario가 Windows/Linux에서 검증된다.
  - 호환 기간 종료 후 제거할 fallback이 코드와 문서에서 추적 가능하다.
- 상세: [TD-020 기술 명세](tasks/td/TD-020-legacy-runtime-identifiers.md)

### TD-021 Windows 실행 스크립트의 PYTHONPATH 중복 및 진단 출력 정리

- 상태: `open`
- 우선순위: 낮음
- 요약: Windows 실행 스크립트가 프로젝트 경로를 `PYTHONPATH`에 중복 추가하지 않고 실제 project root만 출력하게 한다.
- 완료 조건:
  - Motion Server, Axis Control Panel과 IO Control Panel script가 project root를 한 번만 추가한다.
  - 같은 PowerShell process에서 반복 실행해도 `PYTHONPATH` 항목이 증가하지 않는다.
  - 정상 실행 로그는 전체 `PYTHONPATH` 대신 `Project root: <path>`만 출력한다.
  - 기존 외부 `PYTHONPATH` 항목의 순서와 값이 보존되고 PowerShell 구문 및 실행 검사가 통과한다.
- 상세: [TD-021 기술 명세](tasks/td/TD-021-windows-pythonpath.md)

### TD-022 Motion Server 초기화 로그의 책임 및 조건부 출력 정리

- 상태: `open`
- 우선순위: 낮음
- 요약: 서버 초기화 로그에는 실제 적용된 server/runtime 설정만 출력하고 축별 device 상태는 분리한다.
- 완료 조건:
  - 초기화 INFO 로그가 server/runtime 요약 필드만 포함한다.
  - DC와 CSP 세부 parameter는 해당 기능의 실제 활성 조건에서만 출력된다.
  - `statuswords`, software position limits와 actual positions가 서버 초기화 요약에서 제거된다.
  - backend, DC와 motion-mode 조합별 출력 테스트가 실제 적용 상태 및 필드 계약을 검증한다.
- 상세: [TD-022 기술 명세](tasks/td/TD-022-startup-log-boundary.md)
