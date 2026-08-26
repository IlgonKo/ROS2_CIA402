# RF-005 Runtime Fault 및 Recovery 모델 완성

## 목표

runtime fault의 상태, 사용자에게 보이는 진단 정보와 reset/reconnect/restart의 책임 경계를 일관되게 만든다.

## 구현 범위

- normal, initialization-error, bus-disconnected와 fault 상태 및 전이를 정의한다.
- source별 `fault_reset`, `system/bus/reconnect`와 process restart의 허용 조건을 정한다.
- PySOEM Axis restart의 완료 감지, timeout, EtherCAT 재연결과 복구 완료 경계를 정의한다.
- recovery 전후 authority 소유권과 기존 TCP client 유지 정책을 정의한다.
- 실패한 복구와 반복 오류의 degraded behavior를 정의한다.
- 공개 acknowledge API 없이 fault-reset 대상에 속한 latching Fault를 내부 acknowledge하고,
  resolve 이후 clear하는 처리를 구현한다.
- bus reconnect가 해결한 Initialization Fault는 reconnect에 포함된 내부 acknowledge와 함께
  clear한다.

## 현재 구현 상태 점검

TD-005와 TD-018에서 다음 기반은 이미 구현되었다.

- `DiagnosticManager`의 detect, resolve, acknowledge와 latching/non-latching clear 계약
- Server/Bus/Axis source와 Initialization, WKC, Axis Fault/Warning Diagnostic
- runtime 없는 initialization-error degraded server와 제한 API
- `system/server/reset`, `system/server/restart`, `system/bus/reconnect` 요청 및 기존 3단계 복구 범위 검증
- server reset의 새 `DiagnosticManager`와 bus reconnect의 기존 `DiagnosticManager` 유지라는 기존 계약
- reconnect 성공 시 Initialization Fault resolve-only 처리
- reconnect 시 listener/client까지 종료하고 runtime을 재구성하는 기존 lifecycle
- Mock Axis restart 직후 OD readback과 parameter cache/control projection 동기화

RF-005에서는 기반 객체는 재사용하되, 위의 기존 reset/reconnect lifecycle을 확정 계약에 맞게
변경하고 다음 잔여 계약을 구현한다.

1. source별 Fault Reset API와 resolved latching Fault clear
2. 운전 중 EtherCAT transport 단절을 typed Bus recovery 상태로 전환하는 경계
3. Bus reconnect 성공·실패와 반복 요청의 상태 전이 및 자동 테스트
4. PySOEM Axis restart의 완료·timeout·복구 완료 통지 경계
5. recovery 완료 전에 TD-025 parameter refresh를 동기 호출하는 내부 계약

## 구현 전 결정 필요 사항

### 확정: 공통 Runtime 상태 모델

```python
class ServerRuntimeState(Enum):
    NORMAL = "normal"
    INITIALIZATION_ERROR = "initialization_error"
    BUS_DISCONNECTED = "bus_disconnected"
    FAULT = "fault"
```

- `ServerSession`이 상태를 소유하고 API gating과 recovery 경로의 기준으로 사용한다.
- `InitializationStatus`는 초기화 결과와 실패 상세만 담당하며 공통 runtime 상태와 분리한다.
- `NORMAL`은 연결된 정상 runtime, `INITIALIZATION_ERROR`만 `runtime=None`을 사용한다.
  `BUS_DISCONNECTED`는 기존 runtime과 cache/topology를 유지하되 cyclic I/O와 장치 접근을
  중단하고, `FAULT`는 연결된 runtime을 유지하되 정상 motion command를 제한한다.
- `DiagnosticLevel.FAULT`는 개별 Diagnostic 심각도, `ServerRuntimeState.FAULT`는 Fault 때문에
  운전이 제한된 서버 집계 상태다.
- 상세 근거와 영향은 `DEC-026`을 따른다.

### 확정: WKC Fault와 Transport Disconnect

- 연속 WKC mismatch는 `FAULT`로 전환하고 cyclic exchange를 유지하되 정상 motion
  command를 제한한다. 조건 정상화 시 Diagnostic은 resolve하지만 `fault_reset`으로 clear되기
  전까지 `FAULT`를 유지한다.
