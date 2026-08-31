# Work Log

이 문서는 현재 Git 이력과 대화 맥락에서 파악 가능한 범위의 작업 기록이다.
날짜는 기본적으로 Git commit 날짜를 기준으로 정리했고, 아직 commit되지 않은 작업은 현재 작업일 기준으로 별도 기록한다.
미완료 기능과 기술 부채는 [Remaining Tasks](remaining_tasks.md)에서 별도로 관리한다.

## 2026-08-31

### TD-032 CPX IO-Link ISDU Parameter Read/Write 실패 등록

- 실장치 CPX-AP-I-4IOL-M12에서 IO-Link process value는 확인되지만
  `system/io/iol/param_read/write`가 ISDU gateway의 port 선택 단계에서 거부되는 문제를
  TD-032로 등록했다.
- 현재 실패 지점은 `0x2001:02 = 1` SDO write이며, API Fail detail에
  `isdu_step=write port`, `sdo_index=0x2001`, `sdo_subindex=2`, `sdo_value=1`,
  device abort `0x06090030`이 기록되었다.
- 사용자 확인에 따라 센서는 두 번째 물리 포트에 연결되어 있고 `port=1`은 0-base 채널 번호로
  유지한다. process value가 확인되므로 포트 비활성 가설은 낮추고, acyclic ISDU gateway
  sequence와 port의 ISDU service 상태를 별도로 검증하기로 했다.
- 웹 검색으로 Festo CPX-FB36 ISDU Access Object, ifm EtherCAT IO-Link acyclic command와
  Beckhoff IO-Link parameter access 설명을 확인했다. CPX-AP-I-EC의 `0x2001` SDO write 순서는
  직접 확정되지 않았으므로 TD-032에서 ESI/문서/실장치 단계별 검증으로 확정한다.

### IO-Link ISDU gateway 주소 계산 수정

- 실장치 읽기 진단 결과와 사용자 승인에 따라 IO-Link ISDU access object 계산을 module 1
  `0x2001`, module 2 `0x2011` 기준으로 수정했다.
- 실제 request handler, parameter catalog 응답, Virtual CPX gateway dispatch와 Virtual CPX
  ISDU OD 생성 규칙을 같은 기준으로 맞췄다.

### IO-Link gateway 실장치 읽기 진단 완료

- 사용자가 현재 축 상태에서 진행을 승인하고 제어권을 해제한 뒤, 기존 API로 authority를 얻어
  server/restart를 수행했다. PID 14184 → 6172, 15000 listener 재기동을 확인했다.
- 동일 Master의 io0/slave 1에서 `0x2001:02` uint8 read는 값 0으로 성공,
  `0x2021:02` read는 원래 SDO Abort `0x06020000`으로 실패했다.
- 결과는 `.runtime/iol-gateway-probe-result.json`과 `docs/diagnostic/iol_gateway_probe.md`에 기록했다.
  probe 자체는 OD read만 수행했으며 재시작의 기존 device initialization 외에 gateway write나
  센서 ISDU 실행은 하지 않았다. 실제 gateway 주소 계산 변경은 별도 판단으로 남겼다.
- 실행 marker가 소비된 것을 확인하고 server.py의 임시 startup hook을 제거했다.

### IO-Link gateway 일회성 읽기 진단 준비

- 사용자 승인에 따라 기존 Master로 `io0`의 `0x2001:02`, `0x2021:02`만 읽는 임시 진단을
  `scripts/diagnostics/iol_gateway_probe.py`에 추가했다. 일반 EC API 차단은 유지하며
  marker가 있어야 startup에서 한 번 실행한다. 원래 SDO Abort code를 원인 체인에서 기록한다.
- `tests/test_iol_gateway_probe.py` 3개 포함 전체 unittest 377개 및 whitespace 검사 통과.
  테스트 출력의 성공 값은 fake 응답이며 실장치 결과가 아니다.
- 실제 서버 사전 조회에서 Axis 0이 Enable(statusword 0x8637), client 1이 authority 보유 상태였다.
  축 Disable/제어권 해제를 요청했으며 marker 생성과 서버 재시작, 실제 probe는 아직 수행하지 않았다.
- 진단 범위/제약은 `docs/diagnostic/iol_gateway_probe.md`에 기록했다. 완료 후 임시 startup hook을
  제거하며, 실장치 검증 전 gateway 주소를 수정하지 않는다.

### TD-031 Bus 단절 중 장치 조회 및 서버 오류 격리 등록

- 사용자가 AP parameter 20071 읽기 중 RuntimeError traceback과 서버 다운 증상을 보고하여
  status 분류의 transport gating 누락, 미연결 PySOEM SDO의 일반 RuntimeError와 client 오류
  경계를 조사하고 TD-031을 `open`/높음으로 등록했다.
- 오프라인 재현에서 AP 요청의 RuntimeError는 router가 잡아 INTERNAL_FAILURE Fail로 반환했다.
  해당 traceback만으로 실제 프로세스 종료를 확정하지 않았다. 조사 시점에는 PID 14184와
  15000 listener가 존재했지만 이전 재기동 여부/당시 응답성/최초 단절 원인은 미확정으로 남겼다.
- 별도로 JSONDecodeError가 disconnected loop의 OSError-only 경계 밖으로 전파되는
  실제 종료 가능 경로를 재현했다. 이번 AP 요청이 malformed JSON이었다는 의미는 아니다.
- 상세 TD에 원인별 근거, 수정 순서, API/transport/client 경계와 회귀 완료 조건을 기록했다.
  구현 코드 수정, 실장치 접근/설정 변경과 commit/push는 수행하지 않았다.

### RF-015 IO-Link Feedback 디코딩 구현 완료

- 사용자 합의에 따라 DEC-038과 RF-015/API 문서에 포트별 raw/qualifier/decoded 및
  `ok`/`not_configured`/`unsupported`/`invalid_data` 계약을 확정했다.
- `iodd_process_data.py`에서 IODD 기본 숫자/Boolean/flat Record/DatatypeRef와 고정 scale/offset을
  immutable metadata로 준비하고 `process_data.py`가 공통 디코딩한다. 이름/단위는 IODD 및
  공식 표를 사용하고 미지원 구조나 단위를 센서 이름으로 추정하지 않는다.
- `encoder.py`의 input channel을 확장하고 별도 qualifier 배열을 제거했다. feedback/status/
  input-read/output-write snapshot에 공통 process-data 유효성을 전달하여 Bus 단절 시 stale
  값을 정상 측정값으로 보내지 않는다. raw와 output 계약, Virtual Device/Master 경계는 유지했다.
- `tests/test_io_link_decoding.py` 16개와 전체 unittest 374개, whitespace 검사 통과.
  독립 big-endian IEEE754 fixture, 상태 bit/단위, invalid/unsupported, 포트·module·station 격리,
  실장치용 codec과 mock injection parity, XML 재파싱 없음, 조회 API 정합성을 검증했다.
- 4-port snapshot+decode+JSON 로컬 측정 약 0.15ms, UTF-8 14,306 bytes. 동일 fixture에
  5ms/32KiB 회귀 기준을 추가했다. 실센서 대조, 대규모 부하 및 EXE 재빌드는 하지 않았다.
- `.env` 변경, 실장치 mode/ISDU 쓰기, 신규 Dashboard와 commit/push는 하지 않았다.

### RF-015 IO-Link Feedback 디코딩 등록

- 포트별 raw 데이터와 qualifier에 선택된 IODD profile의 측정값·단위·상태 bit를 추가하는
  RF-015를 `planned`로 등록했다. 숫자 profile, 필드 식별자, bit offset과 무효 데이터 처리
  제안 및 구현 전 미확정 사항을 상세 명세에 기록했다.
- IODD metadata → decoder → API encoder 책임 경계를 정리했다. 이번 변경은 문서 등록만이며
  runtime 코드와 Feedback 응답은 변경하지 않았다.

### IO-Link process data profile 선택

- `MOTION_SERVER_IO_<io>_IOL_PORTS`에 선택적 세 번째 항목을 추가했다. 사용자 결정에 따라
  이름 기반 선택을 제거하고 IODD `Condition value`의 숫자로 선택하도록 변경했다.
  생략 시 IODD 문서 순서의 첫 profile을 선택하고 typed config → 포트 binding → module 크기
  산정 및 parameter catalog까지 동일한 선택을 전달한다. 기존 `.env` 값은 변경하지 않았다.
