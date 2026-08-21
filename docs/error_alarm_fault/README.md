# Error·Alarm·Fault 문서

이 폴더는 Motion Server가 사용자에게 표시하는 Error·Alarm·Fault 수준과 이를 만드는 내부 오류 처리
정책을 관리한다. 용어 정의는 [DEC-015](../decisions.md#dec-015-사용자-노출-오류-수준을-erroralarmfault로-구분)를 따른다.

## 현재 문서

- [point_list.md](point_list.md): 현재 Python 오류 발생·catch 지점과 migration inventory

## 추가 예정 문서

- 수준별 판정 및 승격 정책
- API error response와 안정적인 code
- connection/runtime 유지 및 복구 정책
- broad exception 허용 목록

확정 전 설계안은 현재 동작처럼 기록하지 않는다. 사용자 API 계약이 확정되면 API 문서와 시험 절차도
같은 변경에서 갱신한다.