- transport exception/연결 유실은 `BUS_DISCONNECTED`로 전환하고 cyclic exchange를 중단한다.
  AxisRuntime과 cache/control/topology는 유지하며 EtherCAT transport 연결만 닫는다.
- 연속 WKC mismatch가 발생하면 slave transport 상태를 추가 확인한다. transport가 살아 있으면
  WKC Fault로 유지하고, slave가 사라졌으면 transport exception과 같은 `BUS_DISCONNECTED`로
  전환한다.
- Bus reconnect는 같은 AxisRuntime에서 transport와 device/process data를 다시 초기화한다.
  자동 재시도는 하지 않고 사용자 명령으로 시작하며, `NORMAL` 상태에서는 reconnect를 거부한다.
- Bus 상태와 TCP 연결은 연동하지 않는다. disconnect/reconnect 동안 기존 TCP listener와 client를
  유지하고 Server process restart에서만 TCP 연결을 종료한다. 상세 근거는 `DEC-027`을 따른다.

### 확정: 공개 Fault Reset API

- 공개 `acknowledge` 명령과 `diagnostic_id` 입력은 사용하지 않는다.
- `system/server/reset`은 제거하고 Server 전체 복구는 `system/server/restart`로 통일한다.
- `system/server/fault_reset`, `system/bus/fault_reset`,
  `system/axis/fault_reset`, `system/axes/fault_reset`을 사용한다.
- 명령으로 지정한 대상의 모든 활성 Fault를 내부 acknowledge 대상으로 하며 Alarm은 제외한다.
  선택하지 않은 다른 Axis/IO 대상의 Fault는 변경하지 않는다.
- Axis Fault Reset은 CiA 402 recovery, Bus reconnect는 transport recovery와 acknowledge를 함께
  수행한다. 내부 `acknowledged_at`과 latching clear 계약은 유지한다.
- `system/io/fault_reset`의 장치 recovery 확장은 RF-003이 담당한다. 상세 근거는 `DEC-028`을
  따른다.

### 확정: Recovery 실행과 완료 경계

- Bus reconnect와 Axis restart는 모든 recovery 단계가 완료된 뒤 Success/Fail을 반환하는 동기
  명령으로 구현한다. Server restart만 응답 후 process를 재시작한다.
- 별도 recovery worker는 만들지 않는다. recovery handler가 실행되는 동안 같은 server loop의
  다른 API 요청 처리는 일시 정지한다. TCP socket과 command authority는 유지되며 recovery가
  끝난 뒤 기존 client 요청 처리를 재개한다.
- Fault 조건이 resolve되어도 fault-reset으로 clear되기 전까지 관련 runtime/device의
  `FAULT`와 motion 제한을 유지한다.
- recovery 실패 Diagnostic은 `BUS_CONNECTION_LOST`, `BUS_RECONNECT_FAILED`,
  `AXIS_RESTART_FAILED`로 구분한다. `PARAMETER_REFRESH_FAILED`는 TD-025가 소유한다.
- TD-025 연결은 범용 event가 아니라 동기
  `refresh_after_recovery(runtime, recovery_type, affected_axes)` 호출을 사용한다. Bus reconnect는
  모든 Axis, Axis restart는 해당 Axis를 대상으로 하며 refresh 성공 후에만 recovery를 완료한다.
- 동기 parameter refresh는 PRE-OP에서 완료한다. OP 진입 후 blocking SDO read를 연속 수행하여
  cyclic PDO watchdog을 발생시키지 않는다.
- OP 진입 후 expected WKC와 일치하는 process data가 3회 연속 확인되어야 recovery를 완료한다.
  입력 PDO만 수신되고 출력 PDO가 승인되지 않는 상태는 reconnect Success로 처리하지 않는다.
- 공통 설정 기본 timeout은 Bus reconnect 10초, Axis restart 30초로 한다.
- timeout은 backend가 지원하는 connect/OP 전이에도 남은 시간을 전달한다. 단, worker 없이
  실행하므로 이미 진입한 native/SDO 호출을 강제로 중단하는 hard timeout은 보장하지 않는다.
- startup Bus 연결 실패는 runtime을 새로 구성하고 운전 중 단절은 기존 AxisRuntime에서
  transport만 reconnect한다. 상세 계약은 `DEC-029`를 따른다.

