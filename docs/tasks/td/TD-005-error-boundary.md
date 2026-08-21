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

| 하위 작업 | 범위 | 선행 작업 | 상태 |
| --- | --- | --- | --- |
| `TD-005-S01` | FailureCode, Exception 계층, Mapper, PartialFailure 기반 | 없음 | `complete` |
| `TD-005-S02` | Response encoder, request boundary와 기존 API adapter | S01 | `pending` |
| `TD-005-S03` | EtherCAT SDO 및 Mock/PySOEM Exception parity | S01 | `pending` |
| `TD-005-S04` | Axis/IO EtherCAT parameter handler | S02, S03 | `pending` |
| `TD-005-S05` | AP parameter 경로 | S03, S04 | `pending` |
| `TD-005-S06` | IO-Link ISDU 경로 | S03, S04 | `pending` |
| `TD-005-S07A` | Motion/Axis command와 PartialFailure | S02-S04 | `pending` |
| `TD-005-S07B` | IO command와 PartialFailure | S02-S06 | `pending` |
| `TD-005-S07C` | Status/Catalog handler | S02-S06 | `pending` |
| `TD-005-S08` | Diagnostic core와 startup/runtime 연계 | S01-S07 | `pending` |
| `TD-005-S09` | Control Panel과 ROS의 기존/신규 응답 호환 | S02-S08 | `pending` |
| `TD-005-S10` | 서버 Success/Fail envelope 최종 전환 | S09 | `pending` |
| `TD-005-S11` | legacy 제거, broad catch allowlist와 자동 검사 | S10 | `pending` |

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
