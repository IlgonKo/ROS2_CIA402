# RF-002 Low-code Reference Client

## 사용자 가치

Node-RED 같은 low-code 환경과 최소 Python 코드에서 Control Panel 없이 Motion Server를 사용할 수 있게 한다.

## 구현 범위

- TCP JSON-lines 연결, 연결 해제와 재연결을 처리한다.
- request/response correlation과 비동기 feedback 분리를 예제로 제공한다.
- authority acquire/release, feedback, axis motion, I/O output과 parameter access를 포함한다.
- Python은 재사용 가능한 최소 client 모듈만 제공한다. scenario별 동작을 Python script로 중복
  구현하지 않는다.
- 최소 client 모듈은 연결 lifecycle, JSON-lines framing, request id correlation, response/feedback 분리,
  timeout과 연결 단절만 담당한다.
- Node-RED는 공통 연결/request/feedback node와 scenario별 flow를 제공하며 Python client와 동일한
  공개 API 및 correlation 계약을 사용한다.

## Python Reference Client 경계

- 기존 Control Panel용 `motion_server_client` package를 확장하지 않는다. 새 Python package는
  `reference_clients/python/motion_server_reference_client` 아래에 독립적으로 구성하고 자체
  `pyproject.toml`과 README를 제공한다.
- 공통 client 모듈은 임의의 공개 API message를 `request()`로 전송할 수 있어야 하며 특정 축이나
  장치 구성에 종속되지 않는다.
- 공개 요청 인터페이스는 동기 `request()`로 유지하되 여러 application thread의 동시 호출을
  지원한다. 송신은 lock으로 JSON 행 단위로 직렬화하고 각 호출은 고유 `request_id`로 독립 대기한다.
- Python client는 호출자의 message를 복사한 뒤 client session별 고유 prefix와 단조 증가 번호를
  조합한 문자열 `request_id`를 자동 부여한다. 원본 message는 변경하지 않는다.
- 같은 client instance는 재연결 후에도 번호를 계속 증가시킨다. 호출자가 `request_id`를 직접
  지정하면 내부 correlation과의 충돌을 막기 위해 요청을 전송하기 전에 거부한다.
- 수신 thread는 correlation된 response를 해당 요청에 전달하며 비동기 `async/await` API는 초기
  범위에서 제외한다.
- 기본 request timeout은 5초이며 client 생성 인자와 개별 `request(..., timeout=...)`에서 변경할 수
  있다. timeout된 요청은 pending 목록에서 제거하고 나중에 도착한 해당 response는 폐기한다.
- request timeout만으로 TCP 연결을 끊지 않는다. `system/bus/reconnect`, axis restart 등 장시간 명령은
  caller가 명령 특성에 맞는 더 긴 timeout을 지정한다.
- 서버의 `Fail` envelope는 정상적으로 correlation된 API response이므로 dict 그대로 반환하고
  scenario가 `result`, Failure code와 detail을 판단한다.
- Python exception은 미연결, 연결 단절, timeout과 잘못된 client 사용처럼 client 자체에서 발생한
  실패에만 사용한다. 서버 Failure code별 Python exception 계층은 만들지 않는다.
- 비동기 `system/feedback`을 request response와 분리하여 전용 queue에 저장하고 application은
  `get_feedback()`으로 소비한다.
- feedback queue는 크기를 제한하며 가득 차면 가장 오래된 feedback을 제거한 뒤 최신 feedback을
  저장한다. request response는 별도 correlation 경로에서 처리하므로 폐기 대상이 아니다.
- feedback queue 기본 크기는 100개이며 `feedback_queue_size` client 생성 인자로 조정할 수 있다.
  이 값은 reference client의 소비 정책이므로 Motion Server 설정에는 추가하지 않는다.
- TCP 수신 thread에서는 사용자 callback을 직접 실행하지 않는다. 느린 처리, callback 예외 또는
  callback 내부의 동기 `request()`가 response 수신을 막지 않도록 통신과 사용자 처리를 분리한다.
