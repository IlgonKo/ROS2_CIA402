# TD-009 API 문서와 구현 불일치

## 배경 및 현재 구조

- 일부 server reset/restart, bus reconnect와 IO-Link ISDU API의 문서상 지원 여부가 route와 다르다.
- README의 PDO remap 정책 설명이 현재 구현과 다르다.
- 과거 Axis Server 명칭과 manual CSP count scale 설명이 남아 있다.

## 관련 위치

- `docs/motion_server_api_basic.md`
- `README.md`
- `docs/motion_server_architecture.md`
- `motion_server/api/specification.py`
- handler registry

## 목표 구조 및 구현 범위

- API specification과 handler registry를 authoritative source로 검증한다.
- 공개 command 목록 또는 검증 가능한 documentation metadata를 specification과 연결한다.
- 사용 예제와 정책 설명을 현재 구현에 맞춘다.

## 검증 계획

- specification, registry와 문서 command 목록의 차이를 CI에서 검사한다.
- 문서의 JSON 예제를 parse하고 가능한 예제는 mock smoke test로 실행한다.

## 완료 증거

완료 시 동기화 방식, 수정 문서 목록과 자동 검사 결과를 기록한다.
