# Exception 발생·Catch 지점 목표 분류

## 문서 역할

이 문서는 2026-08-21 inventory의 예외 관련 파일 74개, broad catch 85곳과 generic
`RuntimeError` 42곳을 목표 구조로 분류한다. 줄 번호는 조사 시점 기준이며 구현 중 이동할 수 있으므로
파일·함수 책임과 함께 사용한다.

분류 값은 다음 의미를 갖는다.

- `API Fail`: 현재 요청에 Success/Fail response를 반환한다.
- `Alarm`: 운전은 계속 가능하지만 사용자의 확인이나 대응이 필요한 Diagnostic이다.
- `Fault`: 운전이 제한·중단되거나 degraded/unavailable가 되는 Diagnostic이다.
- `Internal only`: client/tool/UI 내부 처리 또는 programming invariant이며 서버 API Diagnostic이 아니다.

한 원인이 요청 실패와 운전 상태 변경을 동시에 만들면 `API Fail + Alarm/Fault`로 분류한다.

## 분류로 확인된 계약 보완

전체 경로를 기존 Exception 계층에 대입한 결과 다음 구체 type이 추가로 필요하다.

```text
MotionServerException
├─ ConfigurationException
└─ DeviceException
   └─ SdoObjectNotFoundException
```

| Exception | FailureCode | 주 사용 경계 |
| --- | --- | --- |
| `ConfigurationException` | `SERVER_NOT_READY` | startup 설정, ESI/IODD/PDO 계약과 실제 장치 불일치 |
| `SdoObjectNotFoundException` | `RESOURCE_NOT_FOUND` | 장치가 OD object/subindex 부재를 명확히 응답한 경우 |

`ConfigurationException` 자체가 startup에서 발생하면 API response를 만들지 않고 Initialization Fault의
원인이 된다. degraded runtime에서 command가 차단될 때의 API code가 `SERVER_NOT_READY`다.

## 확정된 EtherCAT SDO 수직 경로

```text
API handler: request validation과 정상 data 구성
Axis/IO SDO adapter: 논리 selector를 slave index로 변환
SdoAccess/backend: typed Exception 변환과 원인 chaining
API router: FailureMapper를 통한 Fail response 생성
Bus monitor: 실제 운전 영향에 따른 Alarm/Fault 판정
Server client loop: socket send/receive 실패 시 연결 정리
```

| 현재 원인 | 목표 Exception | FailureCode | Diagnostic |
| --- | --- | --- | --- |
| 필수 field 누락 | `InvalidRequestException` | `INVALID_REQUEST` | 없음 |
| field 타입·범위·datatype 오류 | `InvalidArgumentException` | `INVALID_ARGUMENT` | 없음 |
| Axis/IO selector 부재 | `ResourceNotFoundException` | `RESOURCE_NOT_FOUND` | 없음 |
| generic SDO로 ISDU object 접근 | `UnsupportedOperationException` | `UNSUPPORTED_OPERATION` | 없음 |
| mailbox timeout | `CommunicationTimeoutException` | `TIMEOUT` | 단발성 없음 |
| master 연결 끊김 | `CommunicationException` | `COMMUNICATION_FAILED` | Bus Fault |
| OD object/subindex 부재 | `SdoObjectNotFoundException` | `RESOURCE_NOT_FOUND` | 없음 |
| read-only 또는 장치의 명시적 거부 | `DeviceRejectedException` | `DEVICE_REJECTED` | 없음 |
| short payload | `CommunicationException` | `COMMUNICATION_FAILED` | 반복 시 Alarm 후보 |
| 예상하지 못한 codec/programming 실패 | 일반 Python Exception | `INTERNAL_FAILURE` | 운전 영향 별도 판정 |

SDO 요청 실패 하나만으로 Diagnostic을 생성하지 않는다. 실제 disconnect는 Bus Fault로, 반복되는
timeout/short payload는 후속 반복 이상 정책에서 Alarm 승격 여부를 정한다.