- ESI 이름/ident로 선언한 IO-Link module도 port binding을 인식하도록 보완하고, 알 수 없는
  profile 및 module 용량 초과를 거부한다. 실제 장치 mode 자동 쓰기는 구현하지 않았다.
- 신규 테스트는 두 형식, 문서 순서 기본 선택, 크기가 다른 profile, 포트 간 선택 독립성,
  잘못된 설정, typed config 전달, catalog와 bundled Balluff IODD를 검증한다.
- 숫자는 목록 순번이 아니다. Balluff `:2`는 `P_Vibration_Accel`, `:240`은 `P_Custom_Profile`을
  선택하며, catalog는 숫자와 IODD 이름을 각각 보고한다. 실장치 검증 및 Windows EXE 재빌드는
  수행하지 않았다.
- 숫자 선택 회귀 13개를 포함한 전체 unittest 358개와 whitespace 검사가 통과했다.

### CPX PDO 크기 회귀 수정

- 가상 CPX 도입 후 공통 PDO 크기 계산이 실장치에도 fixed block 크기를 강제하고, 기존 station
  출력 1바이트가 Variant 32의 128바이트 출력을 256바이트로 올리는 원인을 수정했다.
- station 크기를 ESI에 맞추고, PRE-OP에서 module/static ESI mapping을 readback 객체, 순서,
  bit 길이 및 padding과 대조한 뒤 실제 PDO 길이로 Master buffer를 확정한다. 임의 크기 허용이나
  검증 생략, 공개 API 및 가상 OD 모델 변경은 하지 않았다.
- 독립 Variant 32 fixture, IODD 자동 크기 산정 및 실패 경로를 포함한 신규 10개 회귀 테스트와
  기존 테스트를 합쳐 341개가 통과했다. 실장치 구동 검증은 수행하지 않았다.
- Windows Server/Panel 실행 파일을 재빌드하고, frozen Server를 mock CMMT 1축 + IODD 자동
  산정 Variant 32 구성으로 실행하여 runtime `normal`과 TCP status 응답을 확인했다.
  `dist/Motion Server`를 교체하면서 기존 config.txt 3개의 해시 일치를 확인했다.
  이전 패키지는 `backup/Motion Server-before-cpx-pdo-20260831-165836`에 보존했으며
  배포용 압축 파일은 생성하지 않았다.

## 2026-08-28

### Node-RED Sample Motion Sequence

- `05 Sample Motion Sequence`를 전용 Sequence node 없이 기존 Motion Server Request/Feedback node와
  표준 Node-RED Function node의 조합으로 추가했다. 각 이동 명령, feedback 완료 gate, DO/AO 출력과
  DI/AI 조건이 Flow에 독립적으로 노출되어 예제값을 직접 변경할 수 있다.
- 임의 4축 sequence는 2축 이동 → 다른 2축 이동 → 외부 출력 → 외부 입력 조건 대기 → 3축 이동 →
  마지막 1축 이동 순서이며, Stop은 기존 `system/axes/stop` API를 사용한다. import/deploy만으로는
  명령을 실행하지 않는다.

## 2026-08-27

### RF-002 구현 완료

- `02 Axis Control` Dashboard에 데스크톱 Axis Control Panel과 동일한 선택 축 Profile parameters,
  Motion Limits와 Software Position Limits 설정 영역을 추가했다. 현재값과 단위는 axis status로
  초기화하고 command authority 보유 시에만 적용하며, 성공 후 status readback으로 다시 동기화한다.
  위치·속도·활성 목표 표시와 status에서 읽은 세 설정 영역의 실수는 소수점 둘째 자리까지 반올림해
  표시하며 제어 및 chart 원본 데이터는 변경하지 않는다.
- `04 Virtual I/O Simulation`을 Inject 예제에서 전용 Dashboard로 전환했다. 공유 연결 상태와 API
  availability를 표시하고 Mock CPX station/module 선택, DI/AI/IO-Link 입력 주입, module/station reset,
  현재 virtual input 상태 확인을 한 화면에서 제공한다.
- CMMT Axis Parameter Catalog JSON이 약 1.14~1.23 MB로 기존 client output buffer 상한 1 MB를
  초과하여 정상 요청의 연결이 종료되던 문제를 수정했다. 느린 client에 대한 누적 방어는 유지하면서
  정상 catalog 응답을 수용하도록 명시적인 상한을 4 MB로 조정하고 경계 테스트를 추가했다.
- Node-RED Dashboard가 Connection Status node의 초기/change-only 알림을 놓치면 실제 TCP socket은
  연결되어 있어도 미연결로 표시되던 문제를 수정했다. 정상적인 `system/feedback` 수신도 현재 연결의
  확정 근거로 사용하고, socket close/error 및 명시적 Disconnect는 미연결의 확정 근거로 유지한다.
- `01` Dashboard를 기존 Control Panel 상단과 유사한 compact server control bar로 재구성했다.
  Authority toggle, Bus Reconnect, Server Fault Reset, Server Restart, Host/Port, Connect/Disconnect,
  연결 상태와 feedback 기반 Motion Server Status 요약을 한 영역에 통합했다.
- 공통 Flow 통합으로 비어 있던 02번부터 기능 Flow 번호를 연속 배치했다. 최종 구성은 Axis Control 02,
  I/O Control 03, Virtual I/O Simulation 04다.
- `03 I/O Control`을 기존 I/O Control Panel과 유사한 Dashboard로 확장했다. I/O device/module 상태,
  Raw Image, Digital Output, EC/AP/IO-Link catalog와 parameter read/write를 제공하며 Virtual Input
  Simulation 명령은 제외하여 `04 Virtual I/O Simulation`과 책임을 분리했다.
- 별도 Parameter Access Flow를 제거했다. Axis parameter catalog/read/write/save는 `02 Axis Control`로,
  I/O EC/AP/IO-Link parameter는 `03 I/O Control`로 통합하고 Virtual I/O Simulation은 04번으로 변경했다.
- Windows non-blocking socket의 `WSAEWOULDBLOCK(10035)`을 연결 단절로 오인하지 않도록 수신 대기와
  송신 backpressure를 분리했다. 송신 데이터는 client별 buffer에 보존하고 부분 전송을 다음 server
  cycle에 이어서 처리한다.
- Axis Dashboard를 데스크톱 Axis Control Panel의 단일 축 화면과 유사하게 확장했다. 첫 feedback의
  축 수로 선택 목록을 제한하고 16-bit Statusword Lamp/CiA402 상태, 현재·목표 위치, 현재 속도,
  목표 위치와 Profile Velocity 입력을 표시한다. Enable, Disable, Run, Stop, Homing, Fault Reset,
  Refresh 및 누르는 동안만 동작하는 Jog −/+를 기존 Axis API에 연결했다. 위치·속도 graph는 선택한
  축만 표시하고 축 선택 변경 시 이전 축의 graph 이력을 초기화한다.
  Jog는 버튼 release, pointer leave와 pointer cancel에서 모두 정지하도록 구성했다.
  Target Position과 Profile Velocity 입력값은 feedback의 임시값이나 고정 fallback을 사용하지 않고
  선택 축의 `system/axis/status` 응답만 반영하도록 책임을 분리했다.
- connection/status와 authority Flow를 하나의 공통 Flow로 통합하고 IP/Port, Connect/Disconnect,
  Request/Release Authority, 연결 및 authority 상태를 표시하는 FlowFuse Dashboard를 추가했다.
  Connection Control node를 추가하여 수동 Disconnect 후에는 다음 Connect까지 자동 재연결을 중지한다.
  공통 Flow가 Dashboard Base/Theme을 소유하고 Axis Flow가 이를 재사용하도록 정리했으며 Node-RED
  자동 테스트 7개를 통과했다.
- Axis example Flow에 명시적인 FlowFuse Dashboard Theme을 추가하고 Page가 Base와 Theme,
  Group이 Page, Chart가 Group을 참조하는 전체 구성 관계를 자동 테스트로 고정했다.
- 독립 `reference_clients` 아래에 재사용 가능한 최소 Python client와 Node-RED package를 구현했다.
  Python client는 thread-safe correlation, raw Success/Fail 반환, bounded feedback queue, timeout,
  disconnect pending 실패, 1초 재연결과 authority 비복원 계약을 제공한다.
