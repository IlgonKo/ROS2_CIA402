# TD-003 Axis Server 과거 명칭 잔존

## 배경 및 현재 구조

서버 로그, script 문구, 문서, 변수와 class 이름 일부에 과거 명칭인 `Axis Server`가 남아 있다.
공식 프로젝트 및 서버 명칭은 `Motion Server`다.

## 관련 위치

- `README.md`
- `motion_server/config.py`
- `motion_server/server.py`
- `scripts/host/*`
- `scripts/windows/*`
- packaging 문서와 설정

## 범위 제외 및 제약

- 제품명이 확정된 `Axis Control Panel`은 변경 대상이 아니다.
- 기존 환경변수, container, systemd service와 설치 경로는 하위 호환성 정책 없이 즉시 제거하지 않는다.
- 프로젝트·설치 경로 변경은 [TD-019](TD-019-project-path-migration.md), 실행 식별자 migration은
  [TD-020](TD-020-legacy-runtime-identifiers.md)에서 별도로 추적한다.

## 목표 구조 및 구현 범위

- 사용자 노출 명칭을 `Motion Server`로 통일한다.
- 내부 identifier는 의미와 호환성 영향을 검토해 변경하거나 허용 목록에 기록한다.
- legacy identifier를 유지할 경우 신규 명칭 우선, 기존 명칭 fallback과 제거 시점을 명시한다.

## 검증 계획

- 저장소 전체 명칭 검색을 자동화하고 허용 목록 외 `Axis Server` 사용을 실패로 처리한다.
- Windows/Linux 시작 script와 packaging entrypoint를 확인한다.

## 완료 증거

완료 시 커밋, 명칭 검사 결과와 호환성 목록을 기록한다.
