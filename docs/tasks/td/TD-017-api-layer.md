# TD-017 Motion Server API Layer 구조 정리

## 상태

`complete`

## 완료 전 구조

API message 해석, validation, handler 선택, response 생성과 기능별 handler가 `motion_server/api`와
`motion_server/commands`에 혼재되어 있었다.

## 목표 및 완료 결과

- 처리 흐름을 `decoder -> validator -> router -> handler -> encoder`로 정리했다.
- `api` package에는 protocol boundary를 남겼다.
- command, status와 authority handler를 `motion_server/handlers` 아래로 분리했다.
- parameter access를 EtherCAT, AP와 IOL 구현으로 분리했다.
- authority, status와 command registry가 API specification과 handler 목록을 startup 전에 검증한다.

## 주요 변경 위치

- `motion_server/api/decoder.py`
- `motion_server/api/validator.py`
- `motion_server/api/router.py`
- `motion_server/api/encoder.py`
- `motion_server/api/specification.py`
- `motion_server/handlers/authority/*`
- `motion_server/handlers/status/*`
- `motion_server/handlers/command/*`
- `motion_server/handlers/parameter_access/*`

## 완료 증거

- 완료 커밋: `9002743 Refactor motion server API and remote IO config`
- 상세 작업 이력: [Work Log](../../worklog.md)