- Node-RED에는 Connection Config, Connection Control, Request, Feedback, Connection Status 5종의
  공통 node를 구현했다. `01` connection/authority는 공통 기반 Flow로, `02`~`04`
  Axis/I/O/parameter/Virtual I/O는 기능 Scenario Flow로 구성했다. `01`만 Connection Config와
  Dashboard Base/Theme을 소유하고 다른 모든 Flow가 이를 공유하여
  여러 Flow를 함께 사용해도 TCP 연결과 command authority가 중복되지 않는다.
- Axis Dashboard에는 첫 feedback 기준으로 축 범위를 고정하고 선택 축 actual position/velocity,
  축 이름 fallback, 500 sample 제한과 축 선택/연결 단절 시 초기화를 반영했다.
- mock Motion Server를 대상으로 Python `system/server/status`와 `system/feedback` smoke test를
  통과했다. 전체 Python unittest 329개, Node-RED test 7개, production dependency audit 0건,
  Python wheel/Node-RED tarball clean install, source compile, Node syntax와 whitespace 검사를 통과하여
  `RF-002`를 완료 처리했다.

### 설계 보완

- `RF-002`는 재사용 가능한 최소 Python client 모듈과 Node-RED의 공통 node 및 scenario flow를
  분리하기로 확정했다. 두 결과물은 새 `reference_clients` 폴더 아래 독립 installable package로
  구성하며 기존 Control Panel client와 장비 자료용 `Reference` 폴더는 변경하지 않는다. Python에서
  scenario별 script를 중복 구현하지 않는다. 공통 모듈은 TCP
  JSON-lines 연결, request id correlation,
  response/feedback 분리, timeout과 연결 단절 처리만 담당하며 authority, motion, I/O와 parameter
  access의 실행 순서는 Node-RED flow 또는 Python client 외부 application에 둔다. 모든 API를 Python method로 감싸는 범용 SDK와 application
  업무 로직은 범위에서 제외한다. 연결 단절 시 미완료 요청은 모두 실패 처리하고 자동 재전송하지
  않으며, 재연결 후 필요한 동작은 application이 새 요청으로 명시하도록 확정했다. 연결 단절로
  해제된 command authority도 자동 복원하지 않고 scenario가 server 상태 확인 후 명시적으로 다시
  요청한다. 비동기 feedback은 전용 queue에 저장하고 scenario가 `get_feedback()`으로 소비하며,
  TCP 수신 thread에서는 사용자 callback을 직접 실행하지 않기로 확정했다. queue 포화 시 가장 오래된
  feedback을 제거하고 최신 값을 유지하되 request response는 별도 경로에서 손실 없이 처리한다.
  queue 기본 크기는 100개로 하고 client 생성 인자로만 조정한다. 공개 API는 동기 `request()`로
  유지하면서 여러 thread의 동시 호출을 지원하고, 송신 직렬화와 고유 `request_id`별 독립 대기를
  제공한다. client는 message 복사본에 session prefix와 증가 번호 기반 `request_id`를 자동 부여하며
  caller의 직접 지정은 거부하고 재연결 후에도 번호를 계속 증가시킨다. `async/await` API는 초기
  범위에서 제외한다. 기본 request timeout은 5초이며 client와
  개별 요청에서 변경할 수 있다. timeout된 pending 요청과 지연 response는 폐기하되 연결은 유지하고,
  장시간 recovery 명령은 scenario가 더 긴 timeout을 지정한다. `start()` 이후 최초 연결 및 단절 후
  재연결은 기존 Control Panel과 같은 고정 1초 주기로 background에서 수행한다. 미연결 요청은 즉시
  실패하고 `wait_connected()`와 `stop()`으로 application이 연결 대기와 종료를 제어한다. 단절 시
  feedback queue를 비우고 재연결 후 새 feedback만 제공하며 연결 상태와 마지막 오류는
  `is_connected`와 `last_error`로 별도 조회한다. 서버 `Fail`은 정상 API response로 반환하고 Python
  exception은 client 자체의 연결, timeout과 사용 실패에만 사용하며 Failure code별 exception 계층은
  만들지 않는다. Node-RED Custom Node는 Connection, Connection Control, Request, Feedback,
  Connection Status 5종으로
  제한하고 상태 조회, authority, Axis, I/O, parameter와 simulation은 scenario Subflow/Flow로
  구성한다. API command마다 Custom Node를 만들지 않고 반복 사용성이 확인된 Subflow만 추후 승격한다.
  Request node는 `msg.payload.cmd`만 command 식별자로 사용하고 caller topic/property를 보존하며,
  Feedback과 Connection Status만 고정 topic을 출력한다. Request 출력은 서버 Success/Fail response와
  client transport failure의 2개로 분리한다. 원본 request payload는 복제하지 않고 caller property만
  보존하며 client error에는 request id와 command를 포함한 최소 정보만 제공한다. Connection은 Config
  Node로 구현하여 이를 선택한 node가 하나의 TCP 연결과 authority/correlation 상태를 공유하고,
  여러 서버는 별도 Config로 격리한다. Config는 host, port와 기본 5초 timeout을 제공하고 Request
  Node만 optional timeout override를 가지며 1초 재연결 주기는 UI에 노출하지 않는다.
  Connection Status는 초기 snapshot과 connected 값 변경 시에만 connected/last_error를 출력하고 반복
  재연결 시도는 event로 내보내지 않는다.
  Example은 connection/status와 authority를 하나의 공통 기반 Flow로, Axis, I/O, parameter와
  Virtual I/O simulation을 기능 Scenario Flow로 제공한다. 공통 Flow만 Connection Config와 Dashboard
  Base/Theme을 소유하고 나머지 Flow가 이를 참조하여 함께 import해도 TCP 연결, Dashboard와 authority가
  중복되지 않게 한다.
  Axis flow에는 선택 축의 actual position/velocity graph를 포함하고 상태 변경
  명령은 수동 입력으로만 실행한다. Dashboard는 `@flowfuse/node-red-dashboard`의 `ui-chart`를 사용하고
  legacy dashboard package는 지원하지 않는다. Axis graph는 모든 feedback에서 선택 축 값만 사용해
  최근 500개 sample을 유지하고 축 선택 변경과 단절 시 초기화하며 첫 feedback의 축 수와 status
  name/fallback으로 선택 범위를 구성한다.
- `TD-030` 검토 중 Mock CMMT가 선택된 `PDO_Configuration`을 Master runtime, OD Model과 Bridge에
  직접 주입하여 cyclic PDO 변환은 수행하지만, 실축의 PRE-OP PDO assignment/mapping SDO write와
  readback 검증을 우회하는 것을 확인했다. `PDO_Configuration` 주입은 변환 규칙일 뿐 device
  configuration을 대체하지 않는 것으로 확정하고, 기존 CMMT profile sequence를 Mock에서도
  실행하는 S08을 TD-030에 추가했다. 이 항목 완료 전까지 TD-030 상태를 `in_progress`로 되돌렸다.

### 등록

- `TD-030`을 등록하여 MockSlave가 소유한 PDO encode/decode를 MockMaster 측으로 이동하고
  PySOEM과 동일한 `prepare -> send -> receive` 직렬화 경계로 정렬한다. MockSlave는 raw PDO/SDO
  endpoint로 축소하되 TD-029의 VirtualOdBridge 및 Model_Update 경계를 유지하며, RF-001 구현과
  EtherCAT frame simulation은 범위에서 제외한다. 현재 구조에 Virtual CPX를 먼저 결합한 뒤 다시
  분리하는 재작업을 막기 위해 TD-030을 RF-001의 명시적인 선행 작업으로 확정했다.

### 완료

- `RF-014`에서 `system/simulation/io/input_read`, `input_write`, `input_reset` API와
  `MOTION_SERVER_SIMULATION_API_ENABLED` 설정을 추가했다. API는 mock backend에서 명시적으로
  활성화한 경우에만 동작하고 command authority와 독립적으로 DI boolean, AI raw integer와
  IO-Link module raw input payload를 RF-001 Virtual CPX input state에 주입한다. 값은 다음 PDO
  cycle부터 기존 feedback에 반영되며 module/station reset과 bus reconnect/server restart에서
  초기화된다. IO Control Panel은 capability probe 성공 시에만 Simulation UI를 표시한다. 다중
  station 격리, 정책/target 거부와 panel 상태 보존을 포함해 전체 unittest 319개를 통과했다.