### 확정: Fault 상태의 API 허용과 Authority

- Bus WKC Fault에서는 전체 motion command를 제한하되 status, authority, fault reset,
  bus reconnect, server restart와 안전 명령인 stop/disable을 허용한다.
- Axis Fault에서는 Fault가 발생한 Axis만 motion command를 제한하고 정상 Axis는 계속 운전할
  수 있다. 해당 Axis의 stop/disable/fault-reset과 장치 recovery인 axis restart는 허용한다.
- 모든 fault-reset, bus reconnect와 server restart는 command authority를 요구한다.
- Bus disconnect 및 initialization-error에서도 authority request/status/release는 허용한다.

### 확정: PySOEM Axis Restart 완료 경계

- Axis restart 동안 전체 Bus motion command를 제한한다.
- restart command를 쓰기 전에 모든 Axis의 homing/trajectory를 중단하고 실제 위치를 hold한 뒤
  전체 Axis를 Operation Enabled에서 해제한다. recovery 후에도 자동으로 enable하거나 이전
  trajectory를 재개하지 않는다.
- 대상 slave 재발견, Bus process data 재구성과 parameter refresh 완료까지를 restart 완료로 본다.
- 완료 전에는 정상 Axis를 포함한 motion command를 허용하지 않는다.
- parameter refresh 책임은 TD-025가 담당하며 timeout과 실패는 RF-005 recovery Fault로 처리한다.

## 구현 전 결정 상태

RF-005 구현을 시작하기 위해 추가로 결정해야 하는 사양은 없다. 다음 항목은 기존 결정으로부터
도출되는 구현 규칙으로 적용한다.

- `system/server/status`와 `system/bus/status`는 공통 `runtime_state`를 반환한다.
- Bus/Server Fault가 전체 운전을 막을 때 `ServerRuntimeState.FAULT`를 사용한다. Axis Fault는
  공통 runtime을 유지하고 Diagnostic source 기준으로 해당 Axis만 제한한다.
- fault-reset은 기존 Success/Fail 공통 응답을 사용한다. 조건이 아직 해제되지 않은 Fault를
  acknowledge해도 명령 자체는 성공이며, Fault와 운전 제한은 resolve될 때까지 유지된다.
- `system/axes/fault_reset` 중 한 Axis의 장치 recovery가 실패하면 요청 전체를 Fail로 반환하고,
  성공한 Axis의 실제 recovery 결과는 되돌리지 않는다. 실패한 Axis Fault는 유지한다.
- 동기 recovery 명령이 실행 중이면 같은 recovery를 중첩 실행하지 않고 Fail로 거부한다.
  별도 worker를 사용하지 않으므로 recovery 호출이 반환될 때까지 status와 안전 명령을 포함한
  다른 API 처리도 일시 정지한다. socket과 authority 보존은 요청 동시 처리 보장을 뜻하지 않는다.
- TD-025가 완성되기 전에는 현재 축 parameter refresh 경계를 adapter로 호출한다. RF-005는
  recovery 완료 시점과 대상 전달을 소유하고, 범용 cache validity와 refresh 구현은 TD-025가
  교체·확장한다.

## 세부 구현 계획

### S01 Runtime 상태 모델과 API 계약 전환 — 완료

- `ServerRuntimeState`를 추가하고 `ServerSession`이 상태와 유효한 전이를 소유하게 한다.
- server/bus status에 `runtime_state`를 노출한다.
- `system/server/reset`을 제거하고 초기화 recovery scope를
  `BUS_RECONNECT < SERVER_RESTART`로 단순화한다.
- 기존 Axis/Axes reset을 fault-reset으로 이름을 바꾸고 Server/Bus fault-reset을 추가한다.
- Bus reconnect 10초, Axis restart 30초 timeout을 공통 configuration model에 추가한다.
- API catalog, validator, handler registry와 기존 테스트를 새 계약으로 전환한다.

구현 결과:

- `ServerSession` 소유의 typed `ServerRuntimeState`와 상태 응답 필드를 추가했다.
- recovery timeout 설정과 양수 검증을 추가했다.
- Server reset lifecycle을 삭제하고 recovery scope를 2단계로 단순화했다.
- Axis/Axes fault-reset API 및 Control Panel 호출부를 새 명칭으로 전환했다.
- Server/Bus fault-reset API는 catalog에 등록했으며 실제 Diagnostic 처리는 S02에서 연결한다.
- 전체 unittest 239개가 통과했다.

