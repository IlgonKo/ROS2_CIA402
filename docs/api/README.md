# API 문서

이 폴더는 Motion Server 외부 요청과 응답 계약을 관리한다.

API 요청 결과는 `Success` 또는 `Fail`로 표현한다. `Fail`은 개별 요청의 실패 결과이며
시스템의 지속 상태나 Diagnostic level이 아니다. 상세 Fail response와 안정적인 failure code는
TD-005에서 확정한 뒤 이 폴더에 기록한다.

운전 상태를 나타내는 `NORMAL`, `ALARM`, `FAULT`와 그 수명 주기는
[Diagnostic 문서](../diagnostic/README.md)에서 관리한다.