- 연결이 끊어지면 응답을 기다리던 모든 요청은 connection failure로 완료하고 자동 재전송하지 않는다.
- 재연결 중 새 요청은 전송하지 않고 연결이 복구된 뒤 application이 새 요청으로 명시적으로 실행한다.
- `start()`는 background connection thread를 시작하고 최초 연결 실패 또는 운전 중 단절 후 고정 1초
  간격으로 재연결을 시도한다. `stop()`은 재연결을 중단하고 socket을 정리한다.
- 미연결 상태의 `request()`는 즉시 connection failure를 반환한다. application이 연결을 기다릴 때는
  `wait_connected(timeout=...)`을 사용한다. 재연결 주기는 client/server 설정으로 확장하지 않는다.
- 연결 단절 시 feedback queue를 비우고 재연결 후 새로 수신한 feedback만 제공한다. 단절 전 마지막
  상태 보존이 필요한 application은 scenario에서 별도로 관리한다.
- 현재 연결 상태와 마지막 연결 오류는 `is_connected`와 `last_error`로 조회한다. 연결 lifecycle을
  가짜 `system/feedback` message로 만들어 feedback queue에 넣지 않는다.
- 연결 단절로 해제된 command authority는 client가 자동 복원하지 않는다. 재연결 후 application이
  server 상태를 확인하고 `system/authority/request`를 명시적으로 다시 실행한다.
- authority, axis motion, I/O와 parameter access의 실행 순서 및 판단은 Python client 외부 application
  또는 Node-RED scenario flow가 소유한다.
- client 모듈은 저장소 밖의 사용자 application에서도 독립적으로 가져다 쓸 수 있을 만큼 의존성을
  작게 유지한다.

## Node-RED 경계

- Node-RED package는 `reference_clients/node_red/node-red-contrib-motion-server` 아래에 Python과
  독립된 installable package로 구성한다.
- Dashboard와 graph는 유지 관리되는 `@flowfuse/node-red-dashboard`의 `ui-chart`를 사용한다.
  legacy `node-red-dashboard`는 지원 대상과 dependency에 포함하지 않는다.
- 초기 Custom Node는 `Motion Server Connection`, `Motion Server Request`, `Motion Server Feedback`,
  `Motion Server Connection Status`의 4종으로 구성한다.
- Connection은 Node-RED Config Node로 구현하고 endpoint, 하나의 TCP 연결, 연결 lifecycle, 1초
  재연결과 request correlation을 소유한다. Request는
  API message를 전송하고 response를 출력하며 Feedback과 Connection Status는 각각 주기 feedback과
  연결 lifecycle event를 분리하여 출력한다.
- 같은 Connection Config를 선택한 모든 Request, Feedback과 Connection Status node는 같은 TCP 연결,
  command authority, request counter와 재연결 상태를 공유한다. Motion Server가 여러 대이면 서버마다
  별도 Connection Config를 생성한다.
- Connection Config는 Name, Host(기본 `127.0.0.1`), Port(기본 `15000`)와 Default Request
  Timeout(기본 5초)을 설정한다. 확정된 1초 재연결 주기는 UI 설정으로 노출하지 않는다.
- Request Node는 Name, Connection Config와 optional Request Timeout을 설정한다. timeout이 비어 있으면
  Config 기본값을 사용하고 값이 있으면 해당 Node에서만 override한다. timeout은 `msg` property로 받지
  않는다. Feedback과 Connection Status Node는 Name과 Connection Config만 설정한다.
- Request 입력은 `msg.payload.cmd`를 유일한 command 식별자로 사용하고 별도 `msg.topic`을 요구하지
  않는다. caller가 설정한 `msg.topic`과 그 밖의 message property는 response에서도 그대로 보존하며
  Request node가 topic을 생성하거나 덮어쓰지 않는다.