### S02 Diagnostic Fault Reset과 운전 제한 — 완료

- `DiagnosticManager`에 source 또는 선택 Axis 집합의 활성 Fault만 acknowledge하는 연산을 추가한다.
- Server/Bus/Axis/Axes fault-reset handler와 CiA 402 Axis Fault Reset을 결합한다.
- Bus/Server Fault의 전체 motion 제한과 Axis Fault의 해당 축 한정 제한을 validator에 적용한다.
- WKC 연속 mismatch의 detect/resolve가 runtime 상태 및 latching clear 조건과 일치하도록 연결한다.
- status, authority, stop/disable 및 recovery 명령의 상태별 허용 행렬을 자동 테스트한다.

구현 결과:

- `DiagnosticManager`에 source/source type별 활성 Fault 조회와 일괄 acknowledge 연산을 추가했다.
- Server/Bus/Axis/Axes fault-reset을 실제 Diagnostic 수명 주기 및 Axis CiA 402 Fault Reset과
  연결했다. Alarm과 선택되지 않은 장치의 Fault는 변경하지 않는다.
- WKC mismatch Fault가 `ServerRuntimeState.FAULT`를 설정하고, 조건 resolve와 fault-reset이 모두
  끝날 때까지 전역 motion 제한을 유지하도록 구현했다.
- Server/Bus Fault에서는 전체 motion을 제한하고 status, authority, stop/disable 및 recovery를
  허용한다. Axis Fault에서는 해당 Axis만 같은 기준으로 제한한다.
- 조건이 남아 있는 Fault Reset은 acknowledge만 기록하고 성공 응답 후 Fault 상태를 유지한다.
- 전체 unittest 246개가 통과했다.

### S03 운전 중 Bus 단절과 동기 Reconnect — 완료

- cyclic transport exception을 초기화 실패와 구분해 `BUS_DISCONNECTED`로 전환한다.
- cable 분리처럼 cyclic 호출이 예외 대신 WKC 0을 반환하는 경우도 연속 mismatch 뒤 slave
  transport 상태를 확인하여 `BUS_DISCONNECTED`로 전환한다.
- AxisRuntime, DeviceManager, topology/cache/controller와 TCP listener/client를 유지하고 EtherCAT
  transport와 cyclic I/O만 중단한다.
- 기존 runtime을 사용하는 동기 reconnect coordinator를 구현한다. startup initialization-error는
  필요한 runtime을 새로 만든 뒤 같은 완료 검증 경계를 사용한다.
- reconnect 성공 시 process data와 모든 축 parameter refresh를 완료한 뒤 `NORMAL` 또는 남은
  Fault에 따른 상태로 전환한다.
- 연결 유실·reconnect 실패 Diagnostic, timeout, 반복/중첩 요청과 authority 유지 여부를 테스트한다.
- `system/bus/reconnect`는 `INITIALIZATION_ERROR`, `BUS_DISCONNECTED`, `FAULT`에서만 허용하고
  정상 운전 중에는 거부한다.

구현 결과:

- PySOEM/Mock cyclic transport 오류를 `CommunicationException` 경계로 통일하고 운전 중 오류를
  `BUS_DISCONNECTED` 및 `BUS_CONNECTION_LOST` Fault로 전환한다.
- transport만 닫고 기존 `ServerSession`, AxisRuntime, DeviceManager, cache/controller/topology,
  TCP listener/client와 command authority를 유지한다.
- disconnected 전용 service loop에서 cyclic I/O와 feedback만 중단하고 status, authority,
  fault-reset, reconnect 및 restart API를 계속 제공한다.
- Bus reconnect를 플래그 기반 서버 재시작에서 동기 coordinator 호출로 변경했다. 같은 runtime에
  PRE-OP 연결, process image 재구성, Axis별 motion mode 복원, OP 진입 및 전체 Axis parameter
  refresh가 끝난 뒤에만 Success를 반환한다.
- startup Bus/Device Initialization 실패에서는 새 runtime을 구성하되 기존 TCP listener/client와
  현재 authority를 유지한 채 정상 server loop로 전환한다.
