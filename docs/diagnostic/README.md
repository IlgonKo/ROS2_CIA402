# Diagnostic 문서

이 폴더는 Motion Server와 장치의 현재 운전 상태 및 그 수명 주기를 관리한다.
용어와 API 결과의 경계는 [DEC-015](../decisions.md#dec-015-api-결과와-diagnostic-상태를-분리)를 따른다.

`DiagnosticLevel`은 다음 세 값만 사용한다.

- `NORMAL`: 활성 Alarm이나 Fault 없이 정상 운전 가능한 상태
- `ALARM`: 확인이나 대응이 필요하지만 정상 운전을 계속할 수 있는 상태
- `FAULT`: 운전이 제한·중단되거나 degraded 또는 unavailable인 상태

API 요청의 `Success`와 `Fail`은 Diagnostic에 포함하지 않는다. Python `Exception`은 내부 전달
수단이며, 처리 결과와 운전 영향에 따라 API Fail 또는 Alarm/Fault Diagnostic으로 각각 변환한다.

## 현재 문서

- [diagnostic_model.md](diagnostic_model.md): 확정된 Diagnostic 객체 구성과 acknowledge/resolve/clear 규칙
- [error_point_inventory.md](error_point_inventory.md): 현재 Python exception 발생·catch 지점과 migration inventory

## 추가 예정 문서

- Alarm/Fault 판정, acknowledge, clear 및 recovery 정책
- Diagnostic code와 source/context 계약

## 설계 및 구현 순서

아래 순서를 고정하며 앞 단계의 계약을 확정하기 전에 다음 단계 구현을 시작하지 않는다.

1. **완료:** Diagnostic 데이터 모델과 수명 주기를 확정한다.
2. **진행 중:** API Success/Fail 응답 계약, failure code와 exception 변환 규칙을 확정한다.
   공통 envelope, code catalog와 mapper 구조는 완료했고 구체적인 내부 Exception 계층이 남아 있다.
3. **대기:** [Exception inventory](error_point_inventory.md)의 각 지점을 `API Fail`, `Alarm`, `Fault`,
   `Internal only`로 분류한다. 한 지점은 API Fail과 Diagnostic을 동시에 만들 수 있다.
4. **대기:** 분류 결과를 바탕으로 TD-005의 exception 계층, API failure mapper, Diagnostic 관리,
   logging 및 오류 주입 테스트 구현 계획을 확정한다.

확정 전 설계안은 현재 동작처럼 기록하지 않는다.
