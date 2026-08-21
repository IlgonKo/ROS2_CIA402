# TD-018 Runtime 생성 단계 Initialization Error 처리

## 배경 및 현재 구조

- `motion_server/server.py`는 `initialize_drive()` 실패만 degraded server loop로 전환한다.
- runtime 생성 중 device profile/config/ESI 검증 오류는 degraded 경계 밖에서 발생해 process가 종료된다.
- CPX module layout과 ESI PDO size mismatch가 발생하면 client가 진단과 복구 API에 연결할 수 없다.

## 문제와 위험

설정 오류와 ESI mismatch가 server startup failure로만 노출되며, 운전 중 복구 가능한 오류와
runtime 생성 오류의 진단 경험이 서로 다르다.

## 관련 위치

- `motion_server/server.py`
- `motion_server/app/startup.py`
- `device/cpx_ap_i_ec/io_config.py`
- `device/cpx_ap_i_ec/module_resolver.py`

## 목표 구조 및 구현 범위

- configuration/profile/catalog 검증 실패를 initialization-error state로 표현한다.
- 최소 degraded runtime 또는 별도 degraded server state에서도 TCP server를 기동한다.
- `system/server/status`, `system/bus/status`, reset/restart/reconnect API를 제공한다.
- API response와 server log에 동일한 원인 식별자와 메시지를 사용한다.

## 검증 계획

- mock runtime 생성 단계에 profile, catalog와 configuration 오류를 주입한다.
- degraded 상태의 status, reset, restart와 reconnect 응답 및 복구를 검증한다.
- 대표 CPX layout/ESI mismatch fixture를 사용한다.

## 완료 증거

완료 시 error state model, API 예제와 오류 주입 테스트 결과를 기록한다.