- 성공 시 connection/WKC/reconnect Fault를 resolve 및 내부 acknowledge하고, 실패/timeout 시
  `BUS_RECONNECT_FAILED`를 남긴 채 `BUS_DISCONNECTED`를 유지한다.
- recovery는 server loop에서 동기 실행한다. 기존 TCP socket과 authority는 유지하지만 완료
  전까지 같은 loop의 status/stop을 포함한 다른 API 처리는 일시 정지한다.
- 전체 unittest 248개가 통과했다.

### S04 PySOEM Axis Restart 완료 검증 — 완료

- Axis restart 시작부터 완료까지 전체 Bus motion을 제한한다.
- restart request 이후 대상 slave 재발견, process image 재구성, 해당 Axis parameter refresh를
  순서대로 검증하는 동기 recovery를 구현한다.
- 성공 후에만 Success를 반환하고 timeout/단계 실패는 `AXIS_RESTART_FAILED`와 Fail로 변환한다.
- MockMaster에도 동일 완료 계약을 적용해 backend parity 테스트를 구성한다.

구현 결과:

- Axis restart request 직후 runtime을 전역 `FAULT`로 전환하여 전체 Bus motion을 제한한다.
- restart request 전에 모든 Axis의 homing/trajectory를 중단하고 실제 위치 hold 및 전체 Axis
  disable을 검증한다. process image 복원 후에도 자동 enable/이전 motion 재개는 하지 않는다.
- transport를 닫고 설정된 30초 안에 전체 slave 수와 대상 profile identity가 다시 발견될 때까지
  PRE-OP 연결을 반복한다. PySOEM `connect()`의 mapping 검증을 통해 process image를 재구성한다.
- 모든 Axis의 기존 motion mode와 CSP interpolation 설정을 복원하고 OP 진입 및 cyclic exchange를
  검증한 뒤 restart 대상 Axis의 parameter cache만 refresh한다.
- MockMaster와 PySOEMMaster가 같은 recovery coordinator 및 완료 조건을 사용한다.
- 완료 전에는 응답하지 않으며 timeout/재발견/process image/OP/refresh 실패를
  `AXIS_RESTART_FAILED`와 Fail로 변환한다. transport를 복원하지 못하면
  `BUS_DISCONNECTED`, 연결 후 후처리 실패면 `FAULT`를 유지한다.
- 이후 Bus reconnect가 성공하면 Axis restart 실패 조건을 resolve하고, Axis fault-reset을 받은 뒤
  latching Fault를 clear하도록 복구 경로를 연결했다.
- 전체 unittest 251개가 통과했다.

### S05 통합 정리와 완료 검증 — 소프트웨어 완료

- recovery coordinator와 TD-025의
  `refresh_after_recovery(runtime, recovery_type, affected_axes)` 경계를 고정한다.
- 삭제된 reset/acknowledge 명칭, 낡은 lifecycle 가정과 dead code를 코드·문서·테스트에서 제거한다.
- 전체 자동 테스트와 mock 오류 주입 시나리오를 통과시킨다.
- 실장치에서는 cable disconnect/reconnect, WKC Fault Reset, drive Fault Reset과 Axis restart를
  별도 체크리스트로 검증하고 결과를 완료 증거에 기록한다.

구현 결과:

- typed `RecoveryType`과
  `refresh_after_recovery(runtime, recovery_type, affected_axes)`를 단일 TD-025 연결 경계로
  추가했다. 현재 구현은 TD-023 Axis cache refresh adapter를 사용한다.
- Bus reconnect는 모든 Axis, Axis restart는 정확히 대상 Axis 하나만 전달하도록 계약 검증과
  자동 테스트를 추가했다.
- startup/operational reconnect가 같은 완료·실패 Diagnostic helper를 사용하도록 통합했다.
- timeout을 slave 연결뿐 아니라 process image 복원과 parameter refresh 전체 완료에 적용했다.
- connect와 OP 전이에는 남은 timeout을 backend까지 전달한다. worker가 없으므로 단일 native/SDO
  호출의 강제 중단은 지원하지 않고 단계 반환 시 deadline 초과를 판정한다.
