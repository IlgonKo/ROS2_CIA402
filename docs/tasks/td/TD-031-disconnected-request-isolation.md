# TD-031 Bus 단절 중 장치 조회 차단 및 요청 오류 격리

- 등록일: 2026-08-31
- 상태: `open`
- 우선순위: 높음
- 관련 계약: DEC-019, DEC-026, DEC-027 / TD-005, RF-005

## 배경 및 사용자 보고

실장치 AP parameter 테스트 중 사용자가 RuntimeError traceback과 서버 다운 증상을 보고했다.
해당 요청은 다음과 같다.

```json
{"cmd":"system/io/ap/param_read","data_type":"uint8","instance":"0","io":"io0","length":"1","module":"1","parameter_id":"20071","request_id":"node-red-350156-42"}
```

로그의 예외 체인은 다음 순서다.

1. RuntimeDiagnosticMonitor가 연속 WKC mismatch 후 transport 불가를 확인하여
   `CommunicationException("bus_transport_state")` 발생.
2. `mark_bus_disconnected()`가 transport를 닫고 session을 `BUS_DISCONNECTED`로 전환.
3. 기존 runtime/TCP를 유지하는 disconnected loop에서 AP read 요청 수신.
4. 요청 validator가 status 분류를 이유로 현재 Bus 상태 검사를 건너뜀.
5. AP header의 첫 단계인 module address write(`0x27F0:02`)가 닫힌 PySOEM transport에 접근.
6. `_require_connected()`가 일반 `RuntimeError("PySOEMMaster is not connected...")` 발생.

이 요청은 parameter id/instance 쓰기보다 앞에서 실패했다. 따라서 이 traceback으로
parameter 20071 자체의 지원 여부나 AP parameter 오류를 판단할 수 없다.

## 확인된 원인

### 1. 읽기/쓰기 분류와 장치 통신 필요 여부를 혼동한 API gating

- `motion_server/api/validator.py::command_allowed_by_runtime_state()`는
  `not spec.is_command`이면 바로 True를 반환한다.
- `system/io/ap/param_read`, `system/io/iol/param_read`는 status 명령이지만 실제로 SDO read/write
  sequence를 실행한다. status snapshot/catalog 조회와 같은 조건으로 허용하면 안 된다.
- runtime 객체가 존재하고 과거 initialization이 성공했다는 사실은 현재 transport 가용성을
  보장하지 않는다. 단절 시 runtime/cache는 유지한다는 DEC-026/027 계약을 API gating에
  충분히 반영하지 못했다.
- AP만 임시 차단하지 말고 EtherCAT/AP/IOL 등 실제 장치 통신이 필요한 조회의 범위를 조사해야 한다.

### 2. 예상 가능한 transport 단절이 일반 RuntimeError로 노출

- `ethercat/pysoem_master.py::read_sdo/write_sdo()`는 `_require_connected()`를
  `_with_sdo_communication_retry()`보다 먼저 호출한다.
- 닫힌 transport에 대한 예상 가능한 접근 실패가 일반 RuntimeError가 되어 API에서는
  `INTERNAL_FAILURE`와 예외 traceback으로 나타난다.
- API gating을 통과한 뒤 연결이 닫히는 경우도 transport 경계에서 등록된 통신 예외로 처리해야 한다.
  모든 RuntimeError를 통신 오류로 바꾸어 실제 programming error를 숨기는 방식은 사용하지 않는다.

### 3. 실제 서버 루프 탈출이 가능한 별도 요청 오류 경계 누락

- `motion_server/app/client_transport.py::service_client()`의 `json.loads()`는 router의
  request_response 경계 밖에서 실행된다.
- `run_bus_disconnected_loop()`의 client 처리 catch는 OSError만 처리하므로 JSONDecodeError는
  루프 밖으로 전파된다. normal loop도 같은 종류의 client 처리 경계를 점검해야 한다.
- configuration/initialization degraded loop는 JSONDecodeError를 처리하고 있어 경계가 일관되지 않다.
- 루프 밖으로 전파되면 `run_main_once()`의 socket context/finally를 통해 listener/runtime 자원이
  닫힐 수 있고, application은 일반 요청 오류를 재시작 예외처럼 처리하지 않는다.
- 잘못된 JSON을 주입한 오프라인 재현에서 disconnected loop 밖으로 예외가 탈출함을 확인했다.
  단, 이번 사용자 로그에 잘못된 JSON이 있었다는 증거는 없으므로 실제 다운 원인으로 단정하지 않는다.

## 서버 종료 여부: 확인된 사실과 미확정 사항

- 제공된 traceback에는 `router.py::request_response()` 프레임이 있다. 해당 경계는 일반 Exception을
  catch하여 logger.exception으로 traceback을 출력하고 `INTERNAL_FAILURE` Fail 응답을 반환한다.
- disconnected loop가 바깥 CommunicationException의 except 블록 안에서 실행되므로, 내부 요청의
  traceback에 `During handling of the above exception`과 바깥 버스 예외가 함께 출력될 수 있다.
  이 문구 자체는 두 예외가 모두 처리되지 않고 프로세스를 종료했다는 증거가 아니다.