- `RF-001`에서 station ESI와 설정된 AP module ESI를 기반으로 `VirtualCpxOdModel`, metadata 기반
  `VirtualApModule`과 `VirtualCpxApDevice`를 구현했다. 설정 크기에 맞는 고정
  `0x6F00`/`0x7F00` PDO block만 활성화하고 Mock PRE-OP에서 실장치와 같은 module ident,
  assignment/mapping 및 process-image 검증을 수행한다. DO/AO/IO-Link output은 OD process image를
  `Model_Update`에서 해석하며 DI/AI/IO-Link input은 독립 상태로 보고하여 자동 loopback을 하지
  않는다. AP/ISDU는 gateway dispatch 경계까지만 제공하고 parameter device와 공개 input injection
  API는 RF-013/RF-014 범위로 유지했다. 완료 리뷰에서 ESI `DefaultData`/`DefaultValue` 초기값 반영과
  input/output channel·datatype 범위 검증을 보완했다. Axis/IO 혼합 runtime을 포함한 RF 전용 테스트
  10개와 전체 unittest 309개, source compile 및 diff whitespace 검사를 통과했다.
- `TD-030`에서 Mock/PySOEM 공통 `MasterPdoRuntime`을 추가하고 RxPDO/TxPDO 객체, PdoCodec과
  prepared/transmitted/received raw buffer를 Master 측으로 통일했다. 두 backend는 strict
  `prepare -> send -> receive` phase와 immutable output snapshot을 사용한다. MockSlave는 raw
  PDO/SDO endpoint로 축소하여 `exchange_processdata()`에서 TD-029의
  `OD -> Model_Update -> OD` 경계만 수행한다. 다중 slave raw input 선검증, in-place TxPDO decode,
  snapshot, lifecycle, WKC와 timing parity를 자동 테스트했다.
- `TD-030-S08`에서 Mock PRE-OP connect도 기존 DeviceProfile의 process-image 준비 sequence를
  실행하도록 연결했다. CMMT ESI array datatype을 subindex별 Virtual OD entry로 확장하고, virtual
  identity 확인, PDO assignment/mapping SDO write, readback 검증과 Master mapping 확정을
  PySOEM startup과 정렬했다. identity mismatch cleanup 및 mapping OD 상태 회귀 테스트를 포함해
  전체 unittest 299개, source compile과 diff whitespace 검사를 통과하여 TD-030을 완료했다.

## 2026-08-26

### 설계 확정

- `RF-001`의 Virtual CPX를 ESI/`CPXApModule` metadata 기반 공통 `VirtualApModule` 구조로
  확정했다. 실제 ESI와 같은 `0x6F00`/`0x7F00` 16-byte block OD, 독립 input state, raw IO-Link
  process data와 Model_Update 경계를 사용하고 자동 loopback은 하지 않는다. I/O reset/restart는
  RF-003, 상세 Diagnostic은 RF-012, AP/ISDU parameter device는 RF-013, 공개 Simulation API는
  RF-014로 분리했다.

### 등록

- `RF-014`를 등록하여 Control Panel과 외부 simulator가 Virtual CPX의 DI/AI/IO-Link input을
  조작할 수 있는 별도 Simulation API를 후속 구현한다. RF-001은 module input state와 내부
  injection 계약까지만 담당하며 일반 운전 API, MockSlave와 OD Bridge에는 simulation 의미를
  추가하지 않는다.
- `RF-013`을 등록하여 Virtual CPX의 gateway OD 뒤에 실제 AP module parameter 공간과 IO-Link
  Device ISDU parameter 공간을 가진 하위 가상 장치를 후속 구현한다. RF-001은 station OD,
  process image와 gateway 전달 기반까지만 담당하고, RF-004의 APDD catalog 기능과도 분리한다.
- Linux 4축 Motion Server에 Windows Axis Control Panel을 연결해도 시작 시 1축 fallback UI가
  유지되는 사례를 확인했다. 기존 TD-024 범위와 동일하므로 중복 TD를 만들지 않고 재현 증거,
  endpoint 변경 시 동적 재구성 완료 조건과 높은 우선순위를 추가했다.
- `TD-027`을 등록하여 Axis/IO Control Panel의 Motion Server runtime·Diagnostic 상태 모니터링과
  Axis Panel Motion Tab의 선택 축 Fault/Alarm 및 Drive 오류 상세 표시 누락을 함께 추적한다.

### 완료

- `TD-029`에서 `VirtualOdBridge`를 `device.virtual_device` 공통 영역으로 이동하고 SDO의
  index/sub-index와 `PDO_Configuration`의 raw RxPDO/TxPDO mapping을 하나의 OD Model에
  연결했다. MockSlave는 실축과 동일한 `DeviceProfile.pdo_codec`으로 PDO 객체와 raw payload를
  변환하고 Bridge는 장치별 PDO 객체나 codec을 참조하지 않는다.
  Virtual Servo의 PDO 직접 참조와 OD write callback을 제거하고 Model_Update 시점에 현재 OD를
  반영하도록 변경했다. `MockSlave`는 `RxPDO -> OD -> Model_Update -> OD -> TxPDO` 순서만
  조정하며 Servo 패키지에 의존하지 않는다. OD 값 codec은 CMMT PDO와 Virtual SDO가 공유하며
  전체 unittest 289개가 통과했다.
- `TD-028`에서 `VirtualOdBridge`에 있던 CMMT reset/save role 분기와 virtual reset sequence를
  제거했다. 장치 내부 반응은 Virtual Servo로 이동했으며 Motion Server/CMMT DeviceProfile의
  실축·가상축 공통 sequence는 변경하지 않았다. Bridge purity 및 기존 동작 회귀를 포함한
  전체 unittest 286개가 통과했다.
- `TD-024`와 `TD-027`을 통합 구현했다. Axis Panel의 축 수 확인용 임시 TCP 연결과 1축 fallback을
  제거하고 상시 연결의 첫 feedback으로 topology를 한 번 확정한 뒤 full status로 metadata를
  보완한다. 정상·Bus 단절·초기화 실패 feedback에 공통 Server health와
  `process_data_valid`를 추가했으며 Axis/IO Panel에 동일하게 표시한다. 선택 축 status는 tab 전환,
  health 변경과 recovery 결과에 맞춰 요청하고 Motion Tab Error에 활성 Diagnostic과 Drive 오류를
  결합한다. 초기 Axis 0 status 3회 및 tab 전환 status 2회 요청을 동일 축 request 병합으로
  제거하고 명시적인 health/recovery/Refresh만 강제 재조회하도록 보완했다. 전체 unittest
  284개가 통과했다.
- `TD-022`에서 Motion Server startup INFO를 server/runtime field 계약으로 분리했다. DC와 phase
  lock, CSP startup mode의 실제 활성 조건에 따라 detail을 포함하고 축별 scale/status/position
  배열을 제거했다. formatter는 typed configuration만 사용하며 정상 listening 로그는 bind
  endpoint만 남겨 초기화 요약의 backend/axes 중복도 제거했다.
- `TD-020`에서 Motion Server image/container를 `motion-server:dev`/`motion-server`, Axis/IO
  Panel 공용 image를 `motion-server-control-panel:dev`, Compose project를 `motion-server`,
  systemd unit을 `motion-server.service`로 직접 전환했다. 운영 script의 legacy fallback을
  제거하고 일회성 cleanup 절차와 legacy identifier 검사를 추가했다. 전체 unittest 265개와
  Compose render 검사는 통과했지만 생성 unit의 `${COMPOSE_ENV_FILE}`을 systemd가 먼저 빈 값으로
  확장하여 service 기동이 실패했다. 중간 변수를 제거하고 Bash command substitution을 직접
  사용하도록 수정한 뒤 회귀 테스트를 266개로 늘렸으며 Linux에서 신규 service와 container의
  정상 기동을 재확인하여 TD-020을 완료했다.
- `TD-019`에서 GitHub repository를 `IlgonKo/motion-server`로 rename하고 Windows/Linux
  repository root를 각각 `C:\Users\Festo\Documents\motion-server`와
  `/home/festo/Documents/motion-server`로 전환했다. 대상 Git checkout과 `.env`를 삭제할 수 있는
  Windows archive sync를 제거하고 Linux update를 Git clone/pull로 통일했다. Windows clean clone의
  전체 unittest 265개와 Linux 새 경로의 실제 Motion Server 구동을 확인했다.

