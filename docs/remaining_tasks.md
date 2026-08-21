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

- 상태: `open`
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
  - capability 판단을 위한 `hasattr()` fallback이 제거된다.
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
- 상세: [TD-015 기술 명세](tasks/td/TD-015-virtual-servo-profile.md)

### TD-016 MockMaster의 Device-specific SDO 처리

- 상태: `open`
- 우선순위: 높음
- 요약: MockMaster에서 device-specific SDO 의미를 제거하고 virtual device에 위임한다.
- 완료 조건:
  - MockMaster는 generic SDO transport만 담당한다.
  - 각 virtual device가 object access interface를 구현한다.
  - device-specific OD/PDO mapping이 해당 device package에서 관리된다.
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
