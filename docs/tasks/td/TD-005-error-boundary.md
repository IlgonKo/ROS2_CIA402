# TD-005 예외 경계와 오류 형식 불균일

## 배경 및 현재 구조

EtherCAT master, startup, SDO/AP/IOL parameter access와 Control Panel에서 broad
`except Exception`이 사용되며 서로 다른 실패가 문자열 오류로 합쳐질 수 있다.

## 문제와 위험

mailbox timeout, unsupported object, protocol validation과 programming error를 구분하기 어려워
client의 복구 판단과 장애 분석이 불안정하다.

## 관련 위치

- `ethercat/pysoem_master.py`
- `ethercat/sdo_access.py`
- `motion_server/app/startup.py`
- `motion_server/handlers/parameter_access/*`
- Axis/IO Control Panel

## 목표 구조 및 구현 범위

- Diagnostic 데이터 모델, API Success/Fail 계약, exception 지점 분류 순으로 선행 설계를 완료한 뒤
  구현 범위를 확정한다. 전체 순서는 [Diagnostic 문서](../../diagnostic/README.md#설계-및-구현-순서)를 따른다.
- 요청 응답은 [API Success/Fail 응답 계약](../../api/response_contract.md)의 공통 envelope로 migration한다.
- client가 의존하는 code는 [API Failure Code](../../api/failure_codes.md)의 catalog와 변환 원칙을 따른다.
- 내부 Exception은 [Exception과 API Failure Mapping](../../api/exception_mapping.md)의 중앙 table과
  최상위 boundary에서 API Failure로 변환한다.
- transport, protocol, validation과 runtime 오류 계층을 정의한다.
- 오류 유형을 안정적인 Motion Server API failure code에 매핑한다.
- 복구 가능한 오류만 해당 계층에서 처리하고 programming error는 숨기지 않는다.
- 최상위 process/client boundary의 broad exception 허용 정책을 문서화한다.

## 하위 작업 계획

각 하위 작업은 독립 브랜치, 자동 테스트와 완료 증거를 갖고 순서대로 main에 병합한다. 서버 API는
내부 migration 동안 기존 형식을 유지한다. Client가 기존/신규 응답을 모두 읽도록 먼저 변경한 뒤
서버를 새 envelope로 전환하며 서버 dual-write는 사용하지 않는다.

각 하위 작업을 시작할 때는 TD-017의 `decoder -> validator -> router -> handler -> encoder` 책임과
대조하여 변경할 기존 모듈을 먼저 기록한다. 신규 파일은 기존 모듈 책임에 포함되지 않는 독립 개념일
때만 추가하고 그 필요성을 해당 단계 계획에 명시한다.

| 하위 작업 | 범위 | 선행 작업 | 상태 |
| --- | --- | --- | --- |
| `TD-005-S01` | FailureCode, Exception 계층, Mapper, PartialFailure 기반 | 없음 | `complete` |
| `TD-005-S02` | Response encoder, request boundary와 기존 API adapter | S01 | `complete` |
| `TD-005-S03` | EtherCAT SDO 및 Mock/PySOEM Exception parity | S01 | `complete` |
| `TD-005-S04` | Axis/IO EtherCAT parameter handler | S02, S03 | `complete` |
| `TD-005-S05` | AP parameter 경로 | S03, S04 | `complete` |
| `TD-005-S06` | IO-Link ISDU 경로 | S03, S04 | `complete` |
| `TD-005-S07A` | Motion/Axis command와 PartialFailure | S02-S04 | `complete` |
| `TD-005-S07B` | IO command와 PartialFailure | S02-S06 | `complete` |
| `TD-005-S07C` | Status/Catalog handler | S02-S06 | `complete` |
| `TD-005-S08` | Diagnostic core와 startup/runtime 연계 | S01-S07 | `complete` |
| `TD-005-S09` | Control Panel과 ROS의 기존/신규 응답 호환 | S02-S08 | `complete` |
| `TD-005-S10` | 서버 Success/Fail envelope 최종 전환 | S09 | `complete` |
| `TD-005-S11` | legacy 제거, broad catch allowlist와 자동 검사 | S10 | `pending` |

### 작업 재개 체크포인트

- 현재 완료 단계: `TD-005-S10`
- 다음 실행 단계: `TD-005-S11`
- 다음 시작 위치: command handler의 임시 response capture와 client legacy fallback을 정리하고,
  broad catch allowlist 및 envelope 위반 자동 검사를 추가한다.
- 현재 호환 상태: 서버 request/response는 신규 Success/Fail envelope만 송신한다. 주기 feedback과
  자발적 notification은 envelope 대상이 아니다.
- 보존할 사용자 변경: `device/cmmt/required_od.py`의 OD 기본값 및 형식 변경은 `TD-023` 범위이며
  TD-005 변경에 포함하지 않는다.
- 재개 방법: 아래에서 가장 앞선 `pending` 단계를 선택하고, 선행 작업과 인계 조건을 확인한 뒤
  상태를 `in_progress`로 변경한다. 완료 후 완료 증거와 다음 시작 위치를 함께 갱신한다.

### TD-005-S01 계약

| 구분 | 기록 내용 |
| --- | --- |
| 공개 계약 | `FailureCode`, `Failure`, MotionServerException 계층, `map_exception`, `ItemFailure`, `PartialFailure` |
| 필수 구현 | 확정된 20개 code, 중앙 mapping table, MRO 기반 최근접 mapping과 INTERNAL_FAILURE fallback |
| 선택 기능 | 구체 Exception별 allowlist 기반 public details |
| 내부 helper | MRO 탐색과 details 추출 함수 |
| 제외 범위 | response JSON encoding, router 연결, 기존 handler/backend 변경, Diagnostic runtime 구현 |

S01 완료 조건:

- FailureCode 20개가 문서 catalog와 일치한다.
- 확정된 상위·구체 Exception과 모든 mapping이 구현된다.
- 정확한 type, 최근접 등록 상위 type, INTERNAL_FAILURE 순으로 선택한다.
- mapper가 허용하지 않은 Exception 문자열, 속성과 `__cause__`를 Failure에 노출하지 않는다.
- 별도 FailureDefinitionRegistry를 만들지 않는다.
- PartialFailure는 Exception이 아닌 결과 집계 객체다.
- 기존 API 응답과 runtime 동작을 변경하지 않는다.
- code 집합, mapping, 상속 fallback, 내부정보 비노출과 partial model 자동 테스트가 통과한다.

## 검증 계획

- timeout, unsupported object, invalid payload, initialization failure와 내부 오류를 주입한다.
- 각 오류의 API code, 메시지, logging과 connection 유지 여부를 검증한다.

## 조사 자료

- [Exception 발생 및 Catch 지점 전수 조사](../../diagnostic/error_point_inventory.md)
- [Exception 발생·Catch 지점 목표 분류](../../diagnostic/exception_point_classification.md)
- 2026-08-21 기준 catch 144곳, broad catch 85곳, 명시적 raise 233곳과
  generic `RuntimeError` 42곳을 migration 대상으로 추적한다.

## 완료 증거

완료 시 오류 표, API 문서, broad exception 검사와 테스트 결과를 기록한다.

## 하위 작업 완료 증거

| 하위 작업 | 구현 | 검증 | 결과 |
| --- | --- | --- | --- |
| `TD-005-S01` | `motion_server/failure/`의 code, model, Exception, mapping과 partial model | `tests/test_failure_contract.py` 9개 및 전체 24개 unittest | 통과 |
| `TD-005-S02` | 기존 `api/encoder.py`의 `ResponseContext`/Success/Fail encoder와 `api/router.py`의 side-effect 없는 request boundary | `tests/test_api_response_boundary.py` 13개 및 전체 37개 unittest | 통과 |
| `TD-005-S03` | 기존 `sdo_access.py`, Mock/PySOEM raw transport와 Virtual OD Bridge의 공통 Exception 변환 | SDO parity 10개, Virtual OD 오류 2개 및 전체 49개 unittest | 통과 |
| `TD-005-S04` | 기존 EtherCAT parameter handler의 operation/validation/boundary 및 임시 legacy adapter | `tests/test_ethercat_parameter_handlers.py` 12개 및 전체 61개 unittest | 통과 |
| `TD-005-S05` | AP API/startup access의 target validation, status Exception 및 임시 legacy adapter | `tests/test_ap_parameter_handlers.py` 12개 및 전체 73개 unittest | 통과 |
| `TD-005-S06` | IO-Link ISDU의 IODD validation, status Exception, backend 전달 및 임시 legacy adapter | `tests/test_iol_parameter_handlers.py` 10개 및 전체 83개 unittest | 통과 |

S01 명세 추적:

| 명세 항목 | 구현 위치 | 검증 테스트 | 범위 확대 여부 |
| --- | --- | --- | --- |
| FailureCode 20개 | `motion_server/failure/codes.py` | `test_failure_code_catalog_is_exact` | 없음 |
| Exception 계층과 중앙 mapping | `exceptions.py`, `mapping.py` | `test_all_contract_exception_types_have_expected_mapping` | 없음 |
| 정확한 type 및 최근접 상위 type | `mapping.py` | `test_exact_mapping_wins_over_registered_base_mapping`, `test_nearest_registered_base_mapping_supports_new_subclass` | 없음 |
| INTERNAL_FAILURE fallback | `mapping.py` | `test_unregistered_exception_uses_safe_internal_failure` | 없음 |
| details allowlist와 내부정보 비노출 | `mapping.py` | `test_exception_cause_and_unlisted_attributes_are_not_exposed`, `test_optional_public_detail_is_omitted_when_not_provided` | 없음 |
| PartialFailure 결과 model | `partial.py` | `test_partial_failure_is_a_result_model_not_an_exception` | 없음 |
| Registry 제외 | package public export | `test_failure_definition_registry_is_not_public_contract` | 없음 |

S01에서는 response JSON encoding, router, handler/backend와 Diagnostic runtime을 변경하지 않았다.

### TD-005-S02 Response encoder와 요청 boundary

| 구분 | 계획 |
| --- | --- |
| 목표 | 확정된 Success/Fail envelope를 생성하는 단일 encoder와 요청 단위 exception 변환 경계를 마련한다. |
| 주요 변경 | 기존 `api/encoder.py`에 Success/Fail builder, `request_id` echo, `Failure` 직렬화와 기존 요청 adapter를 추가하고, 기존 `api/router.py`에 handler 결과/Exception을 response로 바꾸는 boundary를 추가한다. 신규 API module은 만들지 않는다. |
| 필수 계약 | Success는 `data`, Fail은 `failure`만 포함한다. 요청 `type`을 유지하고 빈 Success도 `data: {}`를 가진다. 미등록 Exception은 안전한 INTERNAL_FAILURE로 변환하고 서버 log에는 원인을 남긴다. |
| 제외 범위 | 기존 handler 응답 형식의 일괄 변경, notification/feedback envelope 변경, socket 단절을 API Fail로 송신, client 변경은 하지 않는다. |
| 완료 조건 | response 계약의 필드 포함·배타성·request_id 규칙과 mapper 연계를 자동 테스트한다. 기존 live API 및 기존 전체 테스트 동작이 유지된다. |
| 인계 | S03은 Exception 기반 backend 계약을 사용할 수 있고, S04 이후 handler는 이 encoder/boundary에 연결할 수 있어야 한다. |

S02 명세 추적:

| 명세 항목 | 구현 위치 | 검증 테스트 | 범위 확대 여부 |
| --- | --- | --- | --- |
| Success/Fail 필드와 상호 배타성 | `motion_server/api/encoder.py` | `test_success_contains_data_only`, `test_fail_contains_failure_only_and_omits_absent_details` | 없음 |
| 빈 Success data와 선택 details | `encoder.py` | `test_empty_success_has_empty_data_object`, `test_fail_includes_allowlisted_details` | 없음 |
| request_id echo | `ResponseContext` | `test_request_id_is_echoed_only_when_present` | 없음 |
| 기존 `cmd` 요청 adapter | `ResponseContext.from_request` | `test_legacy_cmd_is_adapted_to_response_type` | 없음 |
| 필수 command type 검증 | `ResponseContext.from_request` | `test_request_without_command_type_is_rejected` | 없음 |
| Exception mapping boundary와 logging | `motion_server/api/router.py` | `test_expected_exception_becomes_mapped_fail`, `test_unexpected_exception_is_logged_and_hidden` | 없음 |
| transport 오류 제외 | socket 송신을 boundary 밖에 유지 | `test_transport_send_is_outside_request_boundary` | 없음 |
| 내부 helper 비공개 | package export | `test_internal_response_helper_is_not_public_contract` | 없음 |
| TD-017 module 책임 준수 | `encoder.py`, `router.py` | `test_response_contract_uses_existing_api_modules` | 없음 |

S02에서는 `route_message`, handler와 socket 송신 경로를 변경하지 않았다. 따라서 서버는 계속 legacy
응답만 송신하며 신규 envelope는 S04 이후 handler migration과 S10 최종 전환 전까지 live API에 적용되지 않는다.

### TD-005-S03 EtherCAT SDO Exception parity

| 구분 | 계획 |
| --- | --- |
| 목표 | MockMaster와 PySOEMMaster의 SDO 실패가 동일한 MotionServerException 의미로 상위 계층에 전달되게 한다. |
| 주요 변경 | `ethercat/sdo_access.py`, Mock/PySOEM SDO read/write의 timeout, 통신 실패, 미지원 OD, device reject 변환과 exception chaining을 정리한다. |
| 필수 계약 | backend 차이와 무관하게 같은 원인은 같은 Exception 계층과 FailureCode로 매핑된다. raw pysoem/OSError 원인은 `raise ... from ...`으로 log용 보존한다. |
| 제외 범위 | handler response 변경, AP/IO-Link 변환, retry/reconnect 정책과 Diagnostic 생성은 하지 않는다. |
| 완료 조건 | read/write 각각의 정상, timeout, object-not-found, device reject, 예상 밖 오류를 Mock/PySOEM parity 테스트로 검증하고 중간 broad catch가 programming error를 숨기지 않는다. |
| 인계 | S04-S06이 backend 문자열을 해석하지 않고 구체 Exception을 그대로 사용할 수 있어야 한다. |

S03 Exception 변환 계약:

| 원인 | Mock 경로 | PySOEM 경로 | 공통 Exception |
| --- | --- | --- | --- |
| SDO object/subindex 없음 | Virtual OD Bridge의 OD lookup 실패 | SDO abort `0x06020000`, `0x06090011` | `SdoObjectNotFoundException` |
| SDO protocol timeout | `TimeoutError` | `TimeoutError`, SDO abort `0x05040000` | `CommunicationTimeoutException` |
| Device reject | Virtual OD Bridge의 read-only 판정 등 | 그 밖의 `SdoError` abort | `DeviceRejectedException` |
| Mailbox/transport 실패 | `ConnectionError`, `OSError` | `MailboxError`, `PacketError`, `WkcError`, interface-not-open 및 OS transport 오류 | `CommunicationException` |
| Typed read short payload | 공통 `SdoAccess` | 공통 `SdoAccess` | `DeviceAccessException` |
| 예상하지 못한 오류 | 변환하지 않음 | 변환하지 않음 | 원래 Exception 유지 |

S03 명세 추적:

| 명세 항목 | 구현 위치 | 검증 테스트 | 범위 확대 여부 |
| --- | --- | --- | --- |
| 정상 read/write parity | `mock_master.py`, `pysoem_master.py` | `test_mock_and_pysoem_normal_read_write_match` | 없음 |
| object-not-found parity | Virtual OD Bridge, PySOEM raw transport | `test_object_not_found_parity_for_read_and_write`, `test_virtual_od_reports_missing_sdo_object` | 없음 |
| timeout 및 communication parity | Mock/PySOEM raw transport | `test_timeout_parity_for_read_and_write`, `test_communication_failure_parity_for_read_and_write` | 없음 |
| device reject parity | Virtual OD Bridge, PySOEM raw transport | `test_device_rejected_parity_for_read_and_write`, `test_virtual_od_reports_read_only_write_as_device_reject` | 없음 |
| exception chaining | backend 변환 지점 | object-not-found 및 parity 테스트의 `__cause__` 검증 | 없음 |
| programming error 비은닉 | raw transport와 `SdoAccess` | `test_unexpected_exception_is_not_hidden`, `test_typed_sdo_access_does_not_hide_unexpected_exception` | 없음 |
| MockMaster device 의미 제외 | `mock_master.py`, `od_bridge.py` | `test_mock_master_does_not_interpret_device_key_error` | 없음 |
| short payload 분류 | `sdo_access.py` | `test_short_typed_payload_is_device_access_failure` | 없음 |

S03에서는 기존 backend 및 Virtual OD Bridge 파일만 변경했다. Handler response, AP/IO-Link, retry,
reconnect와 Diagnostic은 변경하지 않았다.

### TD-005-S04 Axis/IO EtherCAT parameter handler

| 구분 | 계획 |
| --- | --- |
| 목표 | Axis/IO EtherCAT parameter 요청의 validation, resource lookup, device access 실패를 공통 Exception과 request boundary로 통일한다. |
| 주요 변경 | `motion_server/handlers/parameter_access/`의 Axis/IO SDO read/write 경로, payload 검증과 target lookup을 migration한다. |
| 필수 계약 | 잘못된 요청, 없는 axis/IO, 미지원 object, timeout과 device reject가 서로 다른 안정적 FailureCode를 가진다. 성공 payload의 기존 의미는 유지한다. |
| 제외 범위 | AP와 IO-Link 경로, Control Panel 호환 읽기, 전체 서버 envelope 전환은 하지 않는다. |
| 완료 조건 | Axis/IO별 정상 read/write와 대표 실패 주입 테스트가 통과하고 handler 내부의 응답 문자열 조립 및 불필요한 broad catch가 제거된다. |
| 인계 | S05-S07이 동일한 parameter/handler 패턴을 복제하지 않고 재사용할 수 있어야 한다. |

S04 구현 계약:

- Axis/IO read/write operation은 socket에 직접 접근하지 않고 성공 data를 반환하거나 구체
  MotionServerException을 발생시킨다.
- 필수 field와 숫자/data type/value 오류는 `InvalidRequestException` 또는
  `InvalidArgumentException`, 없는 axis/IO는 `ResourceNotFoundException`으로 구분한다.
- 일반 EtherCAT parameter command로 IO-Link ISDU object에 접근하면
  `UnsupportedOperationException`을 발생시킨다.
- S03 backend Exception은 handler에서 문자열로 합치거나 다시 분류하지 않고 request boundary까지 전달한다.
- S10 전까지 `TECH_DEBT[TD-005]` legacy adapter가 신규 envelope를 기존 `ok/error` 응답으로 변환한다.
  서버는 legacy와 신규 필드를 동시에 송신하지 않는다.

S04 명세 추적:

| 명세 항목 | 구현 위치 | 검증 테스트 | 범위 확대 여부 |
| --- | --- | --- | --- |
| Axis 정상 read/write | `parameter_access/ethercat.py` | `test_axis_read_operation_returns_parameter_data`, `test_axis_write_operation_returns_written_value` | 없음 |
| IO selector 및 정상 read/write | `ethercat.py` | `test_io_read_and_write_operations_use_validated_selector` | 없음 |
| request/argument/resource 분류 | parse/validation helpers | missing index/value, invalid axis 및 unknown IO 테스트 | 없음 |
| unsupported ISDU 분류 | `validate_io_parameter_access` | `test_direct_iolink_object_access_is_unsupported` | 없음 |
| S03 Exception 전달 | 순수 operation과 S02 boundary | `test_backend_exception_reaches_request_boundary`, `test_unexpected_backend_error_is_not_reclassified_by_handler` | 없음 |
| legacy API 유지 | `_send_legacy_parameter_response` | live success/failure legacy shape 테스트 | 임시 adapter만 추가 |
| 예상/예상 밖 logging 분리 | `api/router.py` | S02 expected/unexpected logging 테스트 | 계약 명확화 |

S04에서는 기존 `api/router.py`와 `handlers/parameter_access/ethercat.py`만 변경했다. 제품 source 신규
파일은 만들지 않았다. AP, IO-Link, parameter save, 전체 router cutover와 client는 변경하지 않았다.

### TD-005-S05 AP parameter 경로

| 구분 | 계획 |
| --- | --- |
| 목표 | CPX-AP parameter access의 transport, module/parameter lookup과 protocol 실패를 공통 분류로 migration한다. |
| 주요 변경 | AP parameter handler와 하위 access 계층의 validation, timeout, communication, unsupported parameter 및 device reject 변환을 정리한다. |
| 필수 계약 | AP module 식별 실패와 parameter 식별 실패가 구조화된 resource 정보로 구분되고 내부 protocol 문자열은 API에 노출되지 않는다. |
| 제외 범위 | AP catalog 기능(RF-004), 재시도 정책, Diagnostic runtime은 구현하지 않는다. |
| 완료 조건 | 정상 read/write 및 invalid payload, module-not-found, parameter-not-found, timeout, device reject 테스트와 Failure details allowlist 검증이 통과한다. |
| 인계 | IO command와 Status/Catalog 작업이 AP 오류를 중앙 boundary에서 일관되게 처리할 수 있어야 한다. |

S05 구현 계약:

- API read/write는 순수 operation으로 실행하고 I/O와 AP module을 실제 runtime 구성에서 확인한다.
- module `0`은 CPX-AP-I-EC interface module, 그 밖의 번호는 구성된 AP module slot과 일치해야 한다.
- AP parameter catalog 기반 parameter ID 사전 검증은 RF-004 범위이므로 수행하지 않고 장치 status로 판정한다.
- AP busy status가 timeout까지 유지되면 `OperationTimeoutException`, 그 밖의 nonzero status는
  status code를 가진 `DeviceRejectedException`으로 처리한다.
- SDO/transport Exception은 `ap_sdo_step`에서 다시 포장하지 않고 S03 계약 그대로 전달한다.
- S10 전까지 `TECH_DEBT[TD-005]` legacy adapter가 기존 `ok/error` 응답만 송신한다.

S05 명세 추적:

| 명세 항목 | 구현 위치 | 검증 테스트 | 범위 확대 여부 |
| --- | --- | --- | --- |
| AP 정상 read/write | `handlers/parameter_access/ap.py` | `test_ap_read_returns_structured_data`, `test_ap_write_returns_payload_metadata` | 없음 |
| I/O/module lookup | `validate_ap_target` | unknown IO/module 및 interface module 0 테스트 | 없음 |
| request/payload validation | parse/encode helpers | invalid parameter ID/payload 테스트 | 없음 |
| timeout/device reject | API 및 startup AP status 처리 | busy/nonzero status와 startup 공통 Exception 테스트 | 없음 |
| S03 Exception 전달 | `ap_sdo_step` | `test_backend_exception_is_not_wrapped` | 없음 |
| legacy API 유지 | `legacy_ap_parameter_response` | `test_live_handler_keeps_legacy_shape` | 임시 adapter만 추가 |
| import 책임 | `api/__init__.py`, parameter handler 지연 연결 | 전체 module import 및 73개 회귀 테스트 | 없음 |

S05에서는 기존 AP handler, CPX startup AP access, API package export와 S04 handler의 boundary 연결만
변경했다. 제품 source 신규 파일은 만들지 않았다. AP catalog, retry/reconnect와 Diagnostic은 변경하지 않았다.

### TD-005-S06 IO-Link ISDU 경로

| 구분 | 계획 |
| --- | --- |
| 목표 | IO-Link ISDU access의 port/device/resource와 communication 실패를 공통 Exception/Failure 계약으로 통일한다. |
| 주요 변경 | ISDU handler와 access 계층의 request validation, port lookup, timeout, protocol/device reject 처리를 migration한다. |
| 필수 계약 | 없는 IO/port/object, 잘못된 index/subindex/value, timeout과 device reject를 구분하며 low-level 응답과 stack trace는 외부에 노출하지 않는다. |
| 제외 범위 | IODD catalog 확장, 자동 reconnect/retry, 지속 Diagnostic 정책은 다루지 않는다. |
| 완료 조건 | 정상 read/write와 대표 validation/resource/communication/device 실패 테스트가 통과하고 Mock/실 backend의 공개 실패 의미가 일치한다. |
| 인계 | S07B와 S07C가 IO-Link 실패를 별도 문자열 parsing 없이 집계할 수 있어야 한다. |

S06 구현 계약:

- I/O, configured IO-Link module/port binding, IODD variable와 subindex를 각각 식별한다.
- 없는 대상은 `ResourceNotFoundException`, IODD access right 거부는
  `PermissionDeniedException`, payload 오류는 `InvalidArgumentException`으로 구분한다.
- ISDU busy timeout은 `OperationTimeoutException`, 그 밖의 nonzero status는 status code를 가진
  `DeviceRejectedException`으로 처리한다.
- SDO/transport Exception은 재포장하지 않고 S03 계약 그대로 request boundary에 전달한다.
- S10 전까지 legacy adapter가 기존 `ok/error` 응답만 송신한다.

S06 명세 추적:

| 명세 항목 | 구현 위치 | 검증 테스트 | 범위 확대 여부 |
| --- | --- | --- | --- |
| 정상 ISDU read/write | `handlers/parameter_access/iol.py` | 정상 read/write payload 테스트 | 없음 |
| IODD binding/index/subindex | IODD validation helpers | missing binding/index/subindex 테스트 | 없음 |
| IODD access right | `validate_iodd_variable_access` | `test_iodd_access_denial_is_permission_denied` | 없음 |
| timeout/device reject | ISDU status 처리 | busy/nonzero status 테스트 | 없음 |
| S03 Exception 전달 | `isdu_sdo_step` | `test_backend_exception_is_not_wrapped` | 없음 |
| legacy API 유지 | `legacy_isdu_response` | `test_live_handler_keeps_legacy_shape` | 임시 adapter만 추가 |

S06에서는 기존 `handlers/parameter_access/iol.py`만 변경했다. 제품 source 신규 파일은 만들지 않았고,
신규 기능, reconnect/retry와 Diagnostic은 변경하지 않았다.

### TD-005-S07A Motion/Axis command와 PartialFailure

| 구분 | 계획 |
| --- | --- |
| 목표 | Motion/Axis command의 authority, 상태, limit, 대상별 실행 실패를 공통 계약으로 migration한다. |
| 주요 변경 | axis enable/disable/reset/restart/move/stop 등 현재 command handler를 분류표에 따라 변환하고 다축 결과에 PartialFailure 집계를 적용한다. |
| 필수 계약 | 요청 전체 거부와 일부 axis 실패를 구분한다. 일부 성공 시 성공 대상과 대상별 안전한 Failure를 보존하고 전체 code는 PARTIAL_FAILURE를 사용한다. |
| 제외 범위 | trajectory API 재설계(RF-009), recovery 상태 모델(RF-005), 실제 운전 알고리즘 변경은 하지 않는다. |
| 완료 조건 | authority/state/limit/device 실패와 all-success/all-fail/partial-fail 테스트가 통과하며 명령 실행 순서와 기존 안전 동작은 유지된다. |
| 인계 | S08 Diagnostic 연계가 필요한 운전 영향 실패 지점을 명확히 식별할 수 있어야 한다. |

S07A 완료 증거:

- 축 selector는 잘못된 값과 없는 축을 각각 `INVALID_ARGUMENT`, `RESOURCE_NOT_FOUND`로 구분한다.
- 대상별 controlword 실행은 요청 순서를 유지하고 all-success는 성공 대상 목록, all-fail은 첫 번째
  안전한 예상 실패, 일부 실패는 `PartialFailure`로 반환한다.
- request boundary는 authority/state/limit/device 실패와 `PARTIAL_FAILURE`를 공통 Fail envelope로
  변환하며 내부 Exception 문자열을 공개하지 않는다.
- 실제 축 enable/disable handler는 기존 cycle exchange, target hold와 legacy 응답을 유지하는 adapter로
  위 대상별 실행 결과를 사용한다.

### TD-005-S07B IO command와 PartialFailure

| 구분 | 계획 |
| --- | --- |
| 목표 | IO output 및 장치 관리 command의 validation, authority/state와 대상별 실패를 공통 계약으로 migration한다. |
| 주요 변경 | IO write 및 현재 구현된 IO command handler를 변환하고 복수 module/channel 작업에 PartialFailure 집계를 적용한다. |
| 필수 계약 | 잘못된 channel/value, 없는 대상, 권한·상태 거부, device access 실패와 부분 성공이 안정적인 code와 대상 정보로 구분된다. |
| 제외 범위 | 예약 API 구현(RF-003), 신규 IO 기능 추가, recovery 정책은 하지 않는다. |
| 완료 조건 | 단일/복수 대상의 성공, 전체 실패, 부분 실패 및 내부정보 비노출 테스트가 통과한다. |
| 인계 | S08에서 상태 영향이 있는 IO 실패만 Diagnostic 후보로 연결할 수 있어야 한다. |

S07B 완료 증거:

- 단일 `system/io/output_write` 의미를 유지하면서 `writes` 목록을 동일 I/O 장치 또는 항목별 selector의
  복수 module/channel 요청으로 처리한다.
- 없는 I/O, 잘못된 field/value와 device access 실패를 구체 Exception으로 구분한다.
- 복수 출력은 요청 순서대로 실행하며 all-success, all-fail과 partial-fail을 분리하고 부분 실패 시
  성공 target과 대상별 안전한 Failure를 보존한다.
- S07A/B 계약 테스트 7개와 전체 unittest 90개가 통과했다.

### TD-005-S07C Status/Catalog handler

| 구분 | 계획 |
| --- | --- |
| 목표 | 조회형 status/catalog 요청의 validation, not-ready, resource-not-found와 internal failure 처리를 공통화한다. |
| 주요 변경 | system/axis/IO status와 현재 catalog handler를 분류표에 맞춰 migration하고 조회 응답의 boundary 연결을 완료한다. |
| 필수 계약 | 정상 조회는 기존 data 의미를 보존하고 초기화 미완료, 없는 resource와 예상 밖 내부 오류를 안전하게 구분한다. |
| 제외 범위 | catalog 내용 확장, notification/feedback 변경, Diagnostic 조회 API 신규 설계는 하지 않는다. |
| 완료 조건 | 주요 조회 handler의 정상·not-ready·not-found·unexpected 테스트가 통과하고 legacy 오류 필드 생성이 handler에서 제거된다. |
| 인계 | S08은 startup/runtime 상태를 status 경로에 연결할 기반을, S09는 모든 client 응답 종류의 표본을 확보한다. |

S07C 완료 증거:

- server/bus/axes/axis/IO status 조회를 공통 request boundary에 연결하고 신규 Success data에서는
  레거시 `type`, `ok` field를 제거했다.
- 서버와 버스 상태는 초기화 오류 확인을 위해 계속 조회 가능하며, Catalog runtime 구조가 준비되지
  않은 경우 `SERVER_NOT_READY`로 구분한다.
- axis/IO/module/IO-Link port binding 부재, selector validation과 지원하지 않는 Catalog를 각각
  `RESOURCE_NOT_FOUND`, `INVALID_ARGUMENT`, `UNSUPPORTED_OPERATION`으로 구분한다.
- handler의 broad catch 및 직접 `ok: false/error` 생성을 제거하고 중앙 legacy status adapter가
  기존 client 형식을 S10까지 유지한다.
- 정상 조회, not-ready, not-found, validation과 예상 밖 내부 오류 비노출을 검증하는 S07C 테스트
  9개와 전체 unittest 99개가 통과했다.

### TD-005-S08 Diagnostic core와 startup/runtime 연계

| 구분 | 계획 |
| --- | --- |
| 목표 | 확정된 DiagnosticDefinition/Source/History/Status와 latching lifecycle을 구현하고 운전 상태에 영향이 있는 startup/runtime 실패에 연결한다. |
| 주요 변경 | Diagnostic 저장·조회·발생·acknowledge·resolve·clear core, source 식별, startup/runtime의 Alarm/Fault 분류 지점을 구현한다. |
| 필수 계약 | NORMAL은 status 객체를 만들지 않는다. non-latching은 resolve 시 clear, latching은 resolve와 acknowledge가 모두 충족돼야 clear된다. clear 전 재검출은 동일 건, clear 후 재발은 신규 ID다. API Fail과 Diagnostic은 독립적으로 생성될 수 있다. |
| 제외 범위 | reset/reconnect/restart recovery 정책(RF-005), 장기 영속 저장, 새로운 level 추가는 하지 않는다. |
| 완료 조건 | lifecycle 전이, source uniqueness, 재검출/재발, startup/runtime Alarm/Fault와 API Fail 병행 테스트가 통과한다. |
| 인계 | S09 client가 신규 Diagnostic 응답을 읽고 S10 서버 cutover 후 운전 상태를 확인할 수 있어야 한다. |

S08은 운전 영향 범위를 한 번에 변경하지 않고 다음 순서로 진행한다.

| 하위 단계 | 범위 | 선행 단계 | 상태 |
| --- | --- | --- | --- |
| `TD-005-S08A` | Diagnostic model, 활성 저장소와 lifecycle core | S07C | `complete` |
| `TD-005-S08B` | startup 필수 실패와 Initialization Fault 연결 | S08A | `complete` |
| `TD-005-S08C` | runtime Bus/Axis/IO Alarm·Fault producer와 API Fail 병행 | S08B | `complete` |
| `TD-005-S08D` | 기존 status 경로의 Diagnostic 조회·직렬화 계약 연결 | S08C | `complete` |

#### TD-005-S08A 계약

| 구분 | 기록 내용 |
| --- | --- |
| 공개 계약 | `DiagnosticLevel`, `DiagnosticDefinition`, `DiagnosticSourceType`, `DiagnosticSource`, `DiagnosticHistory`, `DiagnosticStatus`, `DiagnosticManager` |
| 필수 구현 | `(definition.code, source.type, source.index)` 활성 건 uniqueness, detect/acknowledge/resolve, latching clear, 재검출·재발, 계산된 현재 level과 `cleared_at` |
| 선택 기능 | test에서 주입 가능한 clock와 ID factory |
| 내부 helper | 활성 key/ID index, clear 조건 판정 |
| 제외 범위 | startup/runtime 연결, 외부 API serialization, notification, clear 이력 영속 저장, recovery handler |

S08A는 `NORMAL` Definition/Status를 생성하지 않는다. clear된 Status는 장기 보존 정책이 확정되지
않았으므로 활성 저장소에서 제거하고 해당 lifecycle 호출의 반환값으로만 제공한다. 알 수 없는 ID의
acknowledge와 활성 조건이 없는 resolve는 호출 계약 오류로 명확히 거부한다.

S08A 완료 증거:

| 계약 항목 | 구현 위치 | 검증 |
| --- | --- | --- |
| Level, Definition, Source, History, Status와 `cleared_at` | `motion_server/diagnostic/models.py` | NORMAL Status 금지, source type/index 식별, clear 시각 시험 |
| 활성 key/ID uniqueness와 detect | `motion_server/diagnostic/manager.py` | 반복 검출 동일 건, source별 uniqueness, definition 불변 시험 |
| acknowledge/resolve/latching clear | `motion_server/diagnostic/manager.py` | ack/resolve 양쪽 순서와 non-latching 자동 clear 시험 |
| 재검출과 clear 후 재발 | `motion_server/diagnostic/manager.py` | resolved reset, 신규 ID와 occurred_at 시험 |
| 계산된 현재 level | `motion_server/diagnostic/manager.py` | FAULT 우선, ALARM, 활성 건 부재 NORMAL 시험 |

- S08A lifecycle/model 테스트 13개와 전체 unittest 112개가 통과했다.
- startup/runtime 연결, 외부 serialization, notification, 영속 이력과 recovery는 생성하지 않았다.
- 현재 완료 단계는 `TD-005-S08A`, 다음 실행 단계는 `TD-005-S08B`다.

#### TD-005-S08B 완료 증거

- `SERVER_INITIALIZATION_FAILED`는 `SERVER:0`, `FAULT`, latching Definition으로 catalog에 등록했다.
- `AxisRuntime.last_diagnostics` 원시 장치 readback과 별도로 `diagnostic_manager`를 소유한다.
- server reset/bus reconnect의 runtime 재생성 동안 같은 manager를 유지하여 Fault 발생 건과 ID를
  보존한다. 재초기화 성공은 resolve만 수행하며 acknowledge 전에는 clear하지 않는다.
- startup 실패의 Exception 문자열은 Diagnostic `detail/context`에 저장하지 않고 기존 degraded server와
  `initialization_error` 호환 상태는 유지한다.
- 일반 운전 command의 `SERVER_NOT_READY` API Fail은 Initialization Fault를 clear하지 않으며,
  reset/reconnect 계열 recovery command는 기존처럼 허용된다.
- S08B startup Diagnostic 테스트 9개와 전체 unittest 121개가 통과했다.
- 현재 완료 단계는 `TD-005-S08B`, 다음 실행 단계는 `TD-005-S08C`다.

#### TD-005-S08C 세부 단계

| 하위 단계 | 범위 | 상태 |
| --- | --- | --- |
| `TD-005-S08C1` | Bus WKC와 Axis statusword 기반 runtime producer | `complete` |
| `TD-005-S08C2` | IO device-profile health source와 Alarm/Fault 판정 | `complete` |

S08C1 완료 증거:

- `RuntimeDiagnosticMonitor`를 정상 server cycle의 process-data 교환 직후에 실행한다.
- 한 번의 WKC 누락은 Diagnostic을 만들지 않고 3회 연속 불일치할 때
  `BUS_PROCESS_DATA_INCOMPLETE` latching Fault를 생성한다. 정상 WKC가 돌아오면 resolve한다.
- Axis별 CiA 402 statusword fault bit는 `AXIS_DRIVE_FAULT` latching Fault, warning bit는
  `AXIS_DRIVE_WARNING` non-latching Alarm으로 생성·resolve한다.
- 단일 SDO timeout API Fail은 runtime Diagnostic을 생성하지 않는다.
- Bus/Axis runtime Diagnostic 테스트 8개와 전체 unittest 129개가 통과했다.

S08C2 조사 결과와 결정:

- CPX-AP ESI에는 `0x6102 Diagnosis`와 이를 전달하는 선택형 `0x1AF1 Diag PDO`가 존재하지만,
  ESI가 `0x1AF1`을 기본 Sync Manager assignment에 포함하지 않는다.
- 현재 CPX process-image 계약은 설정된 AP module의 입력 byte만 사용한다. `0x1AF1`을 추가하면 PDO
  assignment, input image 크기와 module offset 계약이 함께 변경되므로 TD-005 범위에서 암묵적으로
  활성화하지 않는다.
- S08C2에서는 `IO:<configured index>` station 단위보다 세분된 module/channel Diagnostic을 생성하지
  않는다. Bus WKC로 특정 IO source를 추정하거나 단발 AP/ISDU 요청 실패를 Diagnostic으로 승격하지 않는다.
- 선택형 TxPDO 활성화, `0x6102` 해석, station Alarm/Fault 변환과 real/mock parity는 Optional Item
  `RF-012`에서 구현한다.
- 이 조사와 범위 확정으로 S08C2 및 S08C를 완료하며 다음 실행 단계는 `TD-005-S08D`다.

#### TD-005-S08D 완료 증거

- 기존 server/bus/axis/axes/io status에 공통 `diagnostic_status` snapshot을 추가했다.
- server status는 모든 source, bus는 BUS, 단일 axis는 해당 AXIS, axes는 모든 AXIS, io는 모든 IO
  source의 활성 Diagnostic만 조회한다.
- snapshot은 범위별 현재 `level`과 Definition/Source/History로 구성된 `statuses`를 제공하며 활성 건이
  없으면 `normal`과 빈 목록을 반환한다.
- Fault 우선의 안정적인 정렬, UTC ISO 8601 timestamp와 source filtering을 직렬화 계층에서 담당한다.
- 내부 예약 field `detail/context`는 공개 schema가 확정되지 않았으므로 외부에 직렬화하지 않는다.
- Axis status의 기존 `diagnostics` 원시 CMMT readback은 호환을 위해 변경하지 않고 새 공통 상태와
  `diagnostic_status` 이름으로 구분했다.
- acknowledge 명령, notification과 영속 이력 조회는 S08D 범위에 추가하지 않았다.
- S08D 직렬화/status 테스트 4개와 전체 unittest 133개가 통과했다.
- 이로써 S08 전체를 완료하며 다음 실행 단계는 `TD-005-S09`다.

### TD-005-S09 Control Panel/ROS 호환 읽기

| 구분 | 계획 |
| --- | --- |
| 목표 | 서버 cutover 전에 Control Panel과 ROS client가 legacy 응답과 신규 Success/Fail envelope를 모두 읽게 한다. |
| 주요 변경 | 공통 client response decoder/adapter를 우선 만들고 Axis/IO Control Panel 및 현재 범위의 ROS bridge 호출부를 이관한다. Axis 원시 `diagnostics`는 정식 `device_diagnostics`로 이관하고 기존 이름은 호환 adapter에서만 유지한다. |
| 필수 계약 | 같은 요청에 대해 legacy와 신규 응답이 동일한 사용자 결과/실패 의미로 해석된다. 알 수 없는 code와 malformed response는 안전하게 표시하고 연결 loop를 중단시키지 않는다. |
| 제외 범위 | 서버 dual-write, UI 재설계, ROS 기능 이관 전체(RF-008)는 하지 않는다. |
| 완료 조건 | 저장된 legacy/new fixture 기반 dual-read 테스트, panel/ROS 주요 command smoke test와 malformed response 테스트가 통과한다. |
| 인계 | 모든 배포 client가 신규 envelope를 읽을 수 있다는 증거가 확보돼야 S10을 시작한다. |

S09 완료 증거:

- 독립 `motion_server_client` response decoder가 legacy 응답과 신규 Success/Fail envelope를 같은 client
  view로 정규화한다.
- 신규 Fail의 code/message와 승인된 authority/target details를 안전하게 변환하고 malformed response는
  `MALFORMED_RESPONSE`로 처리한다.
- Axis Control Panel, I/O Control Panel과 ROS Bridge 수신 경계가 공통 decoder를 사용한다.
- Axis/axes status의 원시 CMMT readback 정식 이름을 `device_diagnostics`로 변경했다. client는 기존
  `diagnostics`도 새 이름으로 읽고, 현재 서버 legacy adapter만 구버전 client용 별칭을 함께 송신한다.
- 공통 Motion Server Alarm/Fault는 `diagnostic_status`로 유지하여 원시 장치 readback과 구분한다.
- ROS의 과거 command namespace와 전체 기능 이관은 S09에서 확장하지 않고 RF-008에 유지한다.
- legacy/new 성공·실패, authority detail, malformed 응답과 원시 Diagnostic 명칭 호환 테스트 7개 및
  전체 unittest 140개가 통과했다. ROS Bridge source compile 검사를 함께 수행한다.
- 다음 실행 단계는 서버 송신을 신규 envelope로 전환하는 `TD-005-S10`이다.

### TD-005-S10 서버 Success/Fail envelope 전환

| 구분 | 계획 |
| --- | --- |
| 목표 | 모든 request/response API 송신을 신규 Success/Fail envelope로 한 번에 전환한다. |
| 주요 변경 | router/request boundary를 live 경로에 연결하고 handler의 legacy `ok`, `accepted`, `reason`, top-level `error`, `command_rejected` 응답 생성을 제거한다. |
| 필수 계약 | 모든 요청 응답은 동일 envelope를 사용하고 notification/feedback은 대상에서 제외한다. 비동기 Success는 accepted 의미이며 완료 의미가 아니다. 서버는 legacy/new 필드를 함께 쓰지 않는다. |
| 제외 범위 | client legacy 읽기 제거, notification protocol 재설계, recovery 기능 추가는 하지 않는다. |
| 완료 조건 | API specification의 모든 request type에 대해 success/fail schema 검사가 통과하고 실제 client smoke test에서 회귀가 없다. legacy 필드 검색 결과는 승인된 비응답 위치만 남는다. |
| 인계 | S11에서 client legacy adapter와 임시 compatibility code를 안전하게 제거할 수 있어야 한다. |

S10 완료 증거:

- live router가 모든 등록 request를 요청과 같은 `type`의 Success/Fail envelope로 정확히 한 번 송신한다.
- 요청에 `request_id`가 있으면 그대로 반환하고, 결과가 없는 비동기 command도 빈 `data` Success를 보낸다.
- unknown command, mode, authority와 initialization validation을 안정적인 FailureCode로 변환한다.
- status와 EtherCAT/AP/IO-Link parameter 경로는 typed request boundary의 envelope를 직접 송신하며 기존
  `ok/error` 변환 helper를 제거했다.
- Axis 원시 readback은 신규 data에서 `device_diagnostics`만 사용하고 `diagnostics` 송신 별칭을 제거했다.
- command handler 내부의 기존 직접 송신은 외부 전송 전에 중앙에서 수집하여 단일 envelope로 변환한다.
  이 임시 `_RequestCaptureConnection`은 handler가 data 반환/typed Exception 계약으로 정리되는 S11에서 제거한다.
- 주기 `system/feedback`과 자발적 notification은 기존 독립 payload를 유지한다.
- live status, unknown command, authority failure/status, 빈 command Success와 예상 밖 내부 오류 비노출
  cutover 테스트 6개를 추가했으며 전체 unittest 145개와 source compile 검사가 통과했다.
- 다음 실행 단계는 legacy 및 broad catch 정리를 수행하는 `TD-005-S11`이다.

### TD-005-S11 정리와 회귀 방지

| 구분 | 계획 |
| --- | --- |
| 목표 | migration을 위해 남긴 legacy와 불필요한 broad catch를 제거하고 계약 위반을 자동 검출한다. |
| 주요 변경 | client legacy decoder 제거 여부 확정 및 제거, `TECH_DEBT[TD-005]` 임시 코드 정리, broad catch allowlist와 API schema/mapping 정적 검사를 CI 또는 test suite에 추가한다. |
| 필수 계약 | broad catch는 process/request/client 최상위 등 승인된 경계에만 존재하고 각 위치의 logging/connection 정책이 문서화된다. FailureCode/mapping/API schema 불일치는 자동 실패한다. |
| 제외 범위 | TD-005 조사에서 별도 RF/TD로 분리된 기능과 recovery 정책은 구현하지 않는다. |
| 완료 조건 | inventory의 TD-005 대상이 구현·제외·후속 작업 중 하나로 모두 추적되고 전체 자동 테스트, broad catch allowlist, legacy 응답 부재 검사가 통과한다. TD-005 상태를 `complete`로 바꾸고 Work Log에 최종 증거를 기록한다. |
| 인계 | 후속 오류 변경은 확정된 Exception/Failure/Diagnostic 계약과 자동 검사 안에서 수행한다. |