## 74개 파일 기능 경로별 분류

아래 표의 파일 수 합계는 기존 inventory의 74개와 일치한다.

| 기능 경로 | 파일 수 | 주 분류 | 목표 처리 |
| --- | ---: | --- | --- |
| `control_panel/axis_control_panel/*` | 7 | Internal only | UI 입력 오류는 로컬 validation, server Fail은 구조화 표시, socket 실패는 reconnect boundary |
| `control_panel/io_control_panel/*` | 2 | Internal only | UI callback boundary 유지, 문자열 `RuntimeError` 대신 client response/transport type 사용 |
| `device/__init__.py`, `device/capabilities.py` | 2 | Fault / Internal only | 사용자 device 이름 오류는 ConfigurationException, capability 불일치는 programming/config invariant |
| `device/cmmt/*` | 7 | Fault / API Fail / Internal only | ESI·PDO·identity 불일치는 startup Fault, runtime SDO는 typed API Fail, raw diagnostic read는 partial 수집 |
| `device/cpx_ap_i_ec/*` | 8 | Fault / API Fail | layout·ESI·module ident 불일치는 startup Fault, AP/SDO runtime 실패는 typed API Fail |
| `device/io_link/*` | 2 | Fault / API Fail | IODD file/config 오류는 startup Fault, runtime 대상/권한 오류는 API Fail |
| `device/pdo_metadata/base.py` | 1 | Fault / Internal only | 사용자 mapping 오류는 ConfigurationException, 코드 내부 ambiguous field는 invariant 검사 |
| `device/virtual_servo_drive/*` | 3 | API Fail / Internal only | mock KeyError/PermissionError를 실장치와 같은 SDO typed Exception으로 변환 |
| `diagnostics/*` | 4 | Internal only | CLI/tool 최상위 또는 항목별 probe boundary로 제품 API/Diagnostic과 분리 |
| `ethercat/*` | 4 | Fault / API Fail / Internal only | startup state 실패는 Fault, runtime transport는 API Fail과 Bus Diagnostic, 순서 위반은 invariant |
| `motion_server/api/*` | 2 | API Fail | parsing/validation을 RequestException 계층으로 변환 |
| `motion_server/app/*` | 3 | Fault / Alarm / Internal only | startup 필수 실패는 Fault, optional metadata 실패는 Alarm 후보, client transport는 연결 boundary |
| `motion_server/config.py` | 1 | Fault | 환경·CLI 설정 오류를 ConfigurationException으로 변환하여 Initialization Fault 생성 |
| `motion_server/control/*` | 4 | API Fail / Alarm 후보 | trajectory/limit 입력은 Request/Limit Exception, device acknowledgement timeout은 OperationTimeoutException |
| `motion_server/device_manager/*` | 4 | API Fail / Fault / Internal only | selector 부재는 ResourceNotFound, binding/unit startup 오류는 ConfigurationException, diagnostics는 partial 수집 |
| `motion_server/handlers/authority/*` | 1 | API Fail / Internal only | authority 거부는 typed Exception, registry mismatch는 programming invariant |
| `motion_server/handlers/command/*` | 8 | API Fail / Partial Failure / Diagnostic 연계 | handler broad catch를 router로 이동하고 다축 실패만 PartialFailure로 집계 |
| `motion_server/handlers/parameter_access/*` | 3 | API Fail / Diagnostic 연계 | EtherCAT/AP/IOL validation, protocol, transport를 분리하고 handler 문자열 응답 제거 |
| `motion_server/handlers/status/*` | 5 | API Fail / Partial Failure | selector/지원 여부는 typed Fail, 여러 field/device 조회는 partial 결과 정책 사용 |
| `motion_server/server.py` | 1 | Fault / Internal only | initialization boundary는 Fault 생성, client socket boundary는 연결 정리, restart/reset control exception 유지 |
| `motion_server/application.py` | 1 | Fault | bootstrap 이후 전체 configuration build의 최상위 boundary에서 예상·미예상 Exception을 typed Initialization Failure로 변환하고 degraded server에 전달 |
| `motion_server/app/startup.py` runtime factory/cleanup | 2 | Fault / Internal only | factory 반환 전 부분 생성 자원을 정리하고 원래 Initialization Failure를 보존하며 cleanup 실패는 내부 traceback으로만 기록 |
| `ros/*` | 2 | Internal only | ROS/UI 입력 오류와 reconnect boundary이며 server Fail/Diagnostic을 구조화 전달 |

