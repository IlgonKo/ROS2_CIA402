# TD-006 설정 로더와 Bus Parser 중복

## 배경 및 현재 구조

공통 `config_file.py` 외에 ROS runtime, packaging과 panel이 자체 설정 해석을 수행한다.

## 문제와 위험

continuation, indexed entry, explicit `axis:`/`io:` 형식이 실행 경로에 따라 다르게 해석될 수 있다.

## 관련 위치

- `config_file.py`
- `motion_server/config.py`
- `ros/axis_runtime_config.py`
- `packaging/windows_runtime.py`
- Control Panel별 `config.py`

## 목표 구조 및 구현 범위

- file parsing, environment overlay, validation과 typed bus model의 책임을 분리한다.
- 모든 실행 경로가 공통 parser와 bus model을 사용한다.
- client별 설정은 공통 model 위의 명시적인 projection으로 제한한다.

## 검증 계획

- 동일 fixture를 모든 entrypoint에 적용해 결과가 같은지 검증한다.
- continuation, indexed entry, axis/I/O 혼합 bus와 잘못된 설정을 테스트한다.

## 완료 증거

완료 시 제거한 parser 목록, 공통 model과 fixture 테스트 결과를 기록한다.
