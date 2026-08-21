# TD-020 Legacy 실행 식별자 Migration

## 배경 및 현재 구조

실행 환경에 과거 ROS2/CiA402 및 Axis Server 명칭을 포함한 식별자가 남아 있다.

- Docker image/container: `ros2_cia402_*`, `ros_cia402_motion_server`
- systemd unit: `ros-cia402-axis-server.service`
- environment: `ROS2_CIA402_AXIS_NAMES`, `ROS2_CIA402_INTERFACE`
- script cleanup과 log command가 legacy container/service 이름을 직접 사용한다.

## 문제와 위험

- 사용자 노출 명칭과 운영 식별자가 달라 설치 및 장애 대응이 혼란스럽다.
- 즉시 변경하면 실행 중인 container, 설치된 systemd unit, `.env`와 외부 automation이 중단될 수 있다.
- 신규/기존 이름을 무기한 함께 지원하면 fallback과 cleanup code가 기술 부채로 남는다.

## 선행 결정

- 신규 Docker project/image/container와 systemd unit 이름
- 신규 environment variable namespace
- 지원할 alias/fallback 방향과 경고 방식
- 호환 기간 및 legacy 식별자 제거 version

## 구현 범위

- 신규 설치와 생성 artifact는 Motion Server 기반 식별자를 기본값으로 사용한다.
- legacy environment variable은 신규 값이 없을 때만 읽고 deprecation warning을 제공한다.
- systemd unit의 stop/disable/install migration과 container rename/recreation 절차를 제공한다.
- start/stop/service script가 신규 및 migration 대상 legacy resource를 안전하게 처리한다.
- fallback마다 제거 대상 TD 표식 또는 동등한 추적 정보를 남긴다.

## 범위 제외

- repository 및 filesystem 경로는 [TD-019](TD-019-project-path-migration.md)에서 처리한다.
- ROS package, topic, action과 robot identifier는 [RF-008](../rf/RF-008-ros-bridge-migration.md)에서 처리한다.
- 제품명이 확정된 `Axis Control Panel`은 변경하지 않는다.

## 검증 계획

- legacy `.env`와 신규 `.env`의 precedence 및 warning을 자동 테스트한다.
- 기존 container/service가 설치된 환경의 upgrade와 rollback을 검증한다.
- clean Windows/Linux 설치가 신규 식별자만 생성하는지 확인한다.
- 호환성 allowlist 외 legacy identifier를 검사한다.

## 완료 증거

완료 시 identifier mapping, deprecation 일정, upgrade/rollback 및 clean-install 시험 결과를 기록한다.
