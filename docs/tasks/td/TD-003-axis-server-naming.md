# TD-003 Axis Server 과거 명칭 잔존

## 배경 및 현재 구조

서버 로그, script 문구, 문서와 GUI 일부에 과거 명칭인 `Axis Server`가 남아 있었다.
공식 프로젝트 및 서버 명칭인 `Motion Server`로 사용자 노출 문구를 통일했다.

## 상태

`complete`

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

## 완료 내용

- Motion Server CLI, runtime log와 API error 문구를 `Motion Server`로 통일했다.
- Axis Control Panel의 제품명은 유지하고 과거 `Axis Server Control Panel` 표기를 수정했다.
- ROS Bridge/Control Panel의 사용자 노출 연결·authority·trajectory 문구를 수정했다.
- README, architecture, Windows packaging과 host/Windows script의 현재 동작 설명을 수정했다.
- systemd unit 설명은 `Motion Server`로 변경했다.
- `diagnostics/check_legacy_names.py`를 추가해 허용 목록 밖의 과거 명칭을 검출하게 했다.

## 유지한 Legacy Identifier

- Motion Server Docker/systemd 실행 식별자는 TD-020에서 직접 전환한다.
- `ROS2_CIA402_*` 및 ROS image/package 식별자는 RF-008 범위에서 처리한다.
- `ROS2_CIA402/virtual_ethercat` 경로: TD-019에서 처리한다.
- 과거 작업 이력과 이 TD의 설명은 역사 및 추적 목적으로 유지한다.

## 검증 계획

- 저장소 전체 명칭 검색을 자동화하고 허용 목록 외 `Axis Server` 사용을 실패로 처리한다.
- Windows/Linux 시작 script와 packaging entrypoint를 확인한다.

## 완료 증거

- `python -B diagnostics/check_legacy_names.py` 통과
- Motion Server, device, Control Panel, ROS와 diagnostics Python 문법 검사 통과
- 주요 Motion Server/Control Panel module import 검사 통과
- 상세 변경 이력: [Work Log](../../worklog.md)