## Broad Catch 85곳 판정

| 위치 | 판정 | 목표 |
| --- | --- | --- |
| Axis Panel client 121, connection 50 | 허용 boundary | receive thread/reconnect 최상위에서 log와 연결 상태 갱신; 하위 parsing은 구체화 |
| Axis Panel diagnosis 399 | 허용 UI boundary | callback 실패를 사용자 표시하되 server Exception으로 분류하지 않음 |
| IO Panel client 58 | 허용 boundary | receive thread 종료·reconnect 처리 |
| IO Panel control_panel 526, 705, 715, 728, 772, 846, 859, 896, 909, 965, 1176 | 허용 UI boundary / 구체화 | UI callback은 유지하되 Fail response, conversion과 timeout을 각각 client type으로 구분 |
| CMMT profile 437, 446, 459 | 별도 partial 정책 | statusword/error code/mode read 실패를 field별 typed failure로 수집 |
| CMMT profile 486 | 구체화 | unit exponent optional read의 DeviceAccess/Communication 실패만 fallback하고 Alarm 후보로 전달 |
| Virtual Servo 425 | 구체화 | numeric conversion의 `TypeError/ValueError`만 기본값 처리 |
| diagnostic tool 3개 파일의 4곳 | 허용 tool boundary | 항목별 probe 또는 CLI 최상위 출력; 제품 FailureMapper 사용 금지 |
| PySOEM 120 | 허용 cleanup boundary | connect 실패 원인을 그대로 re-raise하기 전 close 수행 |
| PySOEM 123 | 허용 cleanup boundary | close 중 실패는 원래 connect 실패를 가리지 않도록 log 후 무시 |
| PySOEM 161, 289, 423 | 구체화 | state/DC/identity에서 예상되는 backend 예외만 fallback 또는 partial 처리 |
| SdoAccess 45, 82, 94, 109 | 구체화 | timeout, disconnect, abort와 short payload를 확정된 SDO Exception으로 변환 |
| Startup 245, 268 | 별도 정책 | optional unit metadata만 typed catch 후 Alarm 후보; 허용 fallback 목록 명시 |
| Startup 302, 318, 334 | 제거 | 필수 software/profile/motion limit readback 실패를 Initialization Fault로 상위 전달 |
| Startup 418, 452 | 구체화 | restart clear/request의 지원된 예상 실패만 처리; 축 상태 영향에 따라 Fault 유지 |
| Axis diagnostics 42 | 별도 partial 정책 | 축별 조회 실패를 PartialFailure 항목으로 수집 |
| Axis settings 116, 255, 385, 449 | 상위 이동 | validation/device 실패를 router FailureMapper로 전달 |
| Axis settings 371 | 구체화 | write 후 readback 실패를 DeviceAccess로 기록하고 write 성공과 분리 |
| Axis settings 467 | 별도 partial 정책 | 축별 mode 변경 실패를 PartialFailure로 집계 |
| Axis state 83, 170, 202, 242, 274, 292 | 상위 이동 | stop/reset/restart/enable/disable 실패를 typed Exception으로 router에 전달 |
| IO output write 15 | 상위 이동 | request validation과 runtime 실패를 router로 전달 |
| Jog 31, 45, 74, 91 | 상위 이동 / cleanup | 시작·정지는 router로 전달하고 mode 복구 실패는 원래 결과를 보존하며 log/Diagnostic 판정 |
| Motion 93, 202, 225, 242 | 상위 이동 | command별 문자열 rejection을 공통 FailureMapper로 이동 |
| Trajectory 232 | 상위 이동 | stop 실패를 typed Operation/Device Exception으로 전달 |
| AP 70, 125 | 상위 이동 | handler 문자열 response 제거 |
| AP 275 | 구체화 | SDO step wrapper가 typed cause를 유지하고 step context만 추가 |
| AP 429, 433 | 구체화 | failure details formatting에서 parsing Exception만 처리 |
| EtherCAT parameter 104, 152, 210, 256, 370 | 상위 이동 | 확정된 SDO 수직 경로를 적용 |
| IOL 68, 120 | 상위 이동 | handler 문자열 response 제거 |
| IOL 371 | 구체화 | SDO step wrapper가 typed cause를 유지하고 step context만 추가 |
| IOL 522 | 구체화 | failure details formatting에서 parsing Exception만 처리 |
| Status catalog/input 4개 파일의 4곳 | 상위 이동 | selector/config/device 실패를 router 또는 partial mapper로 전달 |
| Status registry 72 | 상위 이동 | axis selector parsing을 ResourceNotFound/InvalidArgument로 전달 |
| Server 346 | 허용 startup boundary | Exception log와 Initialization Fault 생성 후 degraded server 진입 |
| ROS bridge 795 | 허용 thread boundary | 예상 transport는 reconnect, 예상 밖 Exception은 stack trace 후 안전 중단 |
| ROS control panel 363 | 허용 UI/timer boundary | callback 보호 및 사용자 표시; server Diagnostic 아님 |