- 오프라인 재현에서 동일 AP read는 `INTERNAL_FAILURE` 응답으로 반환되어 output buffer에 들어갔다.
  disconnected loop 반복 실행도 명시적 restart action 전까지 유지됨을 별도로 확인했다.
- 조사 시점에는 PID 14184의 `python -B -m motion_server ... --port 15000` 프로세스와
  `0.0.0.0:15000` listener가 존재했다. 사용자가 이후 재기동했는지는 알 수 없으며, 현재 listener
  존재만으로 이전 다운 보고를 부정하거나 당시 TCP 응답성까지 보장하지 않는다.
- 최초 transport 상실의 원인, 당시 실제 PID 종료/종료 코드, 응답 정지와 프로세스 종료의 구분은
  아직 미확정이다. 전체 마지막 로그, 해당 시점 PID/exit code와 reconnect 결과로 보완해야 한다.

## 수정 방향 및 책임 경계

1. 공개 API의 조회/명령 분류와 transport 의존성을 분리하여 장치 접근 전에 현재 session 상태를 검사한다.
   BUS_DISCONNECTED에서는 실제 장치 접근을 기존 `INVALID_STATE` Fail로 거부하고, snapshot/catalog 등
   통신이 필요 없는 조회와 명시적 recovery는 기존 계약에 따라 유지한다.
2. gating 이후 transport 단절은 기존 CommunicationException 계층과 중앙 mapper로 처리한다.
   미연결 startup misuse 등 다른 호출자의 의미를 함께 확인하고 일괄 예외 치환은 피한다.
3. 요청 파싱/라우팅/응답 전송의 client 단위 경계를 normal/disconnected/degraded loop에서 정합화한다.
   malformed request나 해당 client의 송수신 실패로 전체 listener 또는 다른 client를 종료하지 않는다.
4. 예상한 상태/통신 실패는 기존 Fail로 반환한다. 예상 밖 programming error의 조사용 traceback은
   보존하며 서버 전체 broad catch 후 무조건 계속 실행하는 방식으로 오류를 숨기지 않는다.
5. 실제 다운 신고를 재현·검증할 때 PID/listener/동일 TCP 연결/다른 client 응답을 각각 확인한다.
   traceback 출력만으로 프로세스 종료로 판정하지 않는다.

## 구현 순서 초안

1. 실패하는 회귀 테스트: 단절된 runtime의 AP/IOL/EtherCAT 조회, 닫힌 transport,
   malformed JSON의 client 경계, 정상 조회/Feedback 유지.
2. 기존 API별 transport 의존성 목록과 Fail mapping을 확정하고 gating/transport 경계를 수정.
3. client 오류 격리를 정합화하고 loop 생존/reconnect/다중 client 회귀를 검증.
4. 실장치의 최초 단절 원인과 실제 종료 여부를 별도 기록하고 완료 근거를 업데이트.

## 완료 조건

- BUS_DISCONNECTED에서 AP/IOL/EtherCAT의 실제 장치 접근 조회가 SDO 호출 전에 기존 Fail로 거부된다.
- snapshot/catalog/Feedback, 명시적 reconnect/restart는 기존 허용 범위에서 유지된다.
- 검증 직후 transport를 닫아도 예상 가능한 통신 Fail이며 일반 RuntimeError/INTERNAL_FAILURE로 오분류하지 않는다.
- 정상 JSON의 장치 오류, malformed JSON, client 전송 오류가 전체 서버 listener나 다른 client를 종료하지 않는다.
  실패 client의 해제 정책과 그 client가 가진 authority 정리도 함께 검증한다.
- normal/disconnected/degraded loop의 client 경계 테스트, 같은 TCP 연결의 후속 status 요청,
  다른 client 요청 및 reconnect 후 파라미터 조회 회귀가 통과한다.
- mock/오프라인 자동 테스트와 실장치 결과를 구분해 기록하고, 다운 신고의 실제 종료 여부 및
  최초 단절 원인에 대해 확인된 사실/미확인 사항을 명시한다. 확정하지 못한 원인은 별도 추적한다.

## 제외 범위

- CPX firmware 업데이트, ISDU gateway 주소 변경, AP parameter 번호/타입/instance 변경.
- 자동 reconnect, recovery worker 추가, Bus와 TCP lifecycle 결합.
- 이전에 제외한 TCP UTF-8 분할 디코딩 항목의 재도입.
- 모든 예상 밖 예외를 정상 처리로 바꾸거나 loop 바깥의 치명적 오류를 무조건 무시하는 변경.

## 등록 시 검증 결과

- hardware 호출 없이 test fixture runtime과 `_master=None`인 PySOEMMaster의 SDO 경로로 조사.
- `gate_allows_disconnected_ap_read=True` 확인.
- 실제 router 반환: `result=fail`, `failure.code=INTERNAL_FAILURE`, request_id 보존,
  client output buffer 170 bytes; router 밖으로 RuntimeError가 전파되지 않음.
- stub listener/client로 disconnected loop 2회 반복 및 명시적 restart action에서만 정상 반환 확인.
- 같은 loop에 JSONDecodeError를 주입하면 루프 밖으로 전파됨을 확인.
- 이번 변경은 TD 등록과 원인 분석 문서화만이며 구현 코드, 서버 실행 상태 및 실장치 설정은 변경하지 않았다.