- `RF-005` 실축 cable reconnect에서 OP 진입 후 동기 SDO parameter refresh가 cyclic PDO를
  중단하여 WKC가 `5/15`로 유지되고 Axis Fault Reset RxPDO가 전달되지 않는 문제를 확인했다.
  recovery refresh를 PRE-OP으로 이동하고 OP 진입 후 expected WKC 3회 연속 확인을 완료 조건으로
  추가했다. 수정 후 CMMT 4축과 CPX-AP-I-EC 1대 구성에서 cable 분리, 기존 TCP/authority 유지,
  Bus reconnect와 별도 Axis fault-reset을 검증했다. 최종 runtime `normal`, WKC `15/15`, 활성
  Diagnostic 없음이 확인됐으며 전체 unittest 265개가 통과했다.
- 같은 실축 구성에서 Axis 0 restart를 실행하여 restart command 전 전체 축 Controlword `0x0007`,
  Statusword state `0x0023`을 확인했다. 13.27초 후 WKC `15/15`로 recovery가 완료됐고 자동 enable
  및 motion 재개 없이 다른 Axis의 CiA 402 Fault가 별도 fault-reset 대상으로 유지됐다.
- 전 축 Operation Enabled 상태에서 Axis 1 restart를 추가 검증했다. restart 명령이 전 축을
  Controlword `0x0007` 및 Statusword state `0x0023`으로 전환한 뒤 장치를 재시작했고 11.649초
  후 WKC `15/15`로 내부 Bus recovery를 완료했다. 성공한 restart의 예상 transport 단절은 Bus
  Fault를 만들거나 별도 Bus reconnect를 요구하지 않는 계약으로 확정하고 RF-005를 완료했다.
- Windows launcher가 이전 실행에서 process environment에 투영한 Motion Server 설정을 다음 실행에
  재사용하지 않고 현재 `.env`를 다시 읽도록 정리했다. project root `PYTHONPATH` 중복을 제거하고
  전체 경로 대신 resolved project root만 출력하도록 TD-021을 완료했다.
- 실제 CMMT identity/profile 불일치가 일반 `RuntimeError` traceback으로 노출되는 초기화 오류 경계
  개선을 TD-026으로 등록했다.

## 2026-08-25

### 완료

- `RF-005` 완료 리뷰 보완으로 Axis restart 전에 전체 Axis homing/trajectory 중단, 위치 hold 및
  disable을 강제하고 자동 motion 재개를 금지했다. 정상 상태 Bus reconnect를 거부하고 연속 WKC
  mismatch 뒤 slave 상태 확인으로 cable disconnect fallback을 추가했다. recovery worker 없이
  TCP/authority는 유지하되 동기 recovery 동안 다른 API 처리가 일시 정지하는 계약과 best-effort
  timeout 한계를 문서·Control Panel에 명시했다. 전체 unittest 258개가 통과했다.
- `RF-005-S05`에서 typed `RecoveryType`과
  `refresh_after_recovery(runtime, recovery_type, affected_axes)` TD-025 연결 경계를 추가하고
  Bus reconnect 전체 Axis/Axis restart 단일 Axis 계약을 검증했다. startup/operational
  reconnect Diagnostic 처리를 통합하고 recovery 전체 timeout 및 OP 전후 실패 상태를
  보완했으며 API·시험·TD-025 문서의 폐기된 reset 계약을 정리했다. 전체 unittest 255개와
  source compile 및 diff 검사가 통과했다. RF-005는 실축 검증 전까지 `in_progress`로 유지한다.
- `RF-005-S04`에서 Axis restart를 요청 전송 즉시 성공하던 방식에서 대상 slave 재발견,
  PySOEM process image 재구성, 전체 Axis mode/CSP 설정 복원, OP 진입과 대상 Axis parameter
  refresh까지 완료한 뒤 응답하는 동기 recovery로 전환했다. 진행 중에는 전체 Bus motion을
  제한하며 Mock/PySOEM이 같은 coordinator를 사용한다. timeout과 단계 실패는
  `AXIS_RESTART_FAILED`로 유지하고 이후 Bus reconnect와 Axis fault-reset으로 clear 가능한
  경로를 연결했다. 전체 unittest 251개가 통과했다.
- `RF-005-S03`에서 PySOEM/Mock cyclic transport 오류를 `BUS_DISCONNECTED`와
  `BUS_CONNECTION_LOST` Fault로 전환하고 runtime, DeviceManager, cache/controller/topology,
  TCP client 및 authority를 유지하는 disconnected service loop를 구현했다. Bus reconnect를
  같은 runtime의 PRE-OP/process image/Axis mode/OP/전체 parameter refresh가 끝난 뒤 응답하는
  동기 coordinator로 변경했으며 startup 실패 reconnect도 기존 TCP 연결에서 새 runtime으로
  전환한다. 실패는 `BUS_RECONNECT_FAILED`로 유지한다. 전체 unittest 248개가 통과했다.
- `RF-005-S02`에서 Diagnostic source/source type별 활성 Fault 조회와 일괄 acknowledge를
  구현하고 Server/Bus/Axis/Axes fault-reset을 실제 Diagnostic 수명 주기와 Axis CiA 402
  복구에 연결했다. WKC Fault의 전역 runtime `FAULT` 전환 및 latching 제한, Axis Fault의
  해당 축 한정 제한과 상태별 안전/recovery API 허용 행렬을 적용했다. 전체 unittest 246개가
  통과했다.
- `RF-005-S01`에서 `ServerSession` 소유의 `ServerRuntimeState`를 추가하고 server/bus status에
  노출했다. Bus reconnect 및 Axis restart timeout 설정을 추가하고 Initialization recovery
  scope를 `BUS_RECONNECT < SERVER_RESTART`로 단순화했다. 배포 전 호환성 원칙에 따라
  server/axis/axes reset API와 Server reset lifecycle을 제거하고 fault-reset 명칭으로 API,
  Control Panel 및 테스트를 전환했다. 전체 unittest 239개가 통과했다.
- `TD-018` 완료 리뷰의 P1을 반영하여 cache/unit/MotionController projection과 server state
  생성이 끝난 뒤에만 Initialization 성공과 Fault resolve를 확정하도록 수정했다. 후처리 실패는
  runtime을 정리하고 `DEVICE_INITIALIZATION_FAILED` degraded 상태로 전환한다. `0x6081` OD
  readback은 첫 cyclic exchange 전에 RxPDO command에 동기화하고 Axis restart와 공통 helper를
  사용하도록 정리했다. 실패 주입과 실행 순서 검사를 포함한 전체 unittest 238개가 통과했다.
- `TD-018-S05`에서 Initialization API와 server log가 Cause Definition Registry의 동일한
  stage/cause/message를 사용하도록 통일했다. 단계별 오류 주입, 같은 시각의 Fault 생성,
  reconnect의 latching Fault resolve-only 동작, reset/reconnect의 DiagnosticManager 소유권
  차이와 CPX layout/PDO catalog mismatch를 자동 검증했다. 전체 unittest 236개와 source
  compile 및 diff 검사가 통과하여 `TD-018`을 완료했다.
- `TD-018-S04`에서 Diagnostic/InitializationStatus/optional runtime을 소유하는 ServerSession과
  runtime 없는 degraded TCP server를 구현했다. 확정 allowlist와 recovery scope를 적용하고
  server/bus status를 typed/nullable 계약으로 전환했으며 legacy initialization 문자열 상태를
  제거했다. 실제 degraded listener 통합 검사를 포함한 전체 unittest 230개와 6축 정상 startup
  smoke가 통과했다.
- `TD-018-S03`에서 device model build, runtime creation, bus connection과 device initialization
  경계를 분리하고 stage 우선 cause mapping을 구현했다. CPX layout/PDO catalog와 필수 parameter
  readback은 typed cause로 전달하며 runtime factory의 부분 생성 cleanup과 원래 오류 보존 계약을
  적용했다. 전체 unittest 224개와 source compile, diff 검사 및 6축 Mock staged startup smoke가
  통과했다.
