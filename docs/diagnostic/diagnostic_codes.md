# Diagnostic Code Catalog

이 문서는 Motion Server가 생성하는 안정적인 Diagnostic code와 발생·해제 조건을 관리한다.
API 요청 실패 code는 [API Failure Code](../api/failure_codes.md)에서 별도로 관리한다.

## Server

### SERVER_INITIALIZATION_FAILED

| 항목 | 값 |
| --- | --- |
| Level | `FAULT` |
| Source | `SERVER:0` |
| Latching | `true` |
| 발생 조건 | 필수 drive startup initialization 실패로 degraded server mode에 진입함 |
| Resolve 조건 | 같은 프로세스의 runtime 재초기화가 성공함 |
| Clear 조건 | resolve와 사용자 acknowledge가 모두 완료됨 |

Exception 문자열은 Diagnostic `detail/context`에 저장하지 않는다. 기존 `initialization_error` 상태
field는 현재 client 호환을 위해 유지하며 S08D의 Diagnostic 직렬화 계약과 S09 client migration에서
표시 책임을 다시 검토한다.

서버 reset과 bus reconnect는 같은 프로세스의 `DiagnosticManager`를 새 runtime에 전달한다. 따라서
재초기화 성공은 이 Fault를 resolve하지만 acknowledge 없이 제거하지 않는다. 전체 프로세스 재시작을
넘는 영속 저장은 현재 범위에 포함하지 않는다.