- Axis restart의 OP 진입 전 실패와 OP 진입 후 refresh 실패를 구분하여 각각
  `BUS_DISCONNECTED`와 연결된 `FAULT`로 처리한다.
- 폐기된 reset API와 lifecycle 설명을 현재 API 문서, 시험 절차와 TD-025 경계 문서에서
  정리했다. TD-018의 대체된 계약은 DEC-026~DEC-029를 참조하도록 표시했다.
- 전체 Bus Axis restart 안전 정지, 정상 상태 reconnect 거부와 WKC 기반 cable disconnect fallback을
  추가하고 동기 recovery 중 API 일시 정지 계약을 UI·문서에 명시했다.
- 실축 reconnect에서 OP 진입 뒤 전체 Axis SDO refresh 동안 cyclic PDO가 정지하여 WKC가
  `5/15`로 떨어지고 Axis Fault Reset RxPDO가 전달되지 않는 문제를 확인했다. parameter refresh를
  PRE-OP으로 이동하고 OP 진입 후 정상 WKC 3회 연속 검증을 recovery 완료 조건에 추가했다.
- 전체 unittest 265개, source compile과 diff 검사가 통과했다.
- 실축 검증은 아직 수행하지 않았으므로 RF-005 상태는 `in_progress`를 유지한다.

## 관련 작업

runtime 생성 단계의 degraded startup 세부 구조는 [TD-018](../td/TD-018-runtime-initialization-error.md)에서 추적한다.
공통 Diagnostic 객체와 clear 조건은 [Diagnostic 데이터 모델](../../diagnostic/diagnostic_model.md)을 따른다.
Definition에서 제외한 recovery 동작과 handler 연결은 이 RF에서 구현한다.
process restart는 Diagnostic 저장소를 새로 만들지만 bus reconnect는 기존 저장소를 유지한다.
reconnect가 해결한 Initialization Fault의 내부 acknowledge/clear도 이 RF에서 처리한다.
복구 완료 후 parameter OD refresh와 cache invalid 처리는
[TD-025](../td/TD-025-runtime-parameter-cache.md)가 담당한다.

## 검증 계획

- mock backend에 초기화, disconnect와 fault를 주입한다.
- 상태별 API 허용/거부, TCP/authority 유지와 재복구를 검증한다.
- 지원 실장치의 cable disconnect/reconnect와 drive fault recovery를 시험한다.

## 완료 증거

### 자동 검증

- 전체 unittest: 265개 통과
- Python source compile: 통과
- diff 형식 검사: 통과
- MockMaster disconnect/reconnect, timeout, Axis restart와 refresh 대상 parity: 통과

### 실축 검증 완료 — 2026-08-26

- CMMT 4축과 CPX-AP-I-EC 1대, 총 5 slave 구성에서 운전 중 EtherCAT cable을 분리했다.
  WKC `0/10`, `BUS_DISCONNECTED`와 `BUS_CONNECTION_LOST`를 확인했고 기존 TCP client와
  command authority owner `1`이 유지됐다.
- cable 재연결 후 같은 client의 `system/bus/reconnect`가 PRE-OP parameter refresh, OP 진입과
  정상 WKC 검증을 완료했다. Bus 단절로 발생한 Axis Fault는 reconnect와 분리하여 전체 Axis
  fault-reset으로 복구했다.
- 최종 상태는 runtime `normal`, Bus connected, WKC `15/15`, 4축 mode display `1`, 활성
  Diagnostic 없음으로 확인했다.

### 실축 검증 대기

- reconnect 처리 중 기존 TCP socket은 유지되지만 status/stop 등 다른 API 응답은 recovery
  완료까지 대기하는지 확인
- 실제 CMMT Axis restart에서 slave가 사라졌다가 30초 안에 재발견되고, 다른 Axis를 포함한
  process image 복원 후 대상 Axis cache만 갱신되는지 확인. restart 전 전체 Axis가 disable되고
  완료 후 자동 재-enable 또는 이전 trajectory 재개가 없는지도 확인
- reconnect/restart 실패 주입 시 timeout, `BUS_RECONNECT_FAILED` 및 `AXIS_RESTART_FAILED`와
  후속 fault-reset clear 경로 확인
- 위 결과를 기록한 뒤 RF-005를 `done`으로 변경