- `TD-018-S02`에서 port 전용 Bootstrap configuration과 한 번만 읽는 immutable configuration
  snapshot을 도입했다. 전체 typed configuration 실패도 bootstrap endpoint와 typed failure를
  가진 Application으로 보존하고, Motion Server bind host 설정/CLI를 제거하여 `0.0.0.0` 상수로
  고정했다. 관련 회귀 검사 40개와 전체 unittest 215개, source compile 및 diff 검사가 통과했다.
- `TD-018-S01`에서 Initialization stage/cause/failure/status와 Cause Definition Registry를
  구현했다. `DEVICE_MODEL_BUILD` 단계 명칭, 복구 범위 계층과 상태 불변 조건을 단일 typed
  model로 확정했으며 S01 단위 테스트 10개를 포함한 전체 unittest 210개와 source compile,
  diff 검사가 통과했다.
- `TD-014` 후속 보완으로 Windows 환경변수의 대소문자 변형을 설정 파일의 canonical
  key로 병합하여 PowerShell JSON projection 충돌을 제거했다. PowerShell 5.1/7.x
  호환 변환과 실패 시 실행 중단을 적용하고 회귀 검사를 포함한 전체 unittest 194개가
  통과했다.
- `TD-023` 완료 리뷰에서 전체 CMMT PDO mapping과 required Non-PDO OD를 교차 확인했다.
  유일한 중복인 `0x6081 Profile velocity`를 Non-PDO 계약과 preset에서 제거하고 PDO
  schema 소유로 정리했다. Bus reconnect는 runtime 재생성 계약으로 단순화하고 Virtual
  device reset은 선택된 Non-PDO configuration을 복원하도록 보완했다. 전체 unittest
  196개, source compile과 diff 검사가 통과했다.
- `TD-023-S06`에서 Device OD readback을 원본으로 하는 typed
  `AxisParameterRuntimeCache`를 추가했다. startup·설정 변경·Mock Axis restart에서 cache,
  unit conversion과 MotionController 제한을 동기화하고 mutable server state의 중복
  parameter 필드를 제거했다. 범용 cache 관리는 `TD-025`로 분리했다.
- Profile 설정의 여러 SDO write 중 일부가 실패해도 실제 readback으로 cache와
  `0x6081` RxPDO command를 재동기화한 뒤 Fail을 반환하도록 보완했다.
- PySOEM Axis restart 후 cache refresh는 TD-023에서 분리했다. restart 완료 감지와
  EtherCAT recovery는 RF-005, 완료 통지 이후 OD refresh와 invalid 처리는 TD-025가
  담당하도록 문서 경계를 확정했다.
- startup 필수 cache 항목인 user position unit과 converting unit readback 실패를
  initialization error로 변경했다. Software position limit은 필수가 아니므로 기존 안전
  fallback 정책을 유지했다.
- startup 필수 OD를 unit과 exponent로 한정했다. Profile/motion limit 실패는 0 기반
  fallback으로 계속하며, motion/software limit 부분 write 실패도 가능한 readback으로
  cache와 제어 projection을 동기화한 뒤 Fail을 반환하도록 보완했다.
- `TD-023`에서 required non-PDO OD 존재 계약과 code-defined Virtual CMMT commissioning
  configuration catalog를 분리했다. `.env`는 값 정의 없이 preset만 선택하며 6축은
  slave 0~2 `linear_mm`, 3~5 `rotary_deg`를 선택한다.
- CMMT 설정 파일에 섞여 있던 서버 공통 initial motion mode를 메인 설정으로 이동하고,
  코드에서 더 이상 사용하지 않는 `MOTION_SERVER_CSP_COUNTS_PER_UNIT` 잔재를 제거했다.
  CSP interpolation mode와 velocity offset도 현재 전 축 공통 정책에 맞춰 메인 설정과
  `MotionConfig`로 이동하고 CMMT 설정에는 PDO와 Non-PDO preset 선택만 유지했다.
- Mock Virtual OD만 선택 configuration으로 초기화하고 startup motion-limit 덮어쓰기를
  제거했다. mock/실축 모두 정상 시 device OD readback으로 runtime 제한을 구성한다.
- legacy server motion-limit/PP jerk 환경변수와 CLI를 제거하고 CSP jerk를 메인
  `MOTION_SERVER_CSP_JERK` 및 `MotionConfig.csp_jerk`로 분리했다.
- configuration 완전성·ESI 자료형·값 범위·slave 선택, Virtual OD 초기화/lifecycle,
  startup overwrite 부재와 legacy 제거 검증을 추가했으며 전체 unittest 193개가 통과했다.

## 2026-08-24

### 등록

- `TD-024`를 등록하여 Axis Control Panel 시작 시 축 수 확인용 임시 연결과 상시 연결이
  중복되고 Windows 서버에 `WinError 10054`가 남는 문제를 추적한다.

### 완료

- CMMT에서 PDO configuration 외부의 Motion Server 필수 OD 계약임을 명확히 하기 위해
  `required_od.py`를 `required_non_pdo_od.py`로 변경하고 관련 type, 함수와 profile 계약을
  `required_non_pdo_od_*` 명칭으로 통일했다.
- `TD-014` 완료 후 전체 리뷰에서 발견된 DC 비활성 runtime 경계, 축별 CMMT CSP 설정,
  composition root projection, 초기 motion mode validation과 cold-import 검증을 보완했다.
  pre-history 중복과 잔여 코드도 정리했다. Windows launcher를 Application entrypoint로
  수정하고 loader 원본 오류를 보존했다. 프로젝트 외부 작업 폴더에서도 configuration을
  찾도록 보완했으며 전체 unittest 182개와 실제 실행 smoke를 통과했다.
- `TD-014-S07`에서 import-time `motion_server/config.py`, active configuration,
  environment backfill과 전역 CMMT profile을 제거했다. CLI/PDO 계약을 독립 module로
  분리하고 모든 축 동작이 runtime instance profile을 사용하도록 전환했으며,
  Windows/Linux entrypoint와 import isolation 검사를 포함한 전체 unittest 171개가
  통과하여 TD-014를 완료했다.
- `TD-014-S06`에서 derived velocity 계산·설정·API·UI를 제거하고 필수 TxPDO actual
  velocity만 사용하도록 정리했다. `configured_index`와 mock axis type/user-unit 전용
  설정도 제거하여 가상/실제축이 같은 device profile OD/unit을 사용하며, 재도입 방지
  정적 검사 2개를 포함한 전체 unittest 168개가 통과했다.
- `TD-014-S05`에서 전역 logging 상수와 `status_log()`, state의 `tx_history`를 제거하고
  runtime-owned `RuntimeLogger` 및 optional bounded pre-logging을 도입했다. 비활성 시
  buffer/기록을 만들지 않고 활성 시 non-command event에 이전 cycle snapshot을
  첨부하며 command log는 제외한다. 계약 테스트 3개를 포함한 전체 unittest 166개와
  source compile 검사가 통과했다.
- `TD-014-S04`에서 CMMT/CPX typed device instance config를 공통 profile factory에
  주입했다. CMMT PDO와 CPX module/IOL 설정의 장치 내부 환경 변수 재해석을 제거하고
  mock/PySOEM이 같은 CMMT profile 설정을 소비하도록 통일했으며, profile projection
  테스트를 포함한 전체 unittest 163개와 source compile 검사가 통과했다.
- `TD-014-S03`에서 CLI `Namespace`의 runtime 전달을 제거하고 server, EtherCAT,
  motion, logging 및 Bus device typed projection을 TCP loop, runtime/state factory에
  주입했다. feedback/socket/cycle/DC/motion 설정의 전역 의존을 제거하고 startup
  log의 장치 상태 및 비활성 DC 세부값도 정리했으며 전체 unittest 162개와 source
  compile 검사가 통과했다.
- `TD-014-S01`에서 immutable server, EtherCAT/cycle/DC, motion, logging 및 CMMT/CPX
  instance configuration model과 builder/validation을 추가했다. 기존 runtime은 아직
  기존 경로를 유지하며 typed configuration 테스트 5개와 전체 unittest 160개가 통과했다.
- `TD-014-S02`에서 명시적 `ConfigurationSource`와 `MotionServerApplication` composition
  root를 도입하고 일반/Windows entrypoint를 같은 1회 configuration 생성 경로로 연결했다.
  복수 application 격리와 runner 경계 테스트를 포함한 전체 unittest 162개가 통과했다.
- `TD-006`에서 file parser, environment overlay와 typed Bus model을
  `configuration` package로 분리했다.
