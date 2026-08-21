# API 문서

이 폴더는 Motion Server 외부 요청과 응답 계약을 관리한다.

API 요청 결과는 `Success` 또는 `Fail`로 표현한다. `Fail`은 개별 요청의 실패 결과이며
시스템의 지속 상태나 Diagnostic level이 아니다.

## 현재 문서

- [response_contract.md](response_contract.md): 확정된 공통 Success/Fail response envelope
- [failure_codes.md](failure_codes.md): 초기 failure code catalog와 Exception 변환 원칙
- [exception_mapping.md](exception_mapping.md): 내부 Exception과 API Failure의 중앙 mapping 계약

기존 발생·catch 지점의 목표 분류와 migration 범위는 TD-005의 다음 설계 단계에서 확정한다.

운전 상태를 나타내는 `NORMAL`, `ALARM`, `FAULT`와 그 수명 주기는
[Diagnostic 문서](../diagnostic/README.md)에서 관리한다.