- Request는 2개 출력을 가진다. 첫 번째 출력은 서버의 `Success`와 `Fail` API response를 모두
  전달하고 flow가 `msg.payload.result`로 분기한다. 두 번째 출력은 미연결, 연결 단절과 request timeout
  같은 client transport failure만 전달한다. 서버 `Fail`을 transport failure 출력으로 보내지 않는다.
- Request는 원본 request payload의 별도 복사본을 출력 message에 보관하지 않는다. 첫 번째 출력은
  `msg.payload`를 서버 response로 교체하고, caller의 topic과 그 밖의 사용자 property만 보존한다.
- 두 번째 출력의 `msg.payload`는 `type="motion-server/client-error"`, `code`, `message`, `request_id`,
  `command`만 포함한다. 초기 client error code는 `not_connected`, `connection_lost`,
  `request_timeout`, `invalid_client_request`로 제한한다.
- Feedback은 `msg.topic="system/feedback"`, Connection Status는
  `msg.topic="motion-server/connection"`을 사용한다.
- Connection Status는 node 시작 시 현재 상태를 한 번 출력하고 이후 `connected` 값이 실제로 변경될
  때만 출력한다. 1초 재연결 시도마다 같은 disconnected event를 반복하지 않는다.
- Connection Status payload는 `connected: bool`과 `last_error: str`만 제공한다. `connecting`이나
  `retrying` 같은 추가 API state는 만들지 않고 세부 진행은 Node 자체의 status 색상으로 표현한다.
- Basic 상태 조회, authority, Axis, I/O, parameter access와 Virtual I/O simulation은 scenario별
  Subflow/Flow에서 공통 node를 조합하여 표현한다.
- scenario별 순서, 안전 조건, 사용자 Inject/Button과 결과 표시는 flow가 소유하며 공통 node에
  업무 로직을 넣지 않는다.
- 초기 범위에서 API command마다 Custom Node를 만들지 않는다. 반복 사용성이 확인된 Subflow만
  후속 검토를 거쳐 정식 기능 Node로 승격한다.

## 범위 제외

- 기존 Axis/IO Control Panel client의 새 reference transport 이관은 포함하지 않는다. 공통화가
  필요하면 새 package 안정화 후 별도 TD에서 검토한다.
- 장비 문서와 capture가 있는 기존 `Reference` 폴더의 역할과 내용은 변경하지 않는다.
- 모든 API를 Python 전용 method로 감싸는 생산용 범용 SDK는 만들지 않는다.
- trajectory 생성, application 상태 관리, 자동 recovery 정책과 프로젝트별 업무 로직은 포함하지 않는다.
- 특정 PLC/SCADA 제품별 connector는 별도 기능으로 다룬다.

## 공통 및 Scenario Flow 구성

- 공통 기반 Flow는 `01_connection_and_status.json`과 `02_command_authority.json`으로 구성한다.
- `01_connection_and_status.json`은 유일한 공통 Connection Config와 connection lifecycle,
  server/axes/I/O status 및 주기 feedback을 제공한다.
- `02_command_authority.json`은 공통 Connection Config를 재사용하여 authority
  request/status/release와 재연결 후 명시적 재요청을 제공한다.
- 기능 Scenario Flow는 다음 `03`~`06`으로 구성한다.
- `03_axis_control.json`: axis enable/disable, absolute/relative move, stop, status와 Fail 처리를 제공한다.
  Axis Control Panel과 유사하게 feedback으로 모든 축의 actual position과 actual velocity를 시간축
  graph로 표시하고 axis별 series를 구분한다. 모든 feedback을 사용하고 각 series는 최근 500개
  sample을 유지한다. 연결 단절 시 graph를 초기화하고 재연결 후 새 feedback부터 다시 표시한다.
  축 수는 첫 feedback 배열 길이로 확정하며 axis status의 이름을 사용하고 이름이 없으면
  `Axis 0`, `Axis 1` 형식으로 표시한다.
- `04_io_control.json`: input read, output write와 I/O status를 제공한다.
- `05_parameter_access.json`: Axis EtherCAT 및 I/O EtherCAT/AP/IO-Link parameter access와 지원하지
  않는 요청의 Fail 처리를 제공한다.