- Motion Server와 Windows packaging이 동일한 `ConfigurationModel` 및 `BusConfig`를
  사용하고, Bus에 포함된 profile의 장치 설정만 공통 parser로 로드하도록 통일했다.
- Linux Compose, Windows PowerShell과 CMMT sync probe의 독자 parser도 제거하고
  공통 configuration CLI/model의 projection을 사용하도록 전환했다.
- ROS의 프로젝트 `.env` 및 Bus 독자 parser를 제거하고 공통 model 연동과 ROS 전용
  설정은 RF-008 후속 범위로 기록했다.
- continuation, indexed axis/I/O Bus, 오류 설정, 우선순위와 Windows parity를 검증하는
  설정 model 테스트 6개를 추가했다.
- TD-006 전체 리뷰 후 unittest 155개, source compile, 공통 configuration CLI,
  PowerShell projection과 Linux shell 문법 검사가 통과했다.

## 2026-08-21

### 완료

- `TD-005-S11C`에서 파일·함수 단위 broad catch allowlist와 Exception mapping, legacy 제거, handler 직접
  송신 금지 정적 검사 4개를 추가했다.
- broad catch 승인 목적과 변경 절차를 API error boundary 계약으로 문서화하고 최초 error point
  inventory를 migration 완료 snapshot으로 전환했다.
- 전체 unittest 149개와 source compile 검사가 통과하여 `TD-005`를 `complete`로 종결했다.
- `TD-005-S11B2B`를 완료하여 Axis motion/state/settings, jog, homing, trajectory와 parameter-save의
  요청 결과를 data 반환/typed Exception/`PartialFailure` 계약으로 통일했다.
- router의 `_RequestCaptureConnection`, legacy 판별과 `_operation_result` 임시 저장을 제거했다.
  요청 handler/control 계층의 직접 송신도 제거되어 request boundary만 최종 envelope를 한 번 송신한다.
- 전체 unittest 145개와 source compile 검사가 통과했다. S11B를 더 세분화하지 않고 다음 단계는
  broad catch 및 정적 계약 검사를 마무리하는 `TD-005-S11C`다.
- `TD-005-S11B2A`에서 router의 unknown/advanced-only/authority/initialization 거부와 command registry의
  selector/미구현 검증을 legacy 송신 대신 typed Exception으로 전환했다.
- server reset/restart, bus reconnect와 I/O output write는 operation data 또는 `PartialFailure`를
  반환하도록 바꿨다. 전체 unittest 145개와 source compile 검사가 통과했으며 다음 단계는 남은 Axis
  command와 request capture를 제거하는 `TD-005-S11B2B`다.
- `TD-005-S11B1`에서 status, EtherCAT/AP/IO-Link parameter 및 authority operation을 순수 data 반환과
  typed Exception 계약으로 전환하고 사용되지 않는 중간 response helper를 제거했다.
- direct handler 계약 테스트를 새 반환 방식으로 갱신했으며 전체 unittest 145개가 통과했다. 다음은
  command 및 authority validation 직접 송신과 임시 request capture를 제거하는 `TD-005-S11B2`다.
- `TD-005-S11A`에서 미배포 프로젝트에는 backward compatibility가 필요 없다는 결정에 따라 client의
  legacy response와 `diagnostics` fallback을 완전히 제거했다.
- Axis/I/O Control Panel과 ROS Bridge는 현재 Success/Fail envelope 및 승인 notification만 해석하며,
  과거 `ok/error`, `command_rejected`와 result 없는 response는 malformed로 거부한다.
- S11A 테스트 6개와 전체 unittest 145개가 통과했다. 다음 단계는 command capture를 제거하는 S11B다.
- `TD-005-S10`을 완료하여 모든 등록 request/response의 실제 서버 송신을 Success/Fail envelope로
  전환했다. 요청당 한 응답, request ID 반환, 빈 비동기 Success와 최상위 예상 밖 오류 비노출을 보장한다.
- status 및 EtherCAT/AP/IO-Link parameter의 legacy 변환 helper와 Axis `diagnostics` 송신 별칭을 제거했다.
  주기 feedback/notification은 독립 payload로 유지하고 command 내부 직접 송신 capture는 S11 정리 대상으로 남겼다.
- S10 live cutover 테스트 6개와 전체 unittest 145개 및 source compile 검사가 통과했다. 다음 단계는 S11이다.
- `TD-005-S09`를 완료하여 Axis/I/O Control Panel과 ROS Bridge 수신 경계에 legacy/new Success/Fail
  공통 decoder를 적용했다.
- 성공 data, Failure code/message와 승인 details를 기존 client view로 안전하게 변환하고 malformed
  응답도 연결 loop를 중단하지 않는 실패로 처리했다.
- Axis 원시 CMMT readback을 정식 `device_diagnostics`로 이관하고 현재 legacy adapter에서만
  `diagnostics` 별칭을 유지했다. 호환 테스트 7개와 전체 unittest 140개가 통과했으며 다음 단계는 S10이다.
- `TD-005-S08D`를 완료하여 기존 server/bus/axis/axes/io status에 source 범위별 공통
  `diagnostic_status` snapshot을 연결했다.
- Definition/Source/History, 범위별 현재 level, 안정적인 Fault 우선 정렬과 UTC timestamp를 직렬화하고,
  내부 예약 `detail/context`와 기존 Axis `diagnostics` 원시 readback은 공개 공통 계약에서 분리했다.
- S08D 테스트 4개와 전체 unittest 133개가 통과했다. S08 전체를 완료했으며 다음 단계는
  Control Panel/ROS dual-read 호환을 구현하는 S09다.
- `TD-005-S08C2`에서 CPX-AP health source를 조사하여 `0x6102 Diagnosis`와 선택형 `0x1AF1 Diag PDO`가
  존재하지만 기본 Sync Manager assignment에는 포함되지 않음을 확인했다.
- PDO 구성에 따라 진단 가능 여부가 달라지는 상태에서 module/channel Diagnostic을 생성하지 않기로
  확정했다. Bus WKC 추정과 단발 AP/ISDU 실패 승격도 제외하고, 선택형 상세 진단은 Optional Item
  `RF-012`로 분리했다. 이로써 S08C를 완료했으며 다음 단계는 S08D다.
- `TD-005-S08C1`을 완료하여 정상 process-data cycle 직후 Bus WKC와 Axis statusword를 평가하는
  runtime Diagnostic monitor를 연결했다.
- 3회 연속 WKC 불일치는 latching Bus Fault, Axis fault bit는 latching Axis Fault, warning bit는
  non-latching Axis Alarm으로 생성하고 조건 해제 시 resolve하도록 구현했다.
- 단발성 WKC 누락과 API timeout은 Diagnostic으로 승격하지 않았으며 runtime 시험 8개와 전체
  unittest 129개를 통과했다. IO health source 판정은 S08C2로 분리했다.
- `TD-005-S08B`를 완료하여 startup 필수 초기화 실패를 latching
  `SERVER_INITIALIZATION_FAILED` Fault와 `SERVER:0` source로 연결했다.
- DiagnosticManager를 runtime 원시 장치 진단과 분리하고 같은 프로세스의 reset/reconnect 재초기화 동안
  유지하여 성공 시 resolve, acknowledge 후 clear되는 lifecycle을 보존했다.
- 기존 degraded server와 `initialization_error`, recovery command 허용을 유지하고 API Fail과
  Diagnostic 독립성을 포함한 S08B 테스트 9개와 전체 unittest 121개를 통과했다.
- `TD-005-S08A`를 완료하여 확정된 Diagnostic Definition/Source/History/Status model과 활성 lifecycle
  저장소를 구현했다.
- detect, acknowledge, resolve, latching/non-latching clear, clear 전 재검출과 clear 후 신규 ID 재발,
  source별 uniqueness 및 FAULT/ALARM/NORMAL 계산을 구현했다.
- 외부 Diagnostic API와 startup/runtime 연결은 확장하지 않았으며 S08A 테스트 13개와 전체
  unittest 112개를 통과했다. 다음 단계는 startup Initialization Fault를 연결하는 S08B다.
- `TD-005-S07C`를 완료하여 server/bus/axis/axes/IO status와 현재 Axis/EtherCAT/IO-Link Catalog
  handler를 공통 request boundary에 연결했다.
