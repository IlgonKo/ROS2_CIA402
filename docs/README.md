# Documentation Guide

이 폴더는 Motion Server 프로젝트의 설계, API, 시험, 계획과 작업 이력을 관리한다.
처음 프로젝트를 보는 사람은 아래 순서로 문서를 읽는다.

1. [프로젝트 README](../README.md): 프로젝트 개요, 실행 방법과 폴더 구성
2. [Software Architecture](motion_server_architecture.md): 주요 컴포넌트와 내부 처리 흐름
3. [Basic Mode API](motion_server_api_basic.md): TCP JSON API 계약과 사용 예제
4. [Test Procedure](test_procedure.md): 변경 검증과 배포 전 시험 절차
5. [Decisions](decisions.md): 장기간 유지해야 하는 설계 결정과 변경 사유
6. [Remaining Tasks](remaining_tasks.md): 미완료 기능과 기술 부채
7. [Work Log](worklog.md): 날짜별 완료 작업 이력

## 문서별 책임

| 문서 | 기록하는 내용 | 기록하지 않는 내용 |
| --- | --- | --- |
| `README.md` | 사용자가 처음 실행할 때 필요한 현재 정보 | 상세 내부 설계, 작업 일지 |
| `motion_server_architecture.md` | 현재 구현의 구조와 책임 경계 | 미래 계획, 날짜별 변경 내역 |
| `motion_server_api_basic.md` | 현재 지원하는 API 계약 | 아직 확정되지 않은 API |
| `test_procedure.md` | 반복 가능한 검증 절차와 판정 기준 | 특정 시험 1회의 긴 로그 |
| `decisions.md` | 중요한 결정, 이유, 대안과 파급 효과 | 단순 구현 세부사항 |
| `remaining_tasks.md` | 미완료 기능, 기술 부채와 완료 조건 | 완료 작업의 상세 이력 |
| `tasks/td/TD-*.md` | TD별 현재 구조, 위험, 구현 범위와 검증 계획 | 전체 작업의 상태 요약 |
| `worklog.md` | 실제 완료된 변경의 요약 | 미확정 계획과 장기 설계 설명 |

## 갱신 규칙

- 기능이나 기술 부채의 상태가 바뀌면 `remaining_tasks.md`를 갱신한다.
- TD의 기술 분석과 구현 세부사항은 `tasks/td/TD-*.md`에 기록하고
  `remaining_tasks.md`에는 요약과 검증 가능한 완료 조건만 유지한다.
- 작업이 완료되면 같은 변경에서 `worklog.md`에 결과와 검증 내용을 기록한다.
- API 동작이 바뀌면 구현, API 문서와 관련 시험 절차를 함께 갱신한다.
- 아키텍처의 책임 경계나 장기 정책이 바뀌면 `decisions.md`에 결정을 추가하고
  `motion_server_architecture.md`의 현재 상태를 맞춘다.
- 문서에는 현재 동작과 계획을 구분해서 적는다. 계획 중인 항목을 현재 지원 기능처럼 표현하지 않는다.
- 외부 매뉴얼, ESI/IODD, packet capture와 측정 데이터는 `Reference/`에서 관리하고
  프로젝트가 직접 유지하는 설명 문서는 `docs/`에서 관리한다.

## 결정 식별자

설계 결정은 `DEC-###`, 기능은 `RF-###`, 기술 부채는 `TD-###` 형식을 사용한다.
기존 식별자는 재사용하지 않는다.