Broad catch 허용 목록은 process, connection, thread, UI callback, CLI tool과 cleanup 최상위 경계로
제한한다. 허용 catch도 stack trace, 상태 변경과 재시도 여부를 명시해야 한다.

## Generic RuntimeError 42곳 판정

| 위치 | 목표 |
| --- | --- |
| IO Panel 704, 764, 952, 1182 | client 전용 FailResponse/Authority Exception 또는 UI validation으로 교체; Internal only |
| CMMT profile 195, 202 | identity read 실패는 Communication/DeviceAccess, product mismatch는 ConfigurationException; startup Fault |
| CMMT profile 260, 267, 306 | ESI role/bit size/PDO mapping 불일치를 ConfigurationException으로 변경; startup Fault |
| CPX AP module idents 54 | short payload를 CommunicationException으로 변경 |
| CPX AP module idents 86 | configured/detected module mismatch를 ConfigurationException으로 변경; startup Fault |
| CPX AP parameter access 36 | AP status 거부를 DeviceRejectedException으로 변경 |
| CPX PDO configuration 73, 85, 114 | required OD와 process image 계약 불일치를 ConfigurationException으로 변경; startup Fault |
| CMMT sync probe 124, 135 | CLI tool 실패로 유지 가능; 제품 Exception 계층에 포함하지 않음 |
| MockMaster 43, 64 | lifecycle 순서 위반을 InvalidStateException 또는 test invariant로 변경 |
| PySOEM 85 | 발견 slave 부족을 ConfigurationException으로 변경; startup Fault |
| PySOEM 116, 320, 339, 512 | EtherCAT state timeout/실패를 CommunicationTimeoutException으로 변경; startup/runtime Fault 판정 |
| PySOEM 260 | processdata 호출 순서 위반은 programming invariant; Internal only |
| PySOEM 521 | master 미연결은 CommunicationException으로 변경 |
| PySOEM 544 | pysoem dependency 누락을 ConfigurationException으로 변경; startup Fault |
| SdoAccess 46, 83, 95, 110, 116 | 확정 SDO typed Exception과 short-payload CommunicationException으로 변경 |
| Config 615 | 지원하지 않는 backend 설정을 ConfigurationException으로 변경; startup Fault |
| Setpoint output 127 | PP acknowledgement 실패를 OperationTimeoutException으로 변경; API Fail과 Axis Alarm/Fault 판정 후보 |
| Authority/command/status registry 87, 150, 145 | 코드 registry 불일치 programming invariant; startup의 Internal Failure/Fault 원인 |
| Axis state 230 | restart 후 disable 미도달을 OperationTimeoutException으로 변경; API Fail, 기존 Axis Fault 상태 유지 |
| AP 203 | AP status 실패를 DeviceRejectedException으로 변경 |
| AP 276 | wrapper RuntimeError 제거, typed cause와 step context 유지 |
| IOL 199 | ISDU status 실패를 DeviceRejectedException으로 변경 |
| IOL 372 | wrapper RuntimeError 제거, typed cause와 step context 유지 |

