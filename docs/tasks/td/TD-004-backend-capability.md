# TD-004 Backend Capability Fallback과 오래된 Servo Interface

## 배경 및 현재 구조

- `ServoInterface`와 `Axis`가 virtual servo 중심의 오래된 계약을 유지한다.
- 선택 기능을 `hasattr()`로 확인해 호출하는 경로가 있다.
- startup이 backend method 존재 여부로 staged startup과 restart 지원을 판단한다.

## 문제와 위험

지원 기능이 암묵적이어서 backend 구현 누락이 startup 이후에 발견될 수 있고,
device profile과 transport capability의 책임이 섞인다.

## 관련 위치

- `interfaces/servo_interface.py`
- `motion_server/control/axis.py`
- `motion_server/app/startup.py`
- `motion_server/server.py`

## 목표 구조 및 구현 범위

- backend와 device profile capability를 명시적인 interface 또는 immutable capability object로 표현한다.
- 필수 method와 선택 기능을 startup validation에서 구분한다.
- 암묵적인 `hasattr()` fallback을 제거한다.

## 검증 계획

- mock/PySOEM backend의 capability 선언과 필수 method 일치 여부를 테스트한다.
- capability 누락과 지원하지 않는 기능 요청의 오류를 테스트한다.

## 완료 증거

완료 시 interface 정의, migration 결과와 자동 테스트 링크를 기록한다.
