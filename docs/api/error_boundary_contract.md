# Error boundary와 broad catch 계약

## 기본 원칙

- 요청 handler와 control 계층은 data, `PartialFailure` 또는 typed `MotionServerException`을 반환한다.
- `motion_server/api/router.py`의 request boundary만 Exception을 Failure로 변환하고 응답을 송신한다.
- 예상하지 못한 Exception은 `INTERNAL_FAILURE`로 비노출 처리하되 request type과 request ID만 exception
  log에 기록한다.
- broad catch는 오류를 무시하기 위한 수단이 아니라 아래 승인 목적 중 하나를 가져야 한다.

## 승인 목적

| 목적 | 처리 계약 |
| --- | --- |
| request/process/client 최상위 경계 | 전체 traceback을 기록하고 안전한 Failure 또는 연결/프로세스 정책으로 종결한다. |
| backend/transport 변환 경계 | 외부 라이브러리 오류를 typed Exception으로 변환하며 내부 문자열은 API에 노출하지 않는다. |
| multi-target 또는 startup best-effort 수집 | 대상별 실패를 기록하고 `PartialFailure` 또는 Diagnostic/readback 결과로 보존한다. |
| cleanup/관측 경계 | 원래 실패를 덮지 않도록 cleanup 또는 선택적 관측 실패만 격리한다. |
| UI/ROS client 경계 | 연결 loop를 보호하고 안전한 client 실패 상태로 변환한다. |

## 자동 검사

`tests/test_error_contract_static.py`가 다음 계약을 검사한다.

- broad catch가 승인된 파일·함수 allowlist와 정확히 일치한다.
- Exception mapping이 공개 `FailureCode`만 사용한다.
- request capture, `_operation_result`, legacy rejection과 `TECH_DEBT[TD-005]`가 다시 추가되지 않는다.
- request handler/control 계층에서 transport 송신을 직접 수행하지 않는다.

allowlist는 줄 번호가 아니라 함수 단위로 관리한다. 새 broad catch가 필요하면 먼저 위 목적과 처리 계약을
확정한 후 allowlist와 테스트를 함께 변경한다. 단순히 테스트 통과를 위해 항목을 추가하지 않는다.