- `06_virtual_io_simulation.json`: Simulation API availability, DI/AI/IO-Link input write/read/reset과
  기존 I/O feedback 반영을 보여준다.
- 각 파일은 별도로 관리하고 필요한 기능만 선택하여 import할 수 있게 유지한다. 다만 `01`을 먼저
  import하며 `02`~`06`은 `01`이 소유한 하나의 Connection Config를 참조한다. 이를 통해 여러 Flow를
  함께 사용할 때 중복 TCP 연결과 command authority 충돌을 방지한다.
- 상태 변경, motion과 output command는 수동 Inject/Button으로만 실행한다. flow import 또는 deploy로
  자동 실행하지 않으며 연결과 feedback 구독만 자동으로 시작한다.

## 검증 계획

- server restart와 network disconnect 후 재연결을 검증한다.
- server가 없는 상태의 `start()`, 고정 1초 재시도, `wait_connected()`와 `stop()` 중단을 검증한다.
- 단절 시 feedback queue가 비워지고 `is_connected`/`last_error`가 갱신되며, 재연결 후 새 feedback만
  전달되는지 검증한다.
- 연결 단절 시 모든 미완료 요청이 실패하고 재연결 후 자동 재전송되지 않는지 검증한다.
- 재연결만으로 command authority를 다시 요청하지 않으며 명시적 authority request 전까지
  상태 변경 명령이 실행되지 않는지 검증한다.
- 하나의 client 연결에서 response correlation과 비동기 feedback 분리가 동시에 유지되는지 검증한다.
- 여러 thread의 동시 `request()`가 서로 다른 response를 정확히 받고 송신 JSON 행이 섞이지 않는지
  검증한다.
- 자동 `request_id`의 session prefix, 동시 증가, 재연결 후 연속성과 caller 지정 거부를 검증한다.
- 기본/개별 timeout, pending 제거, 지연 response 폐기와 timeout 이후 연결 재사용을 검증한다.
- 서버 `Fail`은 반환되고 client 통신·사용 실패만 Python exception이 되는지 검증한다.
- feedback 소비가 느리거나 application 처리에서 예외가 발생해도 response 수신이 계속되는지 검증한다.
- feedback queue 포화 시 가장 오래된 feedback만 제거되고 최신 feedback과 모든 request response가
  유지되는지 검증한다.
- 기본 queue 크기 100개와 생성 인자로 지정한 크기가 각각 적용되는지 검증한다.
- Node-RED scenario flow가 공통 연결/request/feedback node를 재사용하는지 검증한다.
- `01`만 Connection Config를 소유하고 `02`~`06`이 이를 공통으로 참조하며, 모든 Flow가 deploy만으로
  상태 변경 명령을 실행하지 않는지 검증한다.
- Axis flow가 feedback의 전체 축 actual position/velocity를 axis별 graph series로 표시하는지 검증한다.
- graph의 500 sample 제한, disconnect 초기화, reconnect 재시작과 axis name fallback을 검증한다.
- clean Node-RED 환경에서 FlowFuse Dashboard dependency 설치 후 Axis chart가 추가 수작업 없이
  구성되는지 검증한다.
- 4종 공통 Custom Node의 lifecycle, correlation과 message routing을 자동 또는 Node-RED test helper로
  검증한다.
- 같은 Config를 사용하는 node의 단일 socket/authority 공유와 서로 다른 Config 사이의 연결·상태
  격리를 검증한다.
- Config 기본값과 Request Node별 timeout override 및 다른 Node의 기본 timeout 유지 여부를 검증한다.
- Request가 `msg.payload.cmd`만 사용하고 caller topic/property를 보존하며, unsolicited node만 확정된
  topic을 출력하는지 검증한다.
- Connection Status의 initial snapshot, 상태 변경 1회 출력과 동일 상태 재시도 억제를 검증한다.
- 서버 Success/Fail은 Request 첫 번째 출력으로, client transport failure만 두 번째 출력으로
  routing되는지 검증한다.