## 나머지 Typed Raise/Catch 분류 규칙

| 현재 패턴 | 대상 위치 | 목표 |
| --- | --- | --- |
| API 입력의 `ValueError/TypeError` | decoder, validator, command, parameter/status handler | InvalidRequest/InvalidArgument/ResourceNotFound/LimitViolation로 의미별 분리 |
| 환경·파일·ESI·IODD·PDO 구성 오류 | config와 device catalog/layout/profile | ConfigurationException, startup Fault |
| OD/PDO catalog `KeyError` | CMMT/CPX metadata와 Virtual OD | 사용자 설정 경계에서는 ConfigurationException, runtime SDO에서는 SdoObjectNotFound, 불가능한 내부 lookup은 invariant |
| Virtual OD `PermissionError` | od_bridge | DeviceRejectedException으로 backend parity 확보 |
| socket `OSError/ConnectionError` | server, clients, ROS | 연결 boundary에서 close/reconnect; 송신 불가 상태이므로 API Fail 생성 시도 금지 |
| client `TimeoutError` | IO Panel response wait | client transport timeout으로 유지하고 UI에 Fail timeout 표시; 서버 Diagnostic 아님 |
| JSON decode 실패 | server/client/ROS | server request이면 INVALID_REQUEST 후 연결 유지, client/ROS 수신이면 protocol log와 reconnect 정책 |
| numeric conversion fallback catch | panels, catalog parser, unit conversion | 사용자 입력이면 로컬 validation, optional display parser면 narrow catch, invariant는 숨기지 않음 |
| lifecycle control exception | server reset/restart | 정상 control flow 전용으로 유지하며 FailureMapper 대상에서 제외 |

## Diagnostic 판정 원칙

- request validation, 대상 부재와 장치의 정상적인 거부는 API Fail만 만든다.
- startup에 필요한 configuration, identity, PDO와 필수 OD readback 실패는 Initialization Fault다.
- 실제 bus disconnect 또는 EtherCAT operational state 상실은 Bus Fault다.
- drive statusword/error register가 운전을 제한하면 Axis Fault다.
- 선택 metadata read 실패나 반복되는 일시적 protocol 이상은 Alarm 후보이며 단발 실패는 log/API Fail만 남긴다.
- handler는 Diagnostic을 직접 만들지 않고 device/bus/runtime 상태 판정 계층에 원인과 상태를 전달한다.
- programming invariant는 Diagnostic으로 위장하지 않는다. 최상위에서 Internal Failure를 기록하고
  runtime 안전성이 보장되지 않으면 server Fault/degraded 전환을 별도로 수행한다.

## Migration 우선순위

1. 공통 Exception/FailureMapper와 API router boundary를 구현한다.
2. EtherCAT SDO 및 Mock/PySOEM backend parity를 구현한다.
3. AP와 IO-Link protocol 경로를 같은 typed pattern으로 변환한다.
4. command/status handler broad catch를 제거하고 다축/다장치 partial 집계를 적용한다.
5. startup ConfigurationException과 Initialization Fault 경계를 TD-018/TD-023과 연결한다.
6. Control Panel과 ROS가 새 Success/Fail 및 Diagnostic 계약을 사용하도록 migration한다.
7. broad catch allowlist와 AST 기반 누락 검사를 CI에 추가한다.