- Catalog의 not-ready, 없는 axis/IO/module/port binding, selector validation과 unsupported operation을
  구체 Failure로 분리하고 예상 밖 내부 오류는 `INTERNAL_FAILURE`로 안전하게 숨겼다.
- handler의 직접 `ok: false/error` 생성을 중앙 legacy status adapter로 이동해 S10 전 기존 client
  응답 의미를 유지했으며 S07C 테스트 9개와 전체 unittest 99개를 통과했다.
- `TD-005-S07A/S07B`를 완료하여 request boundary가 `PartialFailure`를 전체 code
  `PARTIAL_FAILURE`, 성공 target과 대상별 안전한 Failure로 encoding하도록 연결했다.
- 축 enable/disable의 대상별 controlword write와 IO output의 단일·복수 module/channel write를
  all-success, all-fail, partial-fail로 구분하고 기존 cycle exchange, target hold와 legacy 응답을 유지했다.
- 축 selector 및 IO output validation을 구체 Exception으로 분류하고 authority/state/limit/device 및
  내부정보 비노출을 포함한 S07A/B 테스트 7개와 전체 unittest 90개를 통과했다.
- `TD-005-S06`을 완료하여 IO-Link ISDU read/write의 I/O, port binding, IODD index/subindex와 access
  right 검증을 구체 Exception으로 구분하고 busy timeout 및 device status 처리를 통일했다.
- ISDU SDO/transport 오류의 broad RuntimeError 포장을 제거하고 S03 backend Exception을 그대로
  request boundary에 전달하면서 기존 `ok/error` 응답은 S10까지 유지했다.
- S06 테스트 10개와 전체 unittest 83개를 통과했으며 제품 source 신규 파일 없이 기존 `iol.py`에서 구현했다.
- `TD-005-S05`를 완료하여 AP parameter API와 startup write의 I/O/module validation, payload 오류,
  busy timeout, device reject 및 S03 backend Exception 전달을 공통 계약으로 migration했다.
- AP parameter catalog가 없는 현재 범위에서는 parameter ID 사전 존재 검증을 RF-004에 유지하고,
  실제 장치의 nonzero status를 `DeviceRejectedException`과 device code로 보존했다.
- S04에서 발견되지 않았던 API package/router 순환 import를 제거하고 임시 handler adapter는 호출
  시점에만 boundary에 연결되도록 수정했다.
- S05 테스트 12개와 전체 unittest 73개를 통과했으며 제품 source 신규 파일 없이 기존 모듈에서 구현했다.
- `TD-005-S04`를 완료하여 Axis/IO EtherCAT parameter read/write를 순수 operation, 구체 validation
  Exception, S03 backend Exception 전달과 S02 request boundary 구조로 migration했다.
- S10 전까지 기존 `ok/error` 응답만 보내는 추적 가능한 legacy adapter를 유지하고, 예상 가능한
  MotionServerException은 간단한 warning으로, 예상 밖 오류만 stack trace로 기록하도록 구분했다.
- S04 테스트 12개와 전체 unittest 61개를 통과했으며 제품 source 신규 파일 없이 기존
  `api/router.py`와 `handlers/parameter_access/ethercat.py` 안에서 구현했다.
- `TD-005-S03`을 완료하여 Mock/PySOEM SDO read/write의 object-not-found, timeout, device reject와
  communication failure를 공통 MotionServerException으로 통일하고 원래 원인을 chaining으로 보존했다.
- Generic MockMaster는 device-specific `KeyError`를 해석하지 않고 Virtual OD Bridge가 OD lookup과
  read-only 의미를 명시적 Exception으로 변환하도록 TD-016 책임 경계를 유지했다.
- SDO parity 테스트 10개, Virtual OD 오류 테스트 2개와 전체 unittest 49개를 통과했으며 예상하지
  못한 backend 및 typed-access 오류가 broad RuntimeError로 숨겨지지 않음을 검증했다.
- S02의 별도 `api/response.py`, `api/boundary.py`가 TD-017의 기존 module 책임과 중복됨을 확인해
  response 기능은 `encoder.py`, request boundary는 `router.py`로 통합하고 두 파일을 제거했다.
- 후속 TD-005 단계는 구현 전에 기존 module 책임과 변경 위치를 대조하고 독립 개념이 아닌 신규
  module을 만들지 않도록 계획 규칙과 구조 검증 테스트를 추가했다.
- `TD-005-S02`를 완료하여 기존 `cmd` 및 신규 `type` 요청을 해석하는 ResponseContext,
  Success/Fail response encoder와 Exception mapping/logging request boundary를 구현했다.
- S02 계약 테스트 13개와 전체 unittest 37개를 통과했으며 `route_message`, handler와 socket 송신
  경로는 변경하지 않아 현재 서버의 legacy API 동작을 유지했다.
- `TD-005-S01`을 완료하여 FailureCode 20개, MotionServerException 계층, 중앙 MRO mapping,
  allowlist 기반 public details, INTERNAL_FAILURE fallback과 PartialFailure 결과 model을 구현했다.
- S01 계약 테스트 9개와 기존 회귀를 포함한 전체 unittest 24개를 통과했으며 API runtime 동작은 변경하지 않았다.
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

- TD-005의 S01-S11 전체 세부 계획에 각 단계의 목표, 주요 변경, 필수 계약, 제외 범위,
  완료 조건과 다음 단계 인계 기준을 추가하고 현재 완료 단계와 다음 시작점을 재개 체크포인트로 기록했다.
- 기존 exception 관련 74개 파일, broad catch 85곳과 generic RuntimeError 42곳을 API Fail, Alarm,
  Fault와 Internal only로 분류하고 기능 경로별 migration boundary와 우선순위를 확정했다.
- EtherCAT SDO 수직 경로를 표준 패턴으로 확정하고 전체 분류에서 발견된 ConfigurationException과
  SdoObjectNotFoundException을 `DEC-019` 계층에 추가했다.
- `DEC-019`의 구체 Exception 계층과 failure code mapping을 확정하고, 구조화 속성 allowlist,
  Python exception chaining 및 별도 PartialFailure 집계 객체 원칙을 추가했다.
- `DEC-019`로 내부 Exception과 API Failure를 중앙 mapping table에서 연결하고 별도
  Failure Definition Registry 없이 FailureCode Enum과 mapper만 사용하는 구조를 확정했다.
- `DEC-018`로 client 대응 기준의 초기 20개 API failure code와 Exception 변환·내부정보 비노출
  원칙을 확정하고 command/argument별 code 증가를 제한했다.
- `DEC-017`로 요청과 같은 type, Success/Fail result, optional request_id 및 data/failure를 사용하는
  공통 API response envelope를 확정하고 기존 응답 필드를 TD-005 migration 대상으로 명시했다.
- API 요청의 실패 결과 명칭을 `Error`가 아닌 `Fail`로 확정하고 관련 계약과 설계 순서의
  표기를 Success/Fail로 통일했다.
- `DEC-016`으로 DiagnosticStatus를 Definition, Source와 History의 조합으로 구성하고
  latching 여부에 따른 acknowledge/resolve/clear 및 재발 규칙을 확정했다.
- Source를 `SERVER`, `BUS`, `AXIS`, `IO` type과 종류별 설정 index의 조합으로 식별하고,
  recovery policy는 RF-005에서 별도 설계하도록 DiagnosticDefinition에서 제외했다.
- `DEC-015`를 개정하여 API 요청 결과를 Success/Fail로, 지속되는 Diagnostic 상태를
  NORMAL/ALARM/FAULT로 분리하고 요청 실패를 Diagnostic level에서 제외했다.
- 관련 문서를 `docs/api/`와 `docs/diagnostic/`으로 분리하고 기존 전수 조사 자료를 분류 전
  중립 inventory인 `diagnostic/error_point_inventory.md`로 변경했다.
- TD-005의 Python 오류 발생·catch 지점을 전수 조사하여 catch 144곳, broad catch 85곳,
  명시적 raise 233곳과 generic `RuntimeError` 42곳을 별도 inventory 문서에 기록했다.
- 오류 inventory는 TD migration 자료로 유지하고, 확정된 장기 계약은 API 결과와 Diagnostic 상태의
  책임에 따라 각각의 문서 폴더에서 관리하는 원칙을 정했다.
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
- `required_non_pdo_od.py`를 추가하여 PDO가 아닌 Motion Server 필수 OD를 별도 관리하는 방향으로 변경.
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