- Request 원본을 복제하지 않고 caller property를 보존하며 client error가 확정된 최소 필드와 code를
  제공하는지 검증한다.
- Python client 자동 테스트와 Node-RED flow smoke test가 동일한 공개 API 및 correlation 계약을
  사용하는지 검증한다.
- clean environment에서 import/install 절차와 예제 payload를 검증한다.
- Python과 Node-RED package가 각각 독립적으로 설치되며 기존 Control Panel import 경로에 영향을 주지
  않는지 검증한다.

## 세부 구현 계획

### S01 Package Skeleton 및 계약 고정

- `reference_clients/python`과 `reference_clients/node_red/node-red-contrib-motion-server` package
  skeleton, metadata와 README를 생성한다.
- 확정된 Python public API, Node-RED node registration name, message와 error contract를 테스트에서
  참조할 수 있게 고정한다.

### S02 Python 최소 Client

- connection thread, JSON-lines byte buffering, 자동 request id, thread-safe send와 pending correlation을
  구현한다.
- feedback queue, oldest-drop, timeout, disconnect/reconnect, authority 비복원과 raw Success/Fail 반환을
  자동 테스트한다.

### S03 Node-RED Connection Runtime

- Config Node가 공유 socket, request counter, pending response, feedback와 connection-status subscriber를
  관리하게 한다.
- 1초 재연결, disconnect pending failure, timeout과 late-response 폐기를 Node-RED test helper로 검증한다.

### S04 Node-RED 공통 Node

- Request, Feedback, Connection Status의 runtime 및 editor UI를 구현한다.
- 두 Request 출력, caller property/topic 보존, client error payload와 initial/change-only connection status를
  검증한다.

### S05 공통/Scenario Flow 및 Dashboard

- 공통 기반 `01`·`02`와 기능 Scenario `03`~`06`을 별도 example flow로 작성하되 하나의
  Connection Config를 공유한다.
- Axis flow에 FlowFuse Dashboard 기반 전체 축 position/velocity 500-sample graph와 disconnect reset을
  구현한다.

### S06 설치 및 Smoke 검증

- Python editable/clean install과 Node-RED local package install 절차를 검증한다.
- mock Motion Server를 대상으로 Python correlation/reconnect 및 Node-RED flow contract smoke test를
  수행한다.

### S07 완료 리뷰

- RF 계약, 구현, 자동 테스트와 사용자 문서를 항목별로 대조하고 범위 확장이 없는지 확인한다.
- 전체 Python unittest, Node package test, compile과 whitespace 검사를 통과한 뒤 완료 증거와 worklog를
  갱신하고 RF-002를 `complete`로 변경한다.

## 완료 증거

- 독립 Python package에 thread-safe request correlation, feedback queue, timeout, 연결 단절 및 1초
  재연결을 구현하고 자동 테스트 8개를 추가했다.
- 독립 Node-RED package에 Connection Config, Request, Feedback, Connection Status 4종을 구현하고
  lifecycle/correlation/routing 자동 테스트 6개를 추가했다.
- `01` connection/status와 `02` authority는 공통 기반 Flow로, `03`~`06`은 기능 Scenario Flow로
  구성했다. `01`만 Connection Config를 소유하고 나머지 Flow는 이를 공유한다.
- Axis Flow에 첫 feedback 기준 축 수 고정, 축별 actual position/velocity series, 500 sample 제한과
  연결 단절 시 graph 초기화를 구현했다.
- mock Motion Server에서 Python client의 `system/server/status` Success와 `system/feedback` 수신을
  확인했다.
- 전체 Python unittest 327개와 Node-RED test 6개가 통과했고 production dependency audit 결과는
  취약점 0개였다. Python wheel과 Node-RED tarball을 각각 깨끗한 대상 폴더에 설치하여 import/install을
  확인했으며 source compile, Node syntax와 whitespace 검사도 통과했다.
