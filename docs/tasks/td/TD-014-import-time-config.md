# TD-014 Import 시점 전역 설정 로딩

## 배경 및 현재 구조

`motion_server/config.py` import가 `.env`와 device config를 읽고 `os.environ`을 변경한다.

## 문제와 위험

테스트 격리, 한 process의 여러 runtime 구성과 packaging entrypoint 동작을 예측하기 어렵다.

## 목표 구조 및 구현 범위

- 명시적인 configuration loader가 immutable typed configuration을 생성한다.
- server와 runtime에 configuration을 dependency로 주입한다.
- module import는 filesystem과 process environment를 변경하지 않는다.

## 관련 위치

- `motion_server/config.py`
- `motion_server/server.py`
- packaging entrypoint
- configuration을 직접 import하는 module

## 검증 계획

- import 전후 environment와 filesystem 접근을 검사한다.
- 서로 다른 configuration 두 개를 같은 process에서 생성해 격리를 검증한다.
- Windows packaging과 Linux startup 경로를 smoke test한다.

## 완료 증거

완료 시 configuration object, dependency graph와 격리 테스트 결과를 기록한다.

